import os
import requests
from typing import Dict, Any, Optional


class StockPriceTool:
    def __init__(self):
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.base_url = "https://www.alphavantage.co/query"

    def get_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get current stock price for a symbol.
        Returns price data or error information.
        """
        if not self.api_key:
            # Fallback: return mock data for demo
            return self._mock_price(symbol)
        
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol.upper(),
                "apikey": self.api_key
            }
            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "Global Quote" in data and data["Global Quote"]:
                quote = data["Global Quote"]
                return {
                    "symbol": quote.get("01. symbol", symbol),
                    "price": quote.get("05. price"),
                    "change": quote.get("09. change"),
                    "change_percent": quote.get("10. change percent"),
                    "volume": quote.get("06. volume"),
                    "high": quote.get("03. high"),
                    "low": quote.get("04. low"),
                }
            return {"error": "Symbol not found", "symbol": symbol}
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

    def _mock_price(self, symbol: str) -> Dict[str, Any]:
        # Mock price data for demo
        import random
        base_price = 100.0 + random.uniform(-20, 50)
        return {
            "symbol": symbol.upper(),
            "price": f"{base_price:.2f}",
            "change": f"{random.uniform(-2, 2):.2f}",
            "change_percent": f"{random.uniform(-3, 3):.2f}%",
            "volume": str(random.randint(1000000, 50000000)),
            "high": f"{base_price + random.uniform(0, 5):.2f}",
            "low": f"{base_price - random.uniform(0, 5):.2f}",
            "note": "Mock data - set ALPHA_VANTAGE_API_KEY for real prices"
        }

