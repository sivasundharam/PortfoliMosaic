"""
Landing AI ADE (Advanced Document Extraction) Integration
Handles PDF parsing and structured data extraction for portfolio documents
"""

import os
import json
import time
import requests
from typing import Dict, Any, Optional


class LandingAIError(Exception):
    """Custom exception for Landing AI API errors"""
    pass


class LandingAIClient:
    """
    Client for Landing AI ADE API using direct HTTP requests

    Features:
    - Manual retry logic for rate limits (429)
    - Exponential backoff
    - Support for both parse and extract operations

    Usage:
        client = LandingAIClient()
        result = client.parse_and_extract("document.pdf", PORTFOLIO_SCHEMA)
        markdown = result["markdown"]
        extraction = result["extraction"]
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.va.landing.ai/v1/ade",
        model: str = "dpt-2-latest",
        timeout: int = 180,
        max_retries: int = 3
    ):
        """
        Initialize Landing AI client

        Args:
            api_key: Landing AI API key (defaults to LANDING_AI_API_KEY env var)
            base_url: Base URL for Landing AI API
            model: Default ADE model to use (default: dpt-2-latest)
            timeout: Request timeout in seconds (default: 180)
            max_retries: Maximum number of retries for rate limits (default: 3)
        """
        # Get API key from environment if not provided
        if not api_key:
            api_key = os.getenv("LANDING_AI_API_KEY")

        if not api_key:
            raise LandingAIError(
                "API key not found. Set LANDING_AI_API_KEY environment variable, "
                "or pass api_key parameter to LandingAIClient()"
            )

        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def parse_pdf(
        self,
        file_path: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Parse PDF document to markdown using Landing AI ADE

        Args:
            file_path: Path to the PDF file
            model: ADE model to use (default: uses client's default model)
            timeout: Request timeout in seconds (default: uses client's default)
            max_retries: Maximum number of retries for rate limits (default: uses client's default)

        Returns:
            Dictionary containing:
            - markdown: Extracted markdown text
            - metadata: Document metadata (page count, etc.)

        Raises:
            LandingAIError: If parsing fails
        """
        url = f"{self.base_url}/parse"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        timeout_val = timeout or self.timeout
        retries = max_retries if max_retries is not None else self.max_retries

        # Retry logic for rate limits
        for attempt in range(retries):
            try:
                with open(file_path, "rb") as f:
                    response = requests.post(
                        url,
                        headers=headers,
                        files={"document": (os.path.basename(file_path), f, "application/pdf")},
                        data={"model": model or self.model},
                        timeout=timeout_val
                    )

                # Handle rate limit with retry
                if response.status_code == 429:
                    if attempt < retries - 1:
                        wait_time = 2 ** (attempt + 1)  # Exponential backoff: 2s, 4s, 8s
                        print(f"⚠️ Rate limit hit (429), retrying in {wait_time}s... (attempt {attempt + 1}/{retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise LandingAIError(
                            f"Landing AI API rate limit exceeded after {retries} retries. "
                            "Please wait a few minutes and try again."
                        )
                # Raise for other HTTP errors
                response.raise_for_status()

                # Parse response
                result = response.json()
                markdown = result.get("markdown", "")

                # Extract metadata
                metadata = {
                    "pages": result.get("pages", 0),
                    "model": model or self.model
                }

                if attempt > 0:
                    print(f"✅ Success on attempt {attempt + 1}!")

                return {
                    "markdown": markdown,
                    "metadata": metadata
                }

            except requests.exceptions.Timeout:
                raise LandingAIError(f"Landing AI API request timed out after {timeout_val} seconds")
            except requests.exceptions.ConnectionError as e:
                raise LandingAIError(f"Landing AI API connection error: {str(e)}")
            except requests.exceptions.HTTPError as e:
                raise LandingAIError(f"Landing AI API request failed: {str(e)}")
            except Exception as e:
                raise LandingAIError(f"Unexpected error during PDF parsing: {str(e)}")

        # Should never reach here
        raise LandingAIError("Failed to parse PDF after all retries")

    def extract_from_markdown(
        self,
        markdown: str,
        schema: Dict[str, Any],
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from markdown using Landing AI ADE

        Args:
            markdown: Markdown text to extract from
            schema: JSON schema defining the structure to extract
            timeout: Request timeout in seconds (default: uses client's default)
            max_retries: Maximum number of retries for rate limits (default: uses client's default)

        Returns:
            Dictionary containing:
            - extraction: Extracted structured data matching the schema
            - confidence: Confidence scores for extracted fields (if available)

        Raises:
            LandingAIError: If extraction fails
        """
        if not markdown or not markdown.strip():
            raise LandingAIError("Markdown content is empty")

        if not schema:
            raise LandingAIError("Schema is required for extraction")

        url = f"{self.base_url}/extract"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        timeout_val = timeout or self.timeout
        retries = max_retries if max_retries is not None else self.max_retries

        # Retry logic for rate limits
        for attempt in range(retries):
            try:
                # Send markdown as a file and schema as JSON string in form data
                import io
                markdown_file = io.BytesIO(markdown.encode('utf-8'))

                response = requests.post(
                    url,
                    headers=headers,
                    files={"markdown": ("document.md", markdown_file, "text/markdown")},
                    data={"schema": json.dumps(schema)},
                    timeout=timeout_val
                )

                # Handle rate limit with retry
                if response.status_code == 429:
                    if attempt < retries - 1:
                        wait_time = 2 ** (attempt + 1)  # Exponential backoff: 2s, 4s, 8s
                        print(f"⚠️ Rate limit hit (429), retrying in {wait_time}s... (attempt {attempt + 1}/{retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise LandingAIError(
                            f"Landing AI API rate limit exceeded after {retries} retries. "
                            "Please wait a few minutes and try again."
                        )

                # Raise for other HTTP errors
                response.raise_for_status()

                # Parse response
                result = response.json()
                extraction = result.get("extraction", {})
                confidence = result.get("confidence", {})

                if attempt > 0:
                    print(f"✅ Success on attempt {attempt + 1}!")

                return {
                    "extraction": extraction,
                    "confidence": confidence
                }

            except requests.exceptions.Timeout:
                raise LandingAIError(f"Landing AI API request timed out after {timeout_val} seconds")
            except requests.exceptions.ConnectionError as e:
                raise LandingAIError(f"Landing AI API connection error: {str(e)}")
            except requests.exceptions.HTTPError as e:
                raise LandingAIError(f"Landing AI API request failed: {str(e)}")
            except Exception as e:
                raise LandingAIError(f"Unexpected error during extraction: {str(e)}")

        # Should never reach here
        raise LandingAIError("Failed to extract data after all retries")

    def parse_and_extract(
        self,
        file_path: str,
        schema: Dict[str, Any],
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Convenience method to parse PDF and extract structured data in one call

        Args:
            file_path: Path to the PDF file
            schema: JSON schema defining the structure to extract
            model: ADE model to use (default: uses client's default model)

        Returns:
            Dictionary containing:
            - markdown: Extracted markdown text
            - extraction: Extracted structured data
            - metadata: Document metadata
            - confidence: Confidence scores

        Raises:
            LandingAIError: If parsing or extraction fails
        """
        # Step 1: Parse PDF to markdown
        parsed = self.parse_pdf(file_path, model=model)
        markdown = parsed.get("markdown", "")

        if not markdown:
            raise LandingAIError("No markdown content extracted from PDF")

        # Step 2: Extract structured data from markdown
        extraction_result = self.extract_from_markdown(markdown, schema)
        extraction_json = extraction_result.get("extraction", {})

        # Combine results
        return {
            "markdown": markdown,
            "extraction": extraction_json,
            "metadata": parsed.get("metadata", {}),
            "confidence": extraction_result.get("confidence", {})
        }

