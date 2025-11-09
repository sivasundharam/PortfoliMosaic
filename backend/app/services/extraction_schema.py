"""
Comprehensive Portfolio Document Extraction Schema
Extracts structured data from various portfolio-related documents:
- Brokerage statements (monthly/quarterly/yearly)
- Trade confirmations
- Balance sheets
- Income statements
- Cash flow statements
- SEC reports (10-K, 10-Q, 8-K)
- Tax documents (1099-DIV, 1099-INT, 1099-B)
- Portfolio performance reports
"""

# Comprehensive extraction schema for portfolio documents
PORTFOLIO_SCHEMA = {
    "type": "object",
    "properties": {
        # === DOCUMENT METADATA ===
        "DocumentType": {
            "type": "string",
            "description": """Type of document. Choose ONE from:
- BalanceSheet: Shows assets, liabilities, and equity at a specific point in time. Contains line items like 'Total Assets', 'Total Liabilities', 'Stockholders Equity'.
- CashFlowStatement: Shows cash inflows/outflows. Contains sections like 'Operating Activities', 'Investing Activities', 'Financing Activities'.
- BrokerageStatement: Investment account statement showing holdings, transactions, account value.
- TradeConfirmation: Confirmation of a specific trade or transaction.
- TaxDocument: Tax forms like 1099-B, 1099-DIV, W-2, Schedule D.
- SECReport: SEC filings like 10-K, 10-Q.
- PerformanceReport: Portfolio performance analysis."""
        },
        "ReportDate": {"type": "string", "description": "Date of the report or statement"},
        "PeriodStart": {"type": "string", "description": "Start date of reporting period"},
        "PeriodEnd": {"type": "string", "description": "End date of reporting period"},
        "CompanyName": {"type": "string", "description": "Company or brokerage name"},
        "TickerSymbol": {"type": "string", "description": "Stock ticker symbol (for SEC reports)"},
        
        # === ACCOUNT INFORMATION ===
        "BrokerageFirm": {"type": "string", "description": "Name of brokerage firm: Fidelity, Charles Schwab, Vanguard, E*TRADE, TD Ameritrade, Robinhood, etc."},
        "AccountNumber": {"type": "string", "description": "Account number"},
        "AccountHolderName": {"type": "string", "description": "Name of account holder"},
        "AccountType": {"type": "string", "description": "Account type: Individual, Joint, IRA, 401k, Roth IRA, etc."},

        # === ACCOUNT FEATURES ===
        "AccountFeatures": {
            "type": "object",
            "description": "Account features and settings",
            "properties": {
                "DividendReinvestmentEnabled": {"type": "boolean", "description": "Whether dividend reinvestment (DRIP) is enabled for the account"},
                "MarginEnabled": {"type": "boolean", "description": "Whether margin trading is enabled"},
                "OptionsEnabled": {"type": "boolean", "description": "Whether options trading is enabled"},
                "CheckWritingEnabled": {"type": "boolean", "description": "Whether check writing is enabled"}
            }
        },
        
        # === HOLDINGS (for brokerage statements) ===
        "Holdings": {
            "type": "array",
            "description": "List of securities held in the account",
            "items": {
                "type": "object",
                "properties": {
                    "Symbol": {"type": "string", "description": "Security ticker symbol"},
                    "SecurityName": {"type": "string", "description": "Full name of security"},
                    "Quantity": {"type": "number", "description": "Number of shares/units"},
                    "PricePerUnit": {"type": "number", "description": "Price per share/unit"},
                    "MarketValue": {"type": "number", "description": "Total market value"},
                    "CostBasis": {"type": "number", "description": "Original purchase cost"},
                    "GainLoss": {"type": "number", "description": "Unrealized gain/loss"},
                    "GainLossPercent": {"type": "number", "description": "Gain/loss percentage"},
                    "DividendReinvestment": {"type": "boolean", "description": "Whether dividend reinvestment (DRIP) is enabled for this specific security"}
                }
            }
        },
        
        # === ACCOUNT BALANCES ===
        "CashBalance": {"type": "number", "description": "Cash balance in account"},
        "TotalAccountValue": {"type": "number", "description": "Total value of account"},
        "TotalMarketValue": {"type": "number", "description": "Total market value of securities"},
        
        # === PERFORMANCE METRICS ===
        "PeriodGainLoss": {"type": "number", "description": "Gain/loss for the period"},
        "PeriodGainLossPercent": {"type": "number", "description": "Gain/loss percentage for period"},
        "YTDGainLoss": {"type": "number", "description": "Year-to-date gain/loss"},
        "YTDGainLossPercent": {"type": "number", "description": "Year-to-date gain/loss percentage"},
        "TotalReturn": {"type": "number", "description": "Total return"},
        "TotalReturnPercent": {"type": "number", "description": "Total return percentage"},
        
        # === INCOME ===
        "DividendsReceived": {"type": "number", "description": "Dividends received during period"},
        "InterestEarned": {"type": "number", "description": "Interest earned during period"},
        "QualifiedDividends": {"type": "number", "description": "Qualified dividends (for tax docs)"},
        "NonQualifiedDividends": {"type": "number", "description": "Non-qualified dividends (for tax docs)"},

        # === TAX DOCUMENTS (1099-B, 1099-DIV, 1099-INT) ===
        "TaxYear": {"type": "string", "description": "Tax year for tax documents (e.g., '2024')"},
        "Form1099B": {
            "type": "object",
            "description": "Form 1099-B: Proceeds from Broker and Barter Exchange Transactions",
            "properties": {
                "TotalProceeds": {"type": "number", "description": "Total proceeds from sales of securities"},
                "TotalCostBasis": {"type": "number", "description": "Total cost basis of securities sold"},
                "ShortTermGain": {"type": "number", "description": "Short-term capital gain/loss (held ≤1 year)"},
                "LongTermGain": {"type": "number", "description": "Long-term capital gain/loss (held >1 year)"},
                "TotalCapitalGain": {"type": "number", "description": "Total capital gain/loss (short-term + long-term)"},
                "WashSaleLoss": {"type": "number", "description": "Wash sale loss disallowed"},
                "FederalTaxWithheld": {"type": "number", "description": "Federal income tax withheld"},
                "NonCoveredSecurities": {"type": "number", "description": "Proceeds from non-covered securities"}
            }
        },
        "Form1099DIV": {
            "type": "object",
            "description": "Form 1099-DIV: Dividends and Distributions",
            "properties": {
                "TotalOrdinaryDividends": {"type": "number", "description": "Total ordinary dividends (Box 1a)"},
                "QualifiedDividends": {"type": "number", "description": "Qualified dividends (Box 1b)"},
                "TotalCapitalGainDistributions": {"type": "number", "description": "Total capital gain distributions (Box 2a)"},
                "Section1250Gain": {"type": "number", "description": "Unrecaptured Section 1250 gain (Box 2b)"},
                "FederalTaxWithheld": {"type": "number", "description": "Federal income tax withheld (Box 4)"}
            }
        },
        "Form1099INT": {
            "type": "object",
            "description": "Form 1099-INT: Interest Income",
            "properties": {
                "InterestIncome": {"type": "number", "description": "Interest income (Box 1)"},
                "EarlyWithdrawalPenalty": {"type": "number", "description": "Early withdrawal penalty (Box 2)"},
                "USBondInterest": {"type": "number", "description": "Interest on U.S. Savings Bonds and Treasury obligations (Box 3)"},
                "FederalTaxWithheld": {"type": "number", "description": "Federal income tax withheld (Box 4)"}
            }
        },

        # === FEES & EXPENSES ===
        "FeesCharged": {"type": "number", "description": "Total fees charged"},
        "ManagementFees": {"type": "number", "description": "Management fees"},
        "CommissionFees": {"type": "number", "description": "Commission fees"},
        
        # === TRANSACTIONS (for trade confirmations) ===
        "Transactions": {
            "type": "array",
            "description": "List of transactions",
            "items": {
                "type": "object",
                "properties": {
                    "TradeDate": {"type": "string", "description": "Date of trade"},
                    "SettlementDate": {"type": "string", "description": "Settlement date"},
                    "Symbol": {"type": "string", "description": "Security symbol"},
                    "SecurityName": {"type": "string", "description": "Security name"},
                    "Action": {"type": "string", "description": "Buy, Sell, Dividend, Interest, Fee"},
                    "Quantity": {"type": "number", "description": "Number of shares"},
                    "Price": {"type": "number", "description": "Price per share"},
                    "Amount": {"type": "number", "description": "Total amount"},
                    "Commission": {"type": "number", "description": "Commission/fees"}
                }
            }
        },
        
        # === BALANCE SHEET ITEMS ===
        "TotalAssets": {"type": "number", "description": "Total assets"},
        "CurrentAssets": {"type": "number", "description": "Current assets"},
        "FixedAssets": {"type": "number", "description": "Fixed assets"},
        "CashAndEquivalents": {"type": "number", "description": "Cash and cash equivalents"},
        "AccountsReceivable": {"type": "number", "description": "Accounts receivable"},
        "Inventory": {"type": "number", "description": "Inventory"},
        "PropertyPlantEquipment": {"type": "number", "description": "Property, plant & equipment"},
        
        "TotalLiabilities": {"type": "number", "description": "Total liabilities"},
        "CurrentLiabilities": {"type": "number", "description": "Current liabilities"},
        "LongTermLiabilities": {"type": "number", "description": "Long-term liabilities"},
        "AccountsPayable": {"type": "number", "description": "Accounts payable"},
        "LongTermDebt": {"type": "number", "description": "Long-term debt"},
        
        "ShareholderEquity": {"type": "number", "description": "Total shareholder equity"},
        "RetainedEarnings": {"type": "number", "description": "Retained earnings"},
        
        # === INCOME STATEMENT ITEMS ===
        "Revenue": {"type": "number", "description": "Total revenue/sales"},
        "CostOfGoodsSold": {"type": "number", "description": "Cost of goods sold (COGS)"},
        "GrossProfit": {"type": "number", "description": "Gross profit"},
        "OperatingExpenses": {"type": "number", "description": "Operating expenses"},
        "OperatingIncome": {"type": "number", "description": "Operating income"},
        "InterestExpense": {"type": "number", "description": "Interest expense"},
        "TaxExpense": {"type": "number", "description": "Tax expense"},
        "NetIncome": {"type": "number", "description": "Net income"},
        "EPS": {"type": "number", "description": "Earnings per share"},
        "DividendsPaid": {"type": "number", "description": "Dividends paid"},
        
        # === CASH FLOW STATEMENT ITEMS ===
        "OperatingCashFlow": {"type": "number", "description": "Cash flow from operations"},
        "InvestingCashFlow": {"type": "number", "description": "Cash flow from investing"},
        "FinancingCashFlow": {"type": "number", "description": "Cash flow from financing"},
        "NetCashFlow": {"type": "number", "description": "Net change in cash"},
        "BeginningCashBalance": {"type": "number", "description": "Beginning cash balance"},
        "EndingCashBalance": {"type": "number", "description": "Ending cash balance"},
        "CapitalExpenditures": {"type": "number", "description": "Capital expenditures (CapEx)"},
        "DepreciationAmortization": {"type": "number", "description": "Depreciation & amortization"},
        
        # === TAX DOCUMENT ITEMS ===
        "TaxYear": {"type": "string", "description": "Tax year"},
        "PayerName": {"type": "string", "description": "Payer name (for 1099 forms)"},
        "RecipientName": {"type": "string", "description": "Recipient name"},
        "ShortTermCapitalGains": {"type": "number", "description": "Short-term capital gains"},
        "LongTermCapitalGains": {"type": "number", "description": "Long-term capital gains"},
        "ProceedsFromSales": {"type": "number", "description": "Proceeds from sales"},
        "WashSaleAdjustments": {"type": "number", "description": "Wash sale loss adjustments"},
        
        # === ASSET ALLOCATION ===
        "AssetAllocation": {
            "type": "object",
            "description": "Asset allocation breakdown",
            "properties": {
                "StocksPercent": {"type": "number", "description": "Percentage in stocks"},
                "BondsPercent": {"type": "number", "description": "Percentage in bonds"},
                "CashPercent": {"type": "number", "description": "Percentage in cash"},
                "OtherPercent": {"type": "number", "description": "Percentage in other assets"}
            }
        },
        
        # === SECTOR ALLOCATION ===
        "SectorAllocation": {
            "type": "array",
            "description": "Allocation by sector",
            "items": {
                "type": "object",
                "properties": {
                    "Sector": {"type": "string", "description": "Sector name"},
                    "Percent": {"type": "number", "description": "Percentage allocation"},
                    "Value": {"type": "number", "description": "Dollar value"}
                }
            }
        },
        
        # === BENCHMARK COMPARISON ===
        "BenchmarkName": {"type": "string", "description": "Benchmark index name (e.g., S&P 500)"},
        "BenchmarkReturn": {"type": "number", "description": "Benchmark return percentage"},
        "OutperformanceUnderperformance": {"type": "number", "description": "Difference vs benchmark"},
        
        # === RISK METRICS ===
        "Beta": {"type": "number", "description": "Portfolio beta"},
        "Volatility": {"type": "number", "description": "Portfolio volatility/standard deviation"},
        "SharpeRatio": {"type": "number", "description": "Sharpe ratio"},
        
        # === CONTRIBUTIONS & WITHDRAWALS ===
        "Contributions": {"type": "number", "description": "Net contributions during period"},
        "Withdrawals": {"type": "number", "description": "Net withdrawals during period"},
        "NetContributions": {"type": "number", "description": "Net contributions (contributions - withdrawals)"},
        
        # === ADDITIONAL METADATA ===
        "Notes": {"type": "string", "description": "Additional notes or important information"},
        "RiskFactors": {"type": "string", "description": "Risk factors mentioned in document"},
        "ManagementDiscussion": {"type": "string", "description": "Management discussion & analysis (MD&A)"}
    },
    "required": []  # Make all optional for flexibility
}

# Categorized field groups for organized display
FIELD_CATEGORIES = {
    "document_metadata": [
        "DocumentType", "ReportDate", "PeriodStart", "PeriodEnd", 
        "CompanyName", "TickerSymbol"
    ],
    "account_info": [
        "AccountNumber", "AccountHolderName", "AccountType"
    ],
    "holdings": [
        "Holdings", "TotalMarketValue"
    ],
    "balances": [
        "CashBalance", "TotalAccountValue"
    ],
    "performance": [
        "PeriodGainLoss", "PeriodGainLossPercent", "YTDGainLoss", 
        "YTDGainLossPercent", "TotalReturn", "TotalReturnPercent"
    ],
    "income": [
        "DividendsReceived", "InterestEarned", "QualifiedDividends", 
        "NonQualifiedDividends"
    ],
    "fees": [
        "FeesCharged", "ManagementFees", "CommissionFees"
    ],
    "transactions": [
        "Transactions"
    ],
    "balance_sheet": [
        "TotalAssets", "CurrentAssets", "FixedAssets", "CashAndEquivalents",
        "AccountsReceivable", "Inventory", "PropertyPlantEquipment",
        "TotalLiabilities", "CurrentLiabilities", "LongTermLiabilities",
        "AccountsPayable", "LongTermDebt", "ShareholderEquity", "RetainedEarnings"
    ],
    "income_statement": [
        "Revenue", "CostOfGoodsSold", "GrossProfit", "OperatingExpenses",
        "OperatingIncome", "InterestExpense", "TaxExpense", "NetIncome",
        "EPS", "DividendsPaid"
    ],
    "cash_flow": [
        "OperatingCashFlow", "InvestingCashFlow", "FinancingCashFlow",
        "NetCashFlow", "BeginningCashBalance", "EndingCashBalance",
        "CapitalExpenditures", "DepreciationAmortization"
    ],
    "tax_documents": [
        "TaxYear", "PayerName", "RecipientName", "ShortTermCapitalGains",
        "LongTermCapitalGains", "ProceedsFromSales", "WashSaleAdjustments"
    ],
    "asset_allocation": [
        "AssetAllocation", "SectorAllocation"
    ],
    "benchmark": [
        "BenchmarkName", "BenchmarkReturn", "OutperformanceUnderperformance"
    ],
    "risk_metrics": [
        "Beta", "Volatility", "SharpeRatio"
    ],
    "contributions_withdrawals": [
        "Contributions", "Withdrawals", "NetContributions"
    ]
}

def categorize_extraction(extraction_json: dict) -> dict:
    """Organize extracted fields by category"""
    categorized = {}
    
    for category, fields in FIELD_CATEGORIES.items():
        category_data = {}
        for field in fields:
            if field in extraction_json and extraction_json[field]:
                category_data[field] = extraction_json[field]
        if category_data:
            categorized[category] = category_data
    
    return categorized

