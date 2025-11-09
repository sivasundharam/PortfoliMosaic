import os
import re
from typing import Dict, Any, List, Optional
import pdfplumber
import pandas as pd
from PyPDF2 import PdfReader


class DocumentParser:
    """Parse various document formats and extract structured data"""
    
    def parse(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Parse document and return extracted text and structured data"""
        ext = filename.lower().split(".")[-1]
        
        if ext == "pdf":
            return self._parse_pdf(file_path, filename)
        elif ext in ["csv", "xlsx", "xls"]:
            return self._parse_spreadsheet(file_path, filename, ext)
        elif ext == "txt":
            return self._parse_text(file_path, filename)
        else:
            return self._parse_generic(file_path, filename)
    
    def _parse_pdf(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Parse PDF using pdfplumber (better for tables) and PyPDF2 (fallback)"""
        text_parts = []
        tables_data = []
        
        try:
            # Try pdfplumber first (better for tables)
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract text
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"=== Page {page_num} ===\n{page_text}\n")
                    
                    # Extract tables
                    page_tables = page.extract_tables()
                    for table in page_tables:
                        if table and len(table) > 1:
                            tables_data.append({
                                "page": page_num,
                                "table": table
                            })
        except Exception as e:
            # Fallback to PyPDF2
            try:
                reader = PdfReader(file_path)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"=== Page {page_num} ===\n{text}\n")
            except Exception as e2:
                return {
                    "text": f"Error parsing PDF: {str(e2)}",
                    "metadata": {"filename": filename, "pages": 0},
                    "entities": [],
                    "tables": []
                }
        
        full_text = "\n".join(text_parts)
        
        # Extract structured data from text
        structured_data = self._extract_structured_data(full_text, filename)
        
        # Convert tables to markdown format for better structure
        markdown_text = full_text
        if tables_data:
            markdown_text += "\n\n## Tables\n\n"
            for table_info in tables_data:
                table = table_info.get("table", [])
                if table and len(table) > 1:
                    # Convert table to markdown
                    markdown_text += f"### Table from page {table_info.get('page', '?')}\n\n"
                    # Header row
                    if table[0]:
                        markdown_text += "| " + " | ".join(str(cell) if cell else "" for cell in table[0]) + " |\n"
                        markdown_text += "| " + " | ".join(["---"] * len(table[0])) + " |\n"
                    # Data rows
                    for row in table[1:]:
                        if row:
                            markdown_text += "| " + " | ".join(str(cell) if cell else "" for cell in row) + " |\n"
                    markdown_text += "\n"
        
        return {
            "text": full_text,
            "markdown": markdown_text,
            "format": "markdown",
            "metadata": {"filename": filename, "pages": len(text_parts)},
            "entities": structured_data,
            "tables": tables_data
        }
    
    def _parse_spreadsheet(self, file_path: str, filename: str, ext: str) -> Dict[str, Any]:
        """Parse CSV or Excel files"""
        try:
            if ext == "csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            
            # Convert to text representation
            text = f"Document: {filename}\n\n"
            text += df.to_string(index=False)
            
            # Also store as structured data
            structured_data = []
            for col in df.columns:
                structured_data.append({
                    "type": "column",
                    "name": col,
                    "values": df[col].dropna().tolist()[:10]  # Sample values
                })
            
            # Extract holdings if column names suggest it
            holdings = self._extract_holdings_from_dataframe(df)
            
            # Convert dataframe to markdown table for better structure
            markdown = f"# {filename}\n\n"
            markdown += "## Data\n\n"
            
            # Convert to markdown table
            if len(df) > 0:
                # Header
                markdown += "| " + " | ".join(str(col) for col in df.columns) + " |\n"
                markdown += "| " + " | ".join(["---"] * len(df.columns)) + " |\n"
                # Rows (limit to 100 for markdown)
                for _, row in df.head(100).iterrows():
                    markdown += "| " + " | ".join(str(val) if pd.notna(val) else "" for val in row) + " |\n"
            
            return {
                "text": text,
                "markdown": markdown,
                "format": "markdown",
                "metadata": {"filename": filename, "rows": len(df), "columns": list(df.columns)},
                "entities": structured_data,
                "holdings": holdings,
                "dataframe": df.to_dict('records')[:100]  # Limit to 100 rows
            }
        except Exception as e:
            return {
                "text": f"Error parsing spreadsheet: {str(e)}",
                "metadata": {"filename": filename},
                "entities": []
            }
    
    def _parse_text(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Parse plain text file"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            
            structured_data = self._extract_structured_data(text, filename)
            
            return {
                "text": text,
                "metadata": {"filename": filename},
                "entities": structured_data
            }
        except Exception as e:
            return {
                "text": f"Error reading text file: {str(e)}",
                "metadata": {"filename": filename},
                "entities": []
            }
    
    def _parse_generic(self, file_path: str, filename: str) -> Dict[str, Any]:
        """Generic parser for unknown file types"""
        return {
            "text": f"Unsupported file type: {filename}",
            "metadata": {"filename": filename},
            "entities": []
        }
    
    def _extract_structured_data(self, text: str, filename: str) -> List[Dict[str, Any]]:
        """Extract structured entities from text"""
        entities = []
        
        # Extract stock symbols (1-5 uppercase letters)
        symbols = re.findall(r'\b[A-Z]{1,5}\b', text)
        if symbols:
            entities.append({
                "type": "stock_symbols",
                "values": list(set(symbols))
            })
        
        # Extract monetary values
        money_pattern = r'\$[\d,]+(?:\.\d{2})?'
        money_values = re.findall(money_pattern, text)
        if money_values:
            entities.append({
                "type": "monetary_values",
                "values": money_values[:20]  # Limit to 20
            })
        
        # Extract percentages
        percent_pattern = r'\d+\.?\d*\s*%'
        percentages = re.findall(percent_pattern, text)
        if percentages:
            entities.append({
                "type": "percentages",
                "values": percentages[:20]
            })
        
        # Extract dates
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        dates = re.findall(date_pattern, text)
        if dates:
            entities.append({
                "type": "dates",
                "values": list(set(dates))[:20]
            })
        
        return entities
    
    def _extract_holdings_from_dataframe(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract holdings from dataframe if relevant columns exist"""
        holdings = []
        
        # Look for symbol/ticker columns
        symbol_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["symbol", "ticker", "stock", "security"])]
        quantity_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["quantity", "shares", "qty", "amount"])]
        price_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["price", "value", "cost"])]
        
        if symbol_cols and quantity_cols:
            symbol_col = symbol_cols[0]
            quantity_col = quantity_cols[0]
            price_col = price_cols[0] if price_cols else None
            
            for _, row in df.iterrows():
                symbol = str(row[symbol_col]).strip() if pd.notna(row[symbol_col]) else None
                quantity = row[quantity_col] if pd.notna(row[quantity_col]) else None
                
                if symbol and quantity and symbol.upper().isalpha() and len(symbol) <= 5:
                    holding = {
                        "symbol": symbol.upper(),
                        "quantity": float(quantity) if isinstance(quantity, (int, float)) else None
                    }
                    if price_col and pd.notna(row[price_col]):
                        holding["price"] = float(row[price_col])
                    holdings.append(holding)
        
        return holdings

