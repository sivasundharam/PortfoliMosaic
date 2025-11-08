from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load environment variables from .env file (look in project root)
import pathlib
project_root = pathlib.Path(__file__).parent.parent.parent  # Go up to PortfoliMosaic root
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

from .db import Base, engine, SessionLocal
from .models import Document, Holding, BalanceSheetItem, IncomeStatementItem, CashFlowItem
from .schemas import HoldingCreate, HoldingRead, FinancialItemCreate, FinancialItemRead
from .services.rag import RAGService
from .services.portfolio_agent import PortfolioAgent  # Portfolio agent with multiple tools (RAG + SQL + API)
from .services.landing_ade import LandingAdeService
from .services.classifier import DocumentClassifier
from .services.consolidator import HoldingsConsolidator
from .services.landing_ai import LandingAIClient, LandingAIError
from .services.extraction_schema import PORTFOLIO_SCHEMA, categorize_extraction

APP_PREFIX = "/api"

app = FastAPI(title="Portfolio Assistance AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve paths relative to project root
UPLOAD_DIR = str(project_root / os.getenv("UPLOAD_DIR", "data/uploads"))
EXTRACTED_DIR = str(project_root / os.getenv("EXTRACTED_DIR", "data/extracted"))
VECTOR_DIR = str(project_root / os.getenv("VECTOR_DIR", "data/vector_index"))
ALLOWED_FILE_EXT = set(os.getenv("ALLOWED_FILE_EXT", "pdf,png,jpg,jpeg,xlsx,xls").split(","))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

for d in [UPLOAD_DIR, EXTRACTED_DIR, VECTOR_DIR]:
    os.makedirs(d, exist_ok=True)

# Ensure DB tables exist
Base.metadata.create_all(bind=engine)

# Initialize services
rag_service = RAGService()  # Keep for backward compatibility
# Note: RAGAgent is created per-request with database session (see chat endpoint)
ade_service = LandingAdeService()
classifier = DocumentClassifier()
consolidator = HoldingsConsolidator()
executor = ThreadPoolExecutor(max_workers=4)

# Use agent by default (set to False to use old RAG service)
USE_AGENT = os.getenv("USE_AGENT", "true").lower() == "true"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    document_type: Optional[str] = None
    extraction_status: str = "processing"


class ExtractResponse(BaseModel):
    document_id: str
    status: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_indexed: int


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    top_k: int = 4


class Citation(BaseModel):
    document_id: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    session_id: str


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Chunk text intelligently with overlap"""
    if not text or len(text) < chunk_size:
        return [text] if text else []
    
    chunks = []
    lines = text.splitlines()
    current_chunk = []
    current_size = 0
    
    for line in lines:
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            # Keep last N lines for overlap
            overlap_lines = current_chunk[-overlap//10:] if len(current_chunk) > overlap//10 else []
            current_chunk = overlap_lines
            current_size = sum(len(l) + 1 for l in current_chunk)
        
        current_chunk.append(line)
        current_size += line_size
    
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks


def _chunk_markdown(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """Chunk markdown intelligently, preserving structure (headers, tables, lists)"""
    if not text or len(text) < chunk_size:
        return [text] if text else []
    
    import re
    
    # Split by headers first (natural boundaries)
    header_pattern = r'^(#{1,6})\s+(.+)$'
    sections = []
    current_section = []
    
    lines = text.splitlines()
    for line in lines:
        if re.match(header_pattern, line):
            if current_section:
                sections.append("\n".join(current_section))
            current_section = [line]
        else:
            current_section.append(line)
    
    if current_section:
        sections.append("\n".join(current_section))
    
    # Chunk each section, but keep headers together
    chunks = []
    for section in sections:
        if len(section) <= chunk_size:
            chunks.append(section)
        else:
            # Further chunk the section
            lines = section.splitlines()
            current_chunk = []
            current_size = 0
            
            for line in lines:
                line_size = len(line) + 1
                if current_size + line_size > chunk_size and current_chunk:
                    chunks.append("\n".join(current_chunk))
                    # Overlap: keep last few lines
                    overlap_lines = current_chunk[-overlap//15:] if len(current_chunk) > overlap//15 else []
                    current_chunk = overlap_lines
                    current_size = sum(len(l) + 1 for l in current_chunk)
                
                current_chunk.append(line)
                current_size += line_size
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
    
    return chunks if chunks else [text]


def _table_to_text(table: List[List[str]]) -> str:
    """Convert table array to readable text"""
    if not table:
        return ""
    
    lines = []
    for row in table:
        if row:
            # Filter out None values and convert to string
            clean_row = [str(cell) if cell is not None else "" for cell in row]
            lines.append(" | ".join(clean_row))
    return "\n".join(lines)


def extract_and_classify(document_id: str, filename: str):
    import time
    import json

    # ========================================
    # PERFORMANCE TRACKING
    # ========================================
    start_time = time.time()
    timings = {}

    def log_timing(step_name: str, step_start: float):
        """Log timing for a step"""
        elapsed = time.time() - step_start
        timings[step_name] = elapsed
        print(f"⏱️  [{step_name}] took {elapsed:.2f}s")
        return time.time()

    db = SessionLocal()
    try:
        step_start = time.time()
        doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
        if not doc:
            return

        doc.extraction_status = "extracting"
        db.commit()
        log_timing("DB_INIT", step_start)

        file_path = os.path.join(UPLOAD_DIR, document_id)
        if not os.path.exists(file_path):
            doc.extraction_status = "error"
            db.commit()
            return

        # Get file size for context
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        print(f"\n{'='*60}")
        print(f"📄 Processing: {filename}")
        print(f"📦 File size: {file_size_mb:.2f} MB")
        print(f"{'='*60}\n")

        # ========================================
        # LANDING AI ADE: Parse + Extract
        # ========================================
        result = None  # Initialize result for fallback path
        try:
            landing_client = LandingAIClient()

            # Step 1: Parse PDF → Markdown
            step_start = time.time()
            print(f"📄 [1/5] Parsing PDF with Landing AI ADE...")
            parsed = landing_client.parse_pdf(file_path)
            markdown = parsed.get("markdown", "")
            print(f"   ✓ Extracted {len(markdown)} characters of markdown")
            step_start = log_timing("LANDING_AI_PARSE", step_start)

            if not markdown or len(markdown.strip()) < 10:
                print(f"⚠️ No markdown extracted, falling back to local parser")
                step_start = time.time()
                result = ade_service.extract(file_path, filename)
                markdown = result.get("markdown") or result.get("text", "")
                step_start = log_timing("FALLBACK_PARSE", step_start)

            # Step 2: Extract Structured Data using Portfolio Schema
            step_start = time.time()
            print(f"🔍 [2/5] Extracting structured data with Landing AI ADE...")
            print(f"   Schema fields: {len(PORTFOLIO_SCHEMA.get('properties', {}))} top-level fields")
            extraction_result = landing_client.extract_from_markdown(markdown, PORTFOLIO_SCHEMA)
            extraction_json = extraction_result.get("extraction", {})
            print(f"   ✓ Extracted {len(extraction_json)} fields")
            step_start = log_timing("LANDING_AI_EXTRACT", step_start)

            # Step 3: Categorize extraction by domain
            step_start = time.time()
            print(f"📊 [3/5] Categorizing extracted data...")
            categorized_data = categorize_extraction(extraction_json)
            print(f"   ✓ Categorized into {len(categorized_data)} groups")
            step_start = log_timing("CATEGORIZE", step_start)

            # Debug output (truncated)
            print(f"\n📋 Extraction Summary:")
            print(f"   Document Type: {extraction_json.get('DocumentType', 'Unknown')}")
            print(f"   Report Date: {extraction_json.get('ReportDate', 'N/A')}")
            print(f"   Holdings: {len(extraction_json.get('Holdings', []))} items")

            # Store in database
            step_start = time.time()
            doc.markdown = markdown
            doc.extraction_json = json.dumps(extraction_json)
            doc.categorized_data = json.dumps(categorized_data)
            doc.ade_metadata = json.dumps(extraction_result.get("confidence", {}))
            doc.document_type = extraction_json.get("DocumentType", "Unknown")
            step_start = log_timing("DB_STORE_EXTRACTION", step_start)

        except LandingAIError as e:
            step_start = time.time()
            print(f"❌ Landing AI ADE failed: {e}")
            print(f"   Marking document as 'failed' - no fallback to local parser")
            # Mark as failed and return error to frontend
            doc.extraction_status = "failed"
            db.commit()
            step_start = log_timing("ADE_FAILED", step_start)
            return
        except Exception as e:
            step_start = time.time()
            print(f"❌ Unexpected error during ADE extraction: {e}")
            print(f"   Marking document as 'failed' - no fallback to local parser")
            # Mark as failed and return error to frontend
            doc.extraction_status = "failed"
            db.commit()
            step_start = log_timing("ADE_ERROR", step_start)
            return

        # Use markdown for RAG indexing
        extracted_content = markdown
        content_format = "markdown"

        if not extracted_content or len(extracted_content.strip()) < 10:
            doc.extraction_status = "error"
            db.commit()
            return

        # Save extracted content (markdown)
        step_start = time.time()
        txt_path = os.path.join(EXTRACTED_DIR, f"{document_id}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(extracted_content)

        md_path = os.path.join(EXTRACTED_DIR, f"{document_id}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(extracted_content)
        step_start = log_timing("SAVE_FILES", step_start)

        extracted_text = extracted_content  # Use for classification

        # Extract holdings from structured data (if available)
        step_start = time.time()
        holdings_data = extraction_json.get("Holdings", []) if extraction_json else []

        # Extract account info for holdings
        account_number = extraction_json.get("AccountNumber", "") if extraction_json else ""
        brokerage_firm = extraction_json.get("BrokerageFirm", "") if extraction_json else ""
        account_type = extraction_json.get("AccountType", "") if extraction_json else ""

        # Store holdings in database
        print(f"   📊 Found {len(holdings_data)} holdings in extraction")
        for holding in holdings_data:
            # Schema uses capital letters (Symbol, Quantity), handle both cases
            symbol = holding.get("Symbol") or holding.get("symbol")
            quantity = holding.get("Quantity") or holding.get("quantity")

            if symbol and quantity:
                # Extract all available fields (handle both capital and lowercase)
                security_name = holding.get("SecurityName") or holding.get("securityName")
                price_per_unit = holding.get("PricePerUnit") or holding.get("pricePerUnit")
                market_value = holding.get("MarketValue") or holding.get("marketValue")
                cost_basis = holding.get("CostBasis") or holding.get("costBasis")
                gain_loss = holding.get("GainLoss") or holding.get("gainLoss")
                gain_loss_percent = holding.get("GainLossPercent") or holding.get("gainLossPercent")

                h = Holding(
                    document_id=doc.id,
                    symbol=symbol,
                    quantity=float(quantity),
                    currency=holding.get("Currency") or holding.get("currency", "USD"),
                    brokerage_firm=brokerage_firm,
                    account_number=account_number,
                    account_type=account_type,
                    # Security details
                    security_name=security_name,
                    # Price and value
                    price_per_unit=float(price_per_unit) if price_per_unit else None,
                    market_value=float(market_value) if market_value else None,
                    cost_basis=float(cost_basis) if cost_basis else None,
                    # Gain/Loss
                    gain_loss=float(gain_loss) if gain_loss else None,
                    gain_loss_percent=float(gain_loss_percent) if gain_loss_percent else None
                )
                db.add(h)

                # Enhanced logging
                log_msg = f"      ✓ {symbol}: {quantity} shares"
                if security_name:
                    log_msg += f" ({security_name})"
                if price_per_unit:
                    log_msg += f" @ ${price_per_unit}"
                print(log_msg)

        if holdings_data:
            print(f"   ✓ Stored {len(holdings_data)} holdings from {brokerage_firm or 'Unknown Firm'}")

        step_start = log_timing("STORE_HOLDINGS", step_start)

        # Classify document type
        # Priority: Use ADE's DocumentType (AI-powered, most accurate)
        # Fallback: Use keyword classifier if ADE didn't provide a type
        step_start = time.time()

        # Check if ADE already classified the document
        ade_doc_type = extraction_json.get("DocumentType") if extraction_json else None

        if ade_doc_type and ade_doc_type != "Unknown":
            # Trust ADE's classification (AI-powered, context-aware)
            doc_type = DocumentClassifier.normalize_document_type(ade_doc_type)
            print(f"   ✓ Document type from ADE: {doc_type} (original: {ade_doc_type})")
        else:
            # Fallback to keyword classifier
            doc_type = classifier.classify(extracted_text, filename)
            print(f"   ✓ Document type from keyword classifier: {doc_type}")

        step_start = log_timing("CLASSIFY", step_start)

        # Update document with type and status
        step_start = time.time()
        doc.document_type = doc_type
        doc.extraction_status = "completed"
        db.commit()
        step_start = log_timing("DB_UPDATE", step_start)

        # Auto-ingest into vector DB with better chunking
        # Use markdown-aware chunking if available (better structure preservation)
        try:
            step_start = time.time()
            print(f"\n🔄 [4/5] Chunking document...")
            if content_format == "markdown":
                chunks = _chunk_markdown(extracted_content)
            else:
                chunks = _chunk_text(extracted_content)

            # Also chunk tables if available (only if not already in markdown)
            # Only process tables if result exists (from fallback parser)
            if result is not None:
                tables = result.get("tables", [])
                if tables and content_format != "markdown":
                    for table_info in tables:
                        table = table_info.get("table", [])
                        if table:
                            table_text = _table_to_text(table)
                            table_chunks = _chunk_text(table_text)
                            chunks.extend(table_chunks)

            print(f"   ✓ Created {len(chunks)} chunks")
            step_start = log_timing("CHUNKING", step_start)

            if chunks:
                step_start = time.time()
                print(f"🚀 [5/5] Ingesting into vector store...")
                print(f"   Chunks: {len(chunks)}")
                print(f"   Avg chunk size: {sum(len(c) for c in chunks) / len(chunks):.0f} chars")

                # Extract company metadata from extraction_json for chunk metadata
                company_name = extraction_json.get("CompanyName")
                ticker_symbol = extraction_json.get("TickerSymbol")
                report_date = extraction_json.get("ReportDate")

                if company_name or ticker_symbol:
                    print(f"   Company: {company_name or 'N/A'} ({ticker_symbol or 'N/A'})")

                # Use agent for ingestion (same vector store)
                if USE_AGENT:
                    agent = PortfolioAgent(db_session=db)
                    agent.ingest_chunks(
                        chunks,
                        document_id=document_id,
                        session_id=doc.session_id,
                        document_name=doc.filename,
                        company_name=company_name,
                        ticker_symbol=ticker_symbol,
                        document_type=doc_type,
                        report_date=report_date
                    )
                else:
                    rag_service.ingest_chunks(chunks, document_id=document_id, session_id=doc.session_id)

                print(f"   ✓ Ingested successfully")
                step_start = log_timing("VECTOR_INGEST", step_start)
        except Exception as e:
            import traceback
            print(f"❌ Error ingesting chunks: {traceback.format_exc()}")

        # ========================================
        # PERFORMANCE SUMMARY
        # ========================================
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"⏱️  PERFORMANCE SUMMARY")
        print(f"{'='*60}")
        print(f"Total time: {total_time:.2f}s")
        print(f"\nBreakdown:")

        # Sort by time (slowest first)
        sorted_timings = sorted(timings.items(), key=lambda x: x[1], reverse=True)
        for step_name, elapsed in sorted_timings:
            percentage = (elapsed / total_time * 100) if total_time > 0 else 0
            bar_length = int(percentage / 2)  # Scale to 50 chars max
            bar = "█" * bar_length
            print(f"  {step_name:25s} {elapsed:6.2f}s  {percentage:5.1f}%  {bar}")

        print(f"{'='*60}\n")

        # Identify bottleneck
        if sorted_timings:
            slowest_step, slowest_time = sorted_timings[0]
            if slowest_time > 5:
                print(f"⚠️  BOTTLENECK DETECTED: {slowest_step} took {slowest_time:.2f}s")

                # Provide recommendations
                if "LANDING_AI_PARSE" in slowest_step:
                    print(f"   💡 Recommendation: Large PDF parsing is slow. Consider:")
                    print(f"      - Using async Parse Jobs API for files > 10MB")
                    print(f"      - Increasing timeout if needed")
                elif "LANDING_AI_EXTRACT" in slowest_step:
                    print(f"   💡 Recommendation: Schema extraction is slow. Consider:")
                    print(f"      - Simplifying schema (currently {len(PORTFOLIO_SCHEMA.get('properties', {}))} fields)")
                    print(f"      - Extracting only essential fields")
                elif "VECTOR_INGEST" in slowest_step:
                    print(f"   💡 Recommendation: Vector ingestion is slow. Consider:")
                    print(f"      - Reducing chunk count (currently {len(chunks) if 'chunks' in locals() else 'N/A'})")
                    print(f"      - Using batch embedding")
                print()

    except Exception as e:
        try:
            doc.extraction_status = "error"
            db.commit()
        except:
            pass
        import traceback
        print(f"❌ Fatal error: {traceback.format_exc()}")
    finally:
        db.close()


@app.post(f"{APP_PREFIX}/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db=Depends(get_db)
):
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = filename.split(".")[-1].lower()
    if ext not in ALLOWED_FILE_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    safe_name = filename.replace(" ", "_")
    import time
    import uuid
    document_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_name}"
    dest_path = os.path.join(UPLOAD_DIR, document_id)

    # Stream to disk with size check
    bytes_written = 0
    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                out.close()
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)

    # Persist document record with session_id
    doc = Document(
        document_id=document_id,
        filename=filename,
        session_id=session_id,
        extraction_status="processing"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Trigger async extraction
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, extract_and_classify, document_id, filename)

    return UploadResponse(document_id=document_id, filename=filename, extraction_status="processing")


@app.get(f"{APP_PREFIX}/documents/{{document_id}}/status")
async def get_document_status(document_id: str, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Debug logging
    print(f"📊 Status check: {doc.filename} -> {doc.extraction_status}")

    return {
        "document_id": doc.document_id,
        "filename": doc.filename,
        "document_type": doc.document_type,
        "extraction_status": doc.extraction_status
    }


@app.post(f"{APP_PREFIX}/extract/{{document_id}}", response_model=ExtractResponse)
async def extract_document(document_id: str, db=Depends(get_db)):
    src_path = os.path.join(UPLOAD_DIR, document_id)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Document not found")

    # Stub extraction: write placeholder text; later integrate ADE
    txt_path = os.path.join(EXTRACTED_DIR, f"{document_id}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Extracted placeholder text for {document_id}\n\n")
        f.write("Holdings: AAPL 10, MSFT 5\n")
        f.write("Balance Sheet: Assets 100, Liabilities 40, Equity 60\n")

    # Also persist minimal structured placeholders
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if doc:
        # Clear previous demo data
        db.query(Holding).filter(Holding.document_id == doc.id).delete()
        db.query(BalanceSheetItem).filter(BalanceSheetItem.document_id == doc.id).delete()
        # Insert placeholders
        db.add_all([
            Holding(document_id=doc.id, symbol="AAPL", quantity=10, currency="USD"),
            Holding(document_id=doc.id, symbol="MSFT", quantity=5, currency="USD"),
            BalanceSheetItem(document_id=doc.id, name="Assets", value=100, period="latest"),
            BalanceSheetItem(document_id=doc.id, name="Liabilities", value=40, period="latest"),
            BalanceSheetItem(document_id=doc.id, name="Equity", value=60, period="latest"),
        ])
        db.commit()

    return ExtractResponse(document_id=document_id, status="extracted")


@app.post(f"{APP_PREFIX}/ingest/{{document_id}}", response_model=IngestResponse)
async def ingest_document(document_id: str, db=Depends(get_db)):
    txt_path = os.path.join(EXTRACTED_DIR, f"{document_id}.txt")
    md_path = os.path.join(EXTRACTED_DIR, f"{document_id}.md")

    # Prefer markdown if available
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = _chunk_markdown(content)
    elif os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = _chunk_text(content)
    else:
        raise HTTPException(status_code=404, detail="Extracted text not found; run extract first")

    if not chunks:
        raise HTTPException(status_code=400, detail="No content to ingest")

    # Use agent for ingestion (same vector store)
    if USE_AGENT:
        agent = PortfolioAgent(db_session=db)
        count = agent.ingest_chunks(chunks, document_id=document_id)
    else:
        count = rag_service.ingest_chunks(chunks, document_id=document_id)

    return IngestResponse(document_id=document_id, chunks_indexed=count)


@app.post(f"{APP_PREFIX}/documents/{{document_id}}/re-extract", response_model=ExtractResponse)
async def re_extract_document(document_id: str):
    """Re-extract and re-ingest a document (useful if extraction failed or was placeholder)"""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Trigger re-extraction
        extract_and_classify(document_id, doc.filename)
        
        return ExtractResponse(document_id=document_id, status="re-extracted")
    finally:
        db.close()


@app.post(f"{APP_PREFIX}/chat", response_model=ChatResponse)
async def chat_rag(request: ChatRequest, db=Depends(get_db)):
    """
    Chat endpoint using Portfolio Agent with multiple tools.

    Uses PortfolioAgent (LangChain agent with RAG + SQL + API tools) by default.
    Set USE_AGENT=false in .env to use old RAGService.
    """
    # DEBUG: Log incoming request
    print(f"\n💬 [CHAT] Question: {request.question[:100]}...")
    print(f"   Session ID: {request.session_id}")

    if USE_AGENT:
        # NEW: Use portfolio agent (LLM decides which tools to use: RAG, SQL, API)
        # Create agent with database session for holdings queries
        agent = PortfolioAgent(db_session=db)
        result = agent.answer(
            request.question,
            session_id=request.session_id
        )
    else:
        # OLD: Use traditional RAG service (for backward compatibility)
        result = rag_service.answer(
            request.question,
            top_k=request.top_k,
            session_id=request.session_id
        )

    citations = [
        Citation(
            document_id=c.get("document_id", "unknown"),
            score=float(c.get("score", 0.0))
        )
        for c in result.get("citations", [])
    ]
    session_id = request.session_id or "session-1"
    return ChatResponse(answer=result.get("answer", ""), citations=citations, session_id=session_id)


# ----- Financials Endpoints -----

@app.get(f"{APP_PREFIX}/documents/{{document_id}}/holdings", response_model=List[HoldingRead])
async def list_holdings(document_id: str, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    items = db.query(Holding).filter(Holding.document_id == doc.id).all()
    return items


@app.get(f"{APP_PREFIX}/holdings/consolidated")
async def get_consolidated_holdings(db=Depends(get_db)):
    """Get consolidated holdings across all documents"""
    all_holdings = db.query(Holding).all()
    holdings_list = [
        {
            "symbol": h.symbol,
            "quantity": h.quantity,
            "currency": h.currency,
            "document_id": db.query(Document).filter(Document.id == h.document_id).first().document_id if h.document_id else "unknown"
        }
        for h in all_holdings
    ]
    consolidated = consolidator.consolidate(holdings_list)
    return consolidated


@app.post(f"{APP_PREFIX}/documents/{{document_id}}/holdings", response_model=HoldingRead)
async def add_holding(document_id: str, payload: HoldingCreate, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    holding = Holding(document_id=doc.id, symbol=payload.symbol, quantity=payload.quantity, currency=payload.currency or "USD")
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


@app.get(f"{APP_PREFIX}/documents/{{document_id}}/balance_sheet", response_model=List[FinancialItemRead])
async def list_balance_sheet(document_id: str, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    items = db.query(BalanceSheetItem).filter(BalanceSheetItem.document_id == doc.id).all()
    return items


@app.post(f"{APP_PREFIX}/documents/{{document_id}}/balance_sheet", response_model=FinancialItemRead)
async def add_balance_sheet_item(document_id: str, payload: FinancialItemCreate, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    item = BalanceSheetItem(document_id=doc.id, name=payload.name, value=payload.value, period=payload.period or "latest")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get(f"{APP_PREFIX}/documents/{{document_id}}/income_statement", response_model=List[FinancialItemRead])
async def list_income_statement(document_id: str, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    items = db.query(IncomeStatementItem).filter(IncomeStatementItem.document_id == doc.id).all()
    return items


@app.post(f"{APP_PREFIX}/documents/{{document_id}}/income_statement", response_model=FinancialItemRead)
async def add_income_statement_item(document_id: str, payload: FinancialItemCreate, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    item = IncomeStatementItem(document_id=doc.id, name=payload.name, value=payload.value, period=payload.period or "latest")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get(f"{APP_PREFIX}/documents/{{document_id}}/cash_flow", response_model=List[FinancialItemRead])
async def list_cash_flow(document_id: str, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    items = db.query(CashFlowItem).filter(CashFlowItem.document_id == doc.id).all()
    return items


@app.post(f"{APP_PREFIX}/documents/{{document_id}}/cash_flow", response_model=FinancialItemRead)
async def add_cash_flow_item(document_id: str, payload: FinancialItemCreate, db=Depends(get_db)):
    doc = db.query(Document).filter(Document.document_id == document_id).one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    item = CashFlowItem(document_id=doc.id, name=payload.name, value=payload.value, period=payload.period or "latest")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
