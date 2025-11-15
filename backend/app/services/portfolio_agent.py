"""
Portfolio Agent using LangChain 1.0 create_agent Pattern

This is a domain-specific agent for portfolio management and financial analysis.
The LLM acts as the brain that decides which tools to use based on user questions.

Tools Available:
1. search_documents - RAG retrieval from uploaded documents (Vector DB)
2. get_stock_price - Real-time stock price lookup (API)
3. query_holdings_and_accounts - Structured holdings data (SQL)
4. check_specific_holding - Specific stock lookup (SQL)

Architecture: LLM + Multiple Tools (RAG is just ONE tool, not the whole system)
"""

from typing import List, Dict, Any, Optional
import os
from langchain.tools import tool
from langchain.agents import create_agent
from sqlalchemy.orm import Session

from .embeddings import Embeddings
from .vector_store import VectorStore
from .stock_price import StockPriceTool


class PortfolioAgent:
    """
    Portfolio Assistant Agent with multiple tools for financial analysis.

    This agent orchestrates multiple data sources:
    - Vector DB (FAISS): For semantic search of document content (RAG)
    - SQL Database: For structured holdings and account data
    - External APIs: For real-time stock prices

    Architecture:
    - LLM is the brain that receives questions and decides which tools to use
    - Tools are specialized executors (RAG, SQL, API calls)
    - LLM combines information from multiple tools and generates final answer

    Why "PortfolioAgent" not "RAGAgent"?
    - RAG is only 1 out of 4 tools (25% of functionality)
    - Agent is domain-specific (portfolio management)
    - Name reflects purpose, not implementation detail
    """
    
    def __init__(self, db_session: Optional[Session] = None):
        self.embedding = Embeddings()
        self.vector_store = VectorStore(index_dir=os.getenv("VECTOR_DIR", "data/vector_index"))
        self.stock_tool_service = StockPriceTool()
        self.db_session = db_session  # Database session for querying holdings

        # Determine which model to use
        self.openai_key = os.getenv("OPENAI_API_KEY", "")

        if self.openai_key:
            self.model_string = "openai:gpt-4o-mini"
        else:
            raise ValueError("OPENAI_API_KEY must be set")
    
    def _create_rag_retrieval_tool(self, session_id: Optional[str] = None):
        """Create a tool that retrieves relevant document chunks."""
        
        @tool
        def search_documents(query: str) -> str:
            """Search uploaded financial documents for relevant information.
            
            CRITICAL: This is the PRIMARY source of truth for all portfolio data.
            ALWAYS use this tool when asked about:
            - Holdings, securities, assets
            - Balance sheets, income statements, cash flows
            - Transactions, trades, account activity
            - Portfolio performance, valuations
            - Any data from uploaded documents
            
            DO NOT answer questions about uploaded documents without using this tool.
            DO NOT make up or hallucinate document data.
            
            Args:
                query: The search query
            
            Returns:
                Relevant document chunks with relevance scores, or "No relevant documents found"
            """
            try:
                # DEBUG: Log search parameters
                print(f"\n🔍 [search_documents] Query: {query[:100]}...")
                print(f"   Session ID: {session_id}")

                # Embed query
                q_vec = self.embedding.embed([query])

                # Search vector store (session-filtered)
                scores, ids = self.vector_store.search(q_vec, k=4, session_id=session_id)

                # DEBUG: Log search results
                print(f"   Found {len(ids[0]) if len(ids) > 0 else 0} chunks")
                if len(scores) > 0 and len(scores[0]) > 0:
                    print(f"   Top score: {scores[0][0]:.4f}")

                # Get chunks
                chunks = self.vector_store.get_chunks_by_ids(ids)

                # Format results
                results = []
                for chunk, score in zip(chunks, scores[0]):
                    if chunk and chunk.get("content"):
                        content = chunk.get("content", "").strip()
                        if len(content) > 50:  # Skip very short chunks
                            # Extract metadata
                            doc_name = chunk.get("document_name") or "Unknown"
                            company_name = chunk.get("company_name")
                            ticker_symbol = chunk.get("ticker_symbol")
                            document_type = chunk.get("document_type")
                            report_date = chunk.get("report_date")

                            # Build metadata header
                            metadata_parts = [f"Document: {doc_name}"]

                            if company_name or ticker_symbol:
                                company_info = company_name or "Unknown Company"
                                if ticker_symbol:
                                    company_info += f" ({ticker_symbol})"
                                metadata_parts.append(f"Company: {company_info}")

                            if document_type:
                                metadata_parts.append(f"Type: {document_type}")

                            if report_date:
                                metadata_parts.append(f"Date: {report_date}")

                            metadata_parts.append(f"Relevance: {score:.2f}")

                            metadata_header = " | ".join(metadata_parts)

                            results.append(
                                f"[{metadata_header}]\n{content}"
                            )

                # DEBUG: Log results
                print(f"   Returning {len(results)} results to LLM")

                if not results:
                    return "No relevant documents found. Please ask the user to upload financial documents."

                return "\n\n---\n\n".join(results)
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
                return f"Error searching documents: {str(e)}"
        
        return search_documents
    
    def _create_stock_price_tool(self):
        """Create a tool that fetches current stock prices"""
        
        @tool
        def get_stock_price(symbol: str) -> str:
            """Get current/real-time stock price for a ticker symbol.
            
            Use this tool ONLY for current market prices.
            DO NOT make up stock prices.
            
            Args:
                symbol: Stock ticker symbol (e.g., 'AAPL', 'GOOGL') or company name
            
            Returns:
                Current stock price data or error message
            """
            try:
                # Map common company names to tickers
                company_to_ticker = {
                    "apple": "AAPL",
                    "google": "GOOGL",
                    "microsoft": "MSFT",
                    "amazon": "AMZN",
                    "tesla": "TSLA",
                    "meta": "META",
                    "facebook": "META",
                    "nvidia": "NVDA",
                    "netflix": "NFLX"
                }
                
                symbol_lower = symbol.lower().strip()
                ticker = company_to_ticker.get(symbol_lower, symbol.upper())
                
                # Get price data
                price_data = self.stock_tool_service.get_price(ticker)
                
                if "error" in price_data:
                    return f"Error: {price_data['error']}"
                
                # Format result
                return f"""Stock: {ticker}
Current Price: ${price_data.get('price', 'N/A')}
Change: {price_data.get('change', 'N/A')}
Change %: {price_data.get('change_percent', 'N/A')}
Volume: {price_data.get('volume', 'N/A')}
Last Updated: {price_data.get('timestamp', 'N/A')}"""
            except Exception as e:
                return f"Error fetching stock price: {str(e)}"
        
        return get_stock_price

    def _create_holdings_query_tool(self, session_id: Optional[str] = None):
        """Create a tool that queries holdings and account information from database"""

        @tool
        def query_holdings_and_accounts(query_type: str) -> str:
            """Query holdings and account information from the database.

            Use this tool to answer questions about:
            - How many accounts the user has
            - Which brokerage firms the user uses
            - List of all holdings across all accounts
            - Holdings grouped by brokerage firm
            - Account types (Individual, IRA, 401k, etc.)

            Args:
                query_type: Type of query - one of:
                    - "count_accounts": Count number of unique accounts
                    - "list_brokerages": List all brokerage firms
                    - "list_holdings": List all holdings with brokerage info
                    - "holdings_by_brokerage": Group holdings by brokerage firm

            Returns:
                Formatted information about holdings and accounts
            """
            if not self.db_session:
                return "Database not available. Cannot query holdings."

            try:
                from ..models import Holding, Document

                # DEBUG: Log session filtering
                print(f"\n📊 [query_holdings_and_accounts] Query type: {query_type}")
                print(f"   Session ID: {session_id}")

                if query_type == "count_accounts":
                    # Count unique accounts (session-filtered)
                    # SECURITY: Require session_id to prevent data leaks
                    if not session_id:
                        return "Error: session_id is required for security. Cannot query holdings without session isolation."

                    accounts_query = self.db_session.query(
                        Holding.brokerage_firm,
                        Holding.account_number,
                        Holding.account_type
                    ).join(Document, Holding.document_id == Document.id).filter(
                        Holding.brokerage_firm.isnot(None),
                        Document.session_id == session_id  # Always filter by session
                    )

                    accounts = accounts_query.distinct().all()

                    count = len(accounts)
                    print(f"   Found {count} account(s)")

                    if count == 0:
                        return "No account information found in uploaded documents for this session."

                    result = f"You have {count} account(s):\n\n"
                    for firm, acc_num, acc_type in accounts:
                        result += f"- {firm or 'Unknown Firm'}"
                        if acc_num:
                            result += f" (Account: {acc_num})"
                        if acc_type:
                            result += f" - {acc_type}"
                        result += "\n"
                    return result

                elif query_type == "list_brokerages":
                    # List unique brokerage firms (session-filtered)
                    # SECURITY: Require session_id to prevent data leaks
                    if not session_id:
                        return "Error: session_id is required for security. Cannot query holdings without session isolation."

                    firms_query = self.db_session.query(Holding.brokerage_firm).join(
                        Document, Holding.document_id == Document.id
                    ).filter(
                        Holding.brokerage_firm.isnot(None),
                        Document.session_id == session_id  # Always filter by session
                    )

                    firms = firms_query.distinct().all()

                    firm_list = [f[0] for f in firms if f[0]]
                    print(f"   Found {len(firm_list)} brokerage(s)")

                    if not firm_list:
                        return "No brokerage firm information found in uploaded documents for this session."

                    return f"You have accounts with {len(firm_list)} brokerage firm(s):\n" + "\n".join(f"- {f}" for f in firm_list)

                elif query_type == "list_holdings":
                    # List all holdings with complete information (session-filtered)
                    # SECURITY: Require session_id to prevent data leaks
                    if not session_id:
                        return "Error: session_id is required for security. Cannot query holdings without session isolation."

                    holdings_query = self.db_session.query(Holding).join(
                        Document, Holding.document_id == Document.id
                    ).filter(
                        Document.session_id == session_id  # Always filter by session
                    )

                    holdings = holdings_query.all()

                    print(f"   Found {len(holdings)} holding(s)")

                    if not holdings:
                        return "No holdings found in uploaded documents for this session."

                    result = f"You have {len(holdings)} holding(s):\n\n"
                    for h in holdings:
                        # Basic info
                        line = f"- **{h.symbol}**"
                        if h.security_name:
                            line += f" ({h.security_name})"
                        line += f": {h.quantity} shares"

                        # Price info
                        if h.price_per_unit:
                            line += f" @ ${h.price_per_unit:.2f}"
                        if h.market_value:
                            line += f" = ${h.market_value:,.2f}"

                        # Cost basis and gain/loss
                        if h.cost_basis:
                            line += f" | Cost Basis: ${h.cost_basis:,.2f}"
                        if h.gain_loss is not None:
                            sign = "+" if h.gain_loss >= 0 else ""
                            line += f" | Gain/Loss: {sign}${h.gain_loss:,.2f}"
                        if h.gain_loss_percent is not None:
                            sign = "+" if h.gain_loss_percent >= 0 else ""
                            line += f" ({sign}{h.gain_loss_percent:.2f}%)"

                        # Account info
                        if h.brokerage_firm:
                            line += f" | {h.brokerage_firm}"
                        if h.account_type:
                            line += f" ({h.account_type})"

                        result += line + "\n"
                    return result

                elif query_type == "holdings_by_brokerage":
                    # Group holdings by brokerage firm (session-filtered)
                    # SECURITY: Require session_id to prevent data leaks
                    if not session_id:
                        return "Error: session_id is required for security. Cannot query holdings without session isolation."

                    holdings_query = self.db_session.query(Holding).join(
                        Document, Holding.document_id == Document.id
                    ).filter(
                        Document.session_id == session_id  # Always filter by session
                    )

                    holdings = holdings_query.all()

                    print(f"   Found {len(holdings)} holding(s) for grouping")

                    if not holdings:
                        return "No holdings found in uploaded documents for this session."

                    # Group by brokerage
                    by_brokerage = {}
                    for h in holdings:
                        firm = h.brokerage_firm or "Unknown Firm"
                        if firm not in by_brokerage:
                            by_brokerage[firm] = []
                        by_brokerage[firm].append(h)

                    result = "Holdings by brokerage firm:\n\n"
                    for firm, holdings_list in by_brokerage.items():
                        result += f"**{firm}**:\n"
                        for h in holdings_list:
                            line = f"  - **{h.symbol}**"
                            if h.security_name:
                                line += f" ({h.security_name})"
                            line += f": {h.quantity} shares"

                            # Price info
                            if h.price_per_unit:
                                line += f" @ ${h.price_per_unit:.2f}"
                            if h.market_value:
                                line += f" = ${h.market_value:,.2f}"

                            # Gain/Loss
                            if h.gain_loss is not None:
                                sign = "+" if h.gain_loss >= 0 else ""
                                line += f" | {sign}${h.gain_loss:,.2f}"
                                if h.gain_loss_percent is not None:
                                    sign = "+" if h.gain_loss_percent >= 0 else ""
                                    line += f" ({sign}{h.gain_loss_percent:.2f}%)"

                            # Account type
                            if h.account_type:
                                line += f" | {h.account_type}"

                            result += line + "\n"
                        result += "\n"
                    return result

                else:
                    return f"Unknown query_type: {query_type}. Use one of: count_accounts, list_brokerages, list_holdings, holdings_by_brokerage"

            except Exception as e:
                return f"Error querying holdings: {str(e)}"

        return query_holdings_and_accounts

    def _create_check_holding_tool(self, session_id: Optional[str] = None):
        """Create a tool that checks if a specific holding exists"""

        @tool
        def check_specific_holding(symbol: str) -> str:
            """Check if user owns a specific stock/security by symbol.

            Use this tool for questions like:
            - "Do I have Apple shares?" → symbol="AAPL"
            - "Do I own Tesla stock?" → symbol="TSLA"
            - "How many Microsoft shares do I have?" → symbol="MSFT"

            This tool returns ONLY information about the requested symbol.
            It does NOT return the entire holdings list.

            Args:
                symbol: Stock ticker symbol (e.g., 'AAPL', 'TSLA', 'MSFT')

            Returns:
                Information about the specific holding, or "No" if not found
            """
            if not self.db_session:
                return "Database not available. Cannot query holdings."

            try:
                from ..models import Holding, Document

                # Normalize symbol to uppercase
                symbol = symbol.upper().strip()

                # DEBUG: Log lookup
                print(f"\n🔍 [check_specific_holding] Symbol: {symbol}")
                print(f"   Session ID: {session_id}")

                # SECURITY: Require session_id to prevent data leaks
                if not session_id:
                    return "Error: session_id is required for security. Cannot query holdings without session isolation."

                # Query for specific symbol (session-filtered)
                holdings_query = self.db_session.query(Holding).join(
                    Document, Holding.document_id == Document.id
                ).filter(
                    Holding.symbol == symbol,
                    Document.session_id == session_id  # Always filter by session
                )

                holdings = holdings_query.all()

                if not holdings:
                    return f"No, you do not have any {symbol} shares in your portfolio."

                # Format holdings for this symbol
                result = f"Yes, you have {symbol} shares:\n\n"

                total_quantity = 0
                total_value = 0

                for h in holdings:
                    total_quantity += h.quantity

                    line = f"- {h.quantity} shares"

                    if h.security_name:
                        line += f" of {h.security_name}"

                    if h.price_per_unit:
                        value = h.quantity * h.price_per_unit
                        total_value += value
                        line += f" @ ${h.price_per_unit:.2f} = ${value:,.2f}"

                    if h.brokerage_firm:
                        line += f" (held at {h.brokerage_firm}"
                        if h.account_type:
                            line += f", {h.account_type}"
                        line += ")"

                    if h.gain_loss is not None:
                        sign = "+" if h.gain_loss >= 0 else ""
                        line += f" | Gain/Loss: {sign}${h.gain_loss:,.2f}"
                        if h.gain_loss_percent is not None:
                            line += f" ({sign}{h.gain_loss_percent:.2f}%)"

                    result += line + "\n"

                # Add summary if multiple holdings
                if len(holdings) > 1:
                    result += f"\nTotal: {total_quantity} shares"
                    if total_value > 0:
                        result += f", ${total_value:,.2f} total value"

                return result

            except Exception as e:
                return f"Error checking holding: {str(e)}"

        return check_specific_holding

    def _create_agent(self, session_id: Optional[str] = None):
        """Create LangChain agent with tools using create_agent"""

        # Create tools
        rag_tool = self._create_rag_retrieval_tool(session_id)
        stock_tool = self._create_stock_price_tool()
        holdings_tool = self._create_holdings_query_tool(session_id)
        check_holding_tool = self._create_check_holding_tool(session_id)
        tools = [rag_tool, stock_tool, holdings_tool, check_holding_tool]
        
        # System prompt
        system_prompt = """You are a specialized financial portfolio assistant. You help users analyze and understand their investment portfolios.

WHAT YOU CAN HELP WITH:
1. Portfolio holdings and positions
2. Brokerage accounts and account information
3. Performance analysis (gains, losses, returns)
4. Tax implications (cost basis, capital gains, tax-loss harvesting)
5. Stock prices and market data
6. Balance sheets, income statements, financial documents
7. Portfolio optimization and diversification
8. Risk analysis and asset allocation

WHAT YOU CANNOT HELP WITH:
- General knowledge questions (history, science, weather, etc.)
- Non-financial topics (cooking, sports, entertainment, etc.)
- Questions unrelated to investing or portfolio management

AVAILABLE TOOLS:
1. **check_specific_holding**: Check if user owns a specific stock by symbol
   - Use for: "Do I have Apple shares?", "How many Tesla shares do I own?", "Do I own Microsoft?"
   - Returns: ONLY information about the requested symbol (NOT the entire holdings list)
   - This is the PREFERRED tool for specific holding lookups

2. **query_holdings_and_accounts**: Query structured holdings data from database
   - Use for: "list ALL holdings", "how many accounts", "which brokerages", "show holdings by firm"
   - Returns: Complete holding information including symbols, quantities, prices, gains/losses, brokerage info
   - WARNING: Only use this when user asks for ALL holdings or summary data

3. **search_documents**: Search uploaded financial documents
   - Use for: Detailed questions about specific documents, transactions, statements
   - Returns: Relevant text chunks from uploaded PDFs

4. **get_stock_price**: Get current stock prices
   - Use for: "What is AAPL stock price?", "Current price of Tesla"
   - Returns: Real-time price data

WHEN TO USE EACH TOOL:

**For Specific Holding Lookups** (use check_specific_holding - PREFERRED):
- "Do I have Apple shares?" → check_specific_holding(symbol="AAPL")
- "How many Tesla shares do I own?" → check_specific_holding(symbol="TSLA")
- "Do I own Microsoft stock?" → check_specific_holding(symbol="MSFT")
- "Show me my Amazon holdings" → check_specific_holding(symbol="AMZN")
- IMPORTANT: This returns ONLY the requested symbol, NOT the entire holdings list
- If the holding doesn't exist, it returns "No, you do not have [SYMBOL] shares"

**For ALL Holdings or Summary Data** (use query_holdings_and_accounts):
- "How many accounts?" → query_type="count_accounts"
- "Which brokerages?" → query_type="list_brokerages"
- "What are ALL my holdings?" → query_type="list_holdings"
- "Show ALL holdings by brokerage" → query_type="holdings_by_brokerage"
- "Which holdings are profitable?" → query_type="list_holdings" then analyze gain_loss
- "Best holdings for tax?" → query_type="list_holdings" then analyze cost_basis and gain_loss
- WARNING: Only use this when user explicitly asks for ALL holdings or needs summary across all positions

**For Document Content Questions** (ALWAYS use search_documents):

INTENT-BASED RULES (Focus on what user wants to know):
1. **"Information about" / "Details about" / "Tell me about"** → search_documents
   - "Show me information about my retirement accounts" → search_documents
   - "Tell me about my brokerage fees" → search_documents
   - "Give me details about my transactions" → search_documents

2. **"What does [document] say"** → search_documents
   - "What does my statement say about fees?" → search_documents
   - "What's in my 1099-B?" → search_documents
   - "What does my balance sheet say?" → search_documents

3. **Questions about document content (not just structure)** → search_documents
   - "What fees did I pay?" → search_documents (fees are in document text)
   - "Show me dividend payments" → search_documents (dividend details in documents)
   - "What transactions happened last month?" → search_documents (transaction details in documents)
   - "Which accounts have dividend reinvestment?" → search_documents (settings in documents)
   - "What are the account details?" → search_documents (details in documents)
   - "Show me my retirement account information" → search_documents (info in documents)

4. **Specific document types mentioned** → search_documents
   - ANY question mentioning: 1099-B, 1099-DIV, statements, confirmations, balance sheets, income statements, etc.

5. **Financial statement questions** → search_documents
   - "What is the total assets?" → search_documents (balance sheet data)
   - "What are the liabilities?" → search_documents (balance sheet data)
   - "What is the revenue?" → search_documents (income statement data)
   - "Show me cash flow" → search_documents (cash flow statement data)
   - "What is the equity?" → search_documents (balance sheet data)
   - "Total value of assets" → search_documents (balance sheet data)
   - ANY question about: assets, liabilities, equity, revenue, expenses, cash flow, net income

KEYWORD-BASED RULES (When to use search_documents):
- User says: "information about", "details about", "tell me about", "show me about"
- User says: "what does [document] say", "according to", "mentioned in"
- User asks about: fees, transactions, dividends, interest, margin, warnings, alerts
- User mentions: statement, 1099, tax form, confirmation, report, balance sheet
- User asks about: assets, liabilities, equity, revenue, expenses, cash flow, net income, total value

**For Stock Prices** (use get_stock_price):
- "Current price of AAPL?" → get_stock_price

**CRITICAL DECISION TREE**:

Question contains "information about" or "details about" or "tell me about"?
  → YES: Use search_documents (user wants document content, not just structured data)
  → NO: Continue to next check

Question asks about financial statement items (assets, liabilities, equity, revenue, expenses, cash flow)?
  → YES: Use search_documents (balance sheet/income statement/cash flow data)
  → NO: Continue to next check

Question asks about document content (fees, transactions, dividends, interest)?
  → YES: Use search_documents (this data is in document text)
  → NO: Continue to next check

Question mentions specific document type (1099, statement, confirmation, balance sheet)?
  → YES: Use search_documents
  → NO: Continue to next check

Question asks for specific stock symbol?
  → YES: Use check_specific_holding
  → NO: Continue to next check

Question asks to "list ALL" or "show ALL" holdings?
  → YES: Use query_holdings_and_accounts
  → NO: Default to search_documents (safer to search than assume)

EXAMPLES TO CLARIFY TOOL SELECTION:

❌ WRONG: "show me information about my retirement accounts" → query_holdings_and_accounts
✅ CORRECT: "show me information about my retirement accounts" → search_documents
   WHY: "information about" = user wants document content, not just list of holdings

❌ WRONG: "what fees did I pay?" → query_holdings_and_accounts
✅ CORRECT: "what fees did I pay?" → search_documents
   WHY: Fee details are in document text, not in structured holdings table

❌ WRONG: "tell me about my brokerage account" → query_holdings_and_accounts
✅ CORRECT: "tell me about my brokerage account" → search_documents
   WHY: "tell me about" = user wants details from documents

✅ CORRECT: "list all my holdings" → query_holdings_and_accounts
   WHY: "list all" = user wants structured data from SQL

✅ CORRECT: "do I have Apple shares?" → check_specific_holding(symbol="AAPL")
   WHY: Specific stock symbol mentioned

✅ CORRECT: "how many accounts do I have?" → query_holdings_and_accounts(query_type="count_accounts")
   WHY: Simple count, not asking for document content

✅ CORRECT: "What is the total value of assets?" → search_documents
   WHY: Balance sheet question - data is in uploaded documents

✅ CORRECT: "What are the total assets on the balance sheet?" → search_documents
   WHY: Explicitly asking about balance sheet data

✅ CORRECT: "Show me the liabilities" → search_documents
   WHY: Balance sheet item - data is in documents

✅ CORRECT: "What is Apple's revenue?" → search_documents
   WHY: Income statement question - data is in uploaded documents

ANALYSIS CAPABILITIES:
When analyzing holdings data, you can:
- Sort by gain/loss to find best/worst performers
- Identify tax-loss harvesting opportunities (holdings with losses)
- Calculate total portfolio value
- Show performance by brokerage firm
- Identify long-term vs short-term holdings (if date info available)
- Highlight high-performing securities

FORMATTING RULES:
1. Use markdown tables for structured data
2. Use **bold** for section headers and important values
3. Show 2 decimal places for currency ($1,234.56)
4. Use +/- signs for gains/losses (+$500.00 or -$200.00)
5. Show percentages with 2 decimals (+15.50% or -8.25%)
6. Add summary insights after data tables

CRITICAL RULES:
- ALWAYS use tools - NEVER make up data
- ONLY use information from uploaded documents or tools
- DO NOT hallucinate holdings, prices, or account information
- If no data is available, say so clearly
- If question is off-topic (non-finance), respond: "I'm a specialized portfolio assistant and can only help with financial portfolio questions. Please ask about your holdings, balance sheets, stock prices, or other portfolio-related topics."
- If no documents found, ask user to upload
- Be concise and professional
- Cite sources (document names, dates)"""
        
        # Create agent using LangChain 1.0 API
        agent_graph = create_agent(
            model=self.model_string,
            tools=tools,
            system_prompt=system_prompt
        )
        
        return agent_graph
    
    def ingest_chunks(
        self,
        chunks: List[str],
        document_id: str,
        session_id: Optional[str] = None,
        document_name: Optional[str] = None,
        company_name: Optional[str] = None,
        ticker_symbol: Optional[str] = None,
        document_type: Optional[str] = None,
        report_date: Optional[str] = None
    ) -> int:
        """
        Ingest document chunks into the vector store.

        Args:
            chunks: List of text chunks to ingest
            document_id: Document identifier
            session_id: Optional session ID for isolation
            document_name: Optional document filename for metadata
            company_name: Optional company name from extraction
            ticker_symbol: Optional ticker symbol from extraction
            document_type: Optional document type (Balance Sheet, etc.)
            report_date: Optional report date from extraction

        Returns:
            Number of chunks ingested
        """
        import time

        if not chunks:
            return 0

        # Embed chunks
        step_start = time.time()
        embeddings = self.embedding.embed(chunks)
        embed_time = time.time() - step_start
        print(f"      ⏱️  Embedding: {embed_time:.2f}s ({len(chunks)} chunks)")

        # Create metadata list with content included
        # VectorStore.add() expects: add(vectors, chunks_metadata)
        # where chunks_metadata contains both metadata AND content
        step_start = time.time()
        chunks_metadata = [
            {
                "document_id": document_id,
                "document_name": document_name,  # Add document filename
                "session_id": session_id,
                "chunk_id": str(i),
                "content": chunk,
                "text_preview": chunk[:200] + "..." if len(chunk) > 200 else chunk,
                # Company identification metadata
                "company_name": company_name,
                "ticker_symbol": ticker_symbol,
                "document_type": document_type,
                "report_date": report_date
            }
            for i, chunk in enumerate(chunks)
        ]
        metadata_time = time.time() - step_start
        print(f"      ⏱️  Metadata prep: {metadata_time:.2f}s")

        # Add to vector store (2 arguments: vectors and metadata)
        step_start = time.time()
        self.vector_store.add(embeddings, chunks_metadata)
        store_time = time.time() - step_start
        print(f"      ⏱️  Vector store add: {store_time:.2f}s")

        total_time = embed_time + metadata_time + store_time
        print(f"      ⏱️  Total ingest: {total_time:.2f}s")

        return len(chunks)

    def answer(self, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Answer a question using the agent.

        Args:
            question: User's question
            session_id: Optional session ID for filtering documents

        Returns:
            Dict with 'answer' and 'citations' keys
        """
        try:
            # Create agent (session-specific)
            agent = self._create_agent(session_id)

            # Invoke agent with the question
            # LangChain 1.0 agents use messages format
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})

            # Extract the final answer from the messages
            messages = result.get("messages", [])
            if messages:
                # Get the last AI message
                for msg in reversed(messages):
                    if hasattr(msg, 'content') and msg.content:
                        answer = msg.content
                        break
                else:
                    answer = "I couldn't generate an answer."
            else:
                answer = "I couldn't generate an answer."

            # Extract citations (simplified - just document level)
            citations = []
            # In LangChain 1.0, tool calls are in the messages
            for msg in messages:
                if hasattr(msg, 'tool_calls'):
                    for tool_call in msg.tool_calls:
                        if tool_call.get('name') == 'search_documents':
                            citations.append({
                                "document_id": "Retrieved from uploaded documents",
                                "score": 1.0
                            })

            return {
                "answer": answer,
                "citations": citations
            }
        except Exception as e:
            return {
                "answer": f"Error: {str(e)}",
                "citations": []
            }

