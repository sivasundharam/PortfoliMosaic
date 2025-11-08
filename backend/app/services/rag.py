from typing import List, Dict, Any
import os
from .embeddings import Embeddings
from .vector_store import VectorStore
from .stock_price import StockPriceTool

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class RAGService:
    def __init__(self):
        self.embedding = Embeddings()
        self.vector_store = VectorStore(index_dir=os.getenv("VECTOR_DIR", "data/vector_index"))
        self.stock_tool = StockPriceTool()
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

        # Initialize LangChain LLMs with low temperature for deterministic responses
        self.llm = None
        if self.openai_key:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.5,  # Set to 0 for maximum determinism
                model_kwargs={"seed": 42},  # Use seed for reproducibility
                api_key=self.openai_key
            )

    def ingest_chunks(self, chunks: List[str], document_id: str = "unknown", session_id: str = None) -> int:
        if not chunks:
            return 0
        vectors = self.embedding.embed(chunks)
        chunks_metadata = [
            {
                "document_id": document_id,
                "session_id": session_id,
                "chunk_id": str(i),
                "content": chunk,
                "text_preview": chunk[:200] + "..." if len(chunk) > 200 else chunk
            }
            for i, chunk in enumerate(chunks)
        ]
        self.vector_store.add(vectors, chunks_metadata)
        return len(chunks)

    def _call_llm(self, context: str, question: str) -> str:
        """Call LLM to generate markdown-formatted responses"""
        if not self.llm:
            # Fallback: simple template-based response
            return f"Based on the provided documents: {context[:500]}...\n\nThe answer to '{question}' would be found in the extracted documents above."

        try:
            # Prompt LLM to generate clean markdown tables
            system_message = SystemMessage(
                content="""You are an intelligent financial assistant with access to real-time stock price data.

TOOLS AVAILABLE:
- Stock Price Tool: Can fetch current stock prices for any ticker symbol (e.g., AAPL, MSFT, GOOGL)

When reporting holdings, balance sheets, income statements, or cash flows, format your answer EXACTLY as valid markdown with tables.

FORMATTING RULES:
1. Use markdown tables with proper syntax: | Column | Column |
2. Right-align all numbers
3. Show 2 decimal places for currency values
4. Use commas for thousands (e.g., $1,234.56)
5. Use **bold** for section headers
6. Add a brief summary sentence after tables

STOCK PRICE QUERIES:
- If asked about current stock prices, respond with: "TOOL_CALL: GET_STOCK_PRICE [SYMBOL]"
- Common company to ticker mappings:
  - Apple = AAPL
  - Microsoft = MSFT
  - Google/Alphabet = GOOGL
  - Amazon = AMZN
  - Tesla = TSLA
  - Meta/Facebook = META
  - Netflix = NFLX
  - AT&T = T
  - Comcast = CMCSA

EXAMPLE for holdings:

**Holdings Summary** (as of April 30, 2011)

| Security Name | Symbol | Quantity | Price per Unit | Total Value |
|--------------|--------|----------|----------------|-------------|
| AT&T Inc. | T | 9.00 | $31.12 | $280.08 |
| Comcast Corp New Cl A | CMCSA | 28.00 | $26.21 | $733.88 |

**Total Portfolio Value:** $1,013.96

The portfolio includes 2 holdings as of April 30, 2011.

EXAMPLE for balance sheet:

**Balance Sheet** (as of December 31, 2023)

| Category | Amount |
|----------|--------|
| **ASSETS** | |
| Current Assets | $5,000,000.00 |
| Fixed Assets | $3,000,000.00 |
| **Total Assets** | **$8,000,000.00** |
| | |
| **LIABILITIES** | |
| Current Liabilities | $2,000,000.00 |
| Long-term Debt | $1,500,000.00 |
| **Total Liabilities** | **$3,500,000.00** |
| | |
| **EQUITY** | **$4,500,000.00** |

The company shows a healthy balance sheet with total assets of $8M.

For narrative questions (summaries, explanations), use clear paragraphs with markdown formatting.

Output ONLY markdown content. Be concise and professional."""
            )

            user_message = HumanMessage(
                content=f"""CONTEXT FROM DOCUMENTS:
{context}

USER QUESTION: {question}

Provide your answer in clean markdown format with tables where appropriate:"""
            )

            # Call LLM with LangChain
            response = self.llm.invoke([system_message, user_message])

            # Extract content from response
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)

        except Exception as e:
            return f"Error calling LLM: {str(e)}"

    def _is_placeholder_content(self, content: str) -> bool:
        """Check if content is placeholder/generic text"""
        placeholder_keywords = [
            "sample content",
            "extracted text from pdf",
            "placeholder",
            "balance information",
            "holdings, transactions"  # from old extraction
        ]
        content_lower = content.lower()
        # If content is very short or contains placeholder keywords, it's likely placeholder
        if len(content.strip()) < 50:
            return True
        if any(keyword in content_lower for keyword in placeholder_keywords):
            # But allow if there's also real content (length check)
            if len(content.strip()) < 200:
                return True
        return False

    def answer(self, question: str, top_k: int = 4, session_id: str = None) -> Dict[str, Any]:
        """Answer a question using RAG - following mna-agent pattern"""
        q_vec = self.embedding.embed([question])
        scores, ids = self.vector_store.search(q_vec, k=top_k, session_id=session_id)

        # Get actual chunk content
        chunks = self.vector_store.get_chunks_by_ids(ids)

        # Build context from retrieved chunks and track document sources
        context_parts = []
        document_sources = {}  # Track unique documents with their best score

        for chunk, score in zip(chunks, scores[0]):
            if chunk and chunk.get("content"):
                content = chunk.get("content", "").strip()
                document_id = chunk.get("document_id", "unknown")

                # Filter out placeholder content
                if content and not self._is_placeholder_content(content):
                    context_parts.append(content)

                    # Track document-level citations (keep best score per document)
                    if document_id not in document_sources:
                        document_sources[document_id] = float(score)
                    else:
                        # Keep the highest score for this document
                        document_sources[document_id] = max(document_sources[document_id], float(score))
                elif content:
                    # Log placeholder content for debugging
                    print(f"Filtered placeholder chunk from {document_id}: {content[:100]}...")

        context = "\n\n".join(context_parts)

        # If no context found, return early with helpful message
        if not context or len(context.strip()) < 10:
            return {
                "answer": "I couldn't find relevant information in your uploaded documents to answer this question. The documents may need to be re-extracted. Please try uploading them again or contact support.",
                "citations": []
            }

        # Convert document sources to citation format (document-level only)
        citations = [
            {
                "document_id": doc_id,
                "score": score
            }
            for doc_id, score in sorted(document_sources.items(), key=lambda x: x[1], reverse=True)
        ]

        # Call LLM with context
        answer = self._call_llm(context, question)

        # Check if LLM requested a tool call
        if "TOOL_CALL: GET_STOCK_PRICE" in answer:
            import re
            # Extract symbol from tool call
            match = re.search(r'TOOL_CALL: GET_STOCK_PRICE\s+\[?([A-Z]+)\]?', answer)
            if match:
                symbol = match.group(1)
                price_data = self.stock_tool.get_price(symbol)

                if "error" not in price_data:
                    # Replace tool call with actual price data
                    price_info = f"""**Current Stock Price for {symbol}**

| Metric | Value |
|--------|-------|
| Symbol | {symbol} |
| Current Price | ${price_data.get('price', 'N/A')} |
| Change | {price_data.get('change', 'N/A')} |
| Change % | {price_data.get('change_percent', 'N/A')} |
| Volume | {price_data.get('volume', 'N/A'):,} |

Data retrieved in real-time from Yahoo Finance."""
                    answer = answer.replace(match.group(0), price_info)
                else:
                    answer = answer.replace(match.group(0), f"Unable to fetch stock price for {symbol}: {price_data.get('error', 'Unknown error')}")

        # Fallback: If question is about stock price but LLM didn't call tool
        elif any(kw in question.lower() for kw in ["stock price", "price of", "current price", "quote for"]):
            # Try to extract company name or symbol
            import re

            # Common company name to ticker mapping
            company_to_ticker = {
                "apple": "AAPL",
                "microsoft": "MSFT",
                "google": "GOOGL",
                "alphabet": "GOOGL",
                "amazon": "AMZN",
                "tesla": "TSLA",
                "meta": "META",
                "facebook": "META",
                "netflix": "NFLX",
                "at&t": "T",
                "att": "T",
                "comcast": "CMCSA",
            }

            # Check for company names
            question_lower = question.lower()
            symbol = None
            for company, ticker in company_to_ticker.items():
                if company in question_lower:
                    symbol = ticker
                    break

            # If no company name found, try to extract ticker symbol
            if not symbol:
                symbols = re.findall(r'\b[A-Z]{1,5}\b', question.upper())
                if symbols:
                    symbol = symbols[0]

            # Fetch price if symbol found
            if symbol:
                price_data = self.stock_tool.get_price(symbol)
                if "error" not in price_data:
                    price_info = f"""

**Current Stock Price for {symbol}**

| Metric | Value |
|--------|-------|
| Symbol | {symbol} |
| Current Price | ${price_data.get('price', 'N/A')} |
| Change | {price_data.get('change', 'N/A')} |
| Change % | {price_data.get('change_percent', 'N/A')} |
| Volume | {price_data.get('volume', 'N/A'):,} |

Data retrieved in real-time from Yahoo Finance."""
                    answer += price_info

        return {
            "answer": answer,
            "citations": citations,
        }
