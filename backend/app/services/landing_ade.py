import os
import requests
from typing import Dict, Any
from .document_parser import DocumentParser


class LandingAdeService:
    def __init__(self):
        self.api_key = os.getenv("LANDING_AI_API_KEY", "")
        self.api_url = os.getenv("LANDING_AI_API_URL", "https://api.va.landing.ai/v1/ade/parse")
        self.parser = DocumentParser()

    def extract(self, file_path: str, filename: str) -> Dict[str, Any]:
        # Always use local parser first to ensure we get real data
        local_result = self.parser.parse(file_path, filename)
        
        # If we have LandingAI API key, enhance with AI extraction
        if self.api_key:
            try:
                with open(file_path, "rb") as f:
                    files = {"document": (filename, f)}
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    response = requests.post(self.api_url, files=files, headers=headers, timeout=60)
                    response.raise_for_status()
                    ai_result = response.json()
                    
                    # Prefer markdown over text if available (better structure preservation)
                    if "markdown" in ai_result and ai_result["markdown"]:
                        local_result["markdown"] = ai_result["markdown"]
                        local_result["text"] = ai_result["markdown"]  # Use markdown as text too
                        local_result["format"] = "markdown"
                    elif "text" in ai_result and ai_result["text"]:
                        local_result["text"] = ai_result["text"]
                        local_result["format"] = "text"
                    
                    # Merge entities if available
                    if "entities" in ai_result:
                        if not local_result.get("entities"):
                            local_result["entities"] = []
                        local_result["entities"].extend(ai_result.get("entities", []))
                    
                    # Use ADE's structured data if available
                    if "structured_data" in ai_result:
                        local_result["structured_data"] = ai_result["structured_data"]
                    
                    # Use ADE's tables if available (usually better formatted)
                    if "tables" in ai_result and ai_result["tables"]:
                        local_result["tables"] = ai_result["tables"]
            except Exception as e:
                # Fall back to local parsing if API fails
                pass
        
        return local_result

