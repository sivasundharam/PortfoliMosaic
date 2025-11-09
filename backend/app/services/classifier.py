import re
from typing import Dict, Any


class DocumentClassifier:
    """
    Document classifier with two modes:
    1. Primary: Use Landing AI ADE's DocumentType (AI-powered, context-aware)
    2. Fallback: Use keyword-based classification

    ADE Document Types (from extraction_schema.py):
    - BrokerageStatement
    - TradeConfirmation
    - BalanceSheet
    - CashFlowStatement
    - SECReport
    - TaxDocument
    - PerformanceReport

    Keyword Classifier Types:
    - Tax Document
    - Brokerage Statement
    - Balance Sheet
    - Income Statement
    - Cash Flow Statement
    - SEC Report
    - Annual Report
    - Quarterly Report
    - Other
    """

    @staticmethod
    def normalize_document_type(doc_type: str) -> str:
        """
        Normalize document type to consistent format.
        Handles both ADE types (CamelCase) and classifier types (Title Case).

        Args:
            doc_type: Document type from ADE or classifier

        Returns:
            Normalized document type string
        """
        if not doc_type:
            return "Other"

        # Mapping from ADE types to display types
        ade_to_display = {
            "BrokerageStatement": "Brokerage Statement",
            "TradeConfirmation": "Trade Confirmation",
            "BalanceSheet": "Balance Sheet",
            "CashFlowStatement": "Cash Flow Statement",
            "SECReport": "SEC Report",
            "TaxDocument": "Tax Document",
            "PerformanceReport": "Performance Report"
        }

        # If it's an ADE type, convert to display format
        if doc_type in ade_to_display:
            return ade_to_display[doc_type]

        # Otherwise return as-is (already in display format)
        return doc_type
    def classify(self, text: str, filename: str) -> str:
        text_lower = text.lower()
        filename_lower = filename.lower()

        # Check for tax documents FIRST (highest priority)
        # 1099 forms: 1099-B, 1099-DIV, 1099-INT, 1099-MISC, etc.
        if any(kw in text_lower for kw in ["form 1099", "1099-b", "1099-div", "1099-int", "1099-misc", "1099-r"]):
            return "Tax Document"
        if any(kw in filename_lower for kw in ["1099", "1099b", "1099_b"]):
            return "Tax Document"

        # W-2 forms
        if "form w-2" in text_lower or "w-2" in filename_lower or "w2" in filename_lower:
            return "Tax Document"

        # Other tax forms
        if any(kw in text_lower for kw in ["schedule d", "form 8949", "capital gains and losses"]):
            return "Tax Document"

        # Check for brokerage statement indicators
        if any(kw in text_lower for kw in ["brokerage statement", "account statement", "trade confirmation", "holding", "portfolio"]):
            return "Brokerage Statement"
        
        # Check for balance sheet indicators
        if any(kw in text_lower for kw in ["balance sheet", "assets", "liabilities", "equity", "total assets"]) and "balance" in text_lower:
            return "Balance Sheet"
        
        # Check for cash flow indicators
        if any(kw in text_lower for kw in ["cash flow", "operating activities", "investing activities", "financing activities"]):
            return "Cash Flow Statement"
        
        # Check for income statement indicators
        if any(kw in text_lower for kw in ["income statement", "revenue", "net income", "earnings per share", "income from operations"]):
            return "Income Statement"
        
        # Check for SEC report indicators
        if any(kw in text_lower for kw in ["form 10-k", "form 10-q", "sec filing", "sec report", "sarbanes-oxley"]):
            return "SEC Report"
        
        # Check for annual report indicators
        if "annual report" in text_lower or "annual" in filename_lower:
            return "Annual Report"
        
        # Check for quarterly report indicators
        if "quarterly" in text_lower or "q1" in filename_lower or "q2" in filename_lower or "q3" in filename_lower or "q4" in filename_lower:
            return "Quarterly Report"
        
        # Default classification based on filename patterns
        if any(kw in filename_lower for kw in ["balance", "bs"]):
            return "Balance Sheet"
        if any(kw in filename_lower for kw in ["income", "p&l", "pnl"]):
            return "Income Statement"
        if any(kw in filename_lower for kw in ["cash", "cf"]):
            return "Cash Flow Statement"
        if any(kw in filename_lower for kw in ["statement", "stmt"]):
            return "Brokerage Statement"
        
        return "Other"

