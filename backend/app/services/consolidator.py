from typing import Dict, List, Any
from collections import defaultdict


class HoldingsConsolidator:
    """Consolidate holdings across multiple documents"""
    
    def consolidate(self, holdings_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Consolidate holdings by symbol across multiple documents
        Returns aggregated view with total quantities
        """
        consolidated = defaultdict(lambda: {
            "symbol": "",
            "total_quantity": 0.0,
            "sources": []
        })
        
        for holding in holdings_list:
            symbol = holding.get("symbol", "").upper()
            quantity = float(holding.get("quantity", 0))
            source = holding.get("document_id", "unknown")
            
            if symbol:
                consolidated[symbol]["symbol"] = symbol
                consolidated[symbol]["total_quantity"] += quantity
                consolidated[symbol]["sources"].append({
                    "document_id": source,
                    "quantity": quantity
                })
        
        return {
            "holdings": list(consolidated.values()),
            "total_symbols": len(consolidated),
            "total_positions": sum(h["total_quantity"] for h in consolidated.values())
        }
    
    def get_portfolio_summary(self, holdings_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get portfolio summary statistics"""
        if not holdings_list:
            return {
                "total_symbols": 0,
                "total_quantity": 0,
                "by_document": {}
            }
        
        by_doc = defaultdict(list)
        total_qty = 0
        symbols = set()
        
        for holding in holdings_list:
            doc_id = holding.get("document_id", "unknown")
            symbol = holding.get("symbol", "").upper()
            quantity = float(holding.get("quantity", 0))
            
            by_doc[doc_id].append(holding)
            total_qty += quantity
            if symbol:
                symbols.add(symbol)
        
        return {
            "total_symbols": len(symbols),
            "total_quantity": total_qty,
            "by_document": dict(by_doc)
        }

