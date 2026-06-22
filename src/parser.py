import io
import ipaddress
import logging
import os
import re
import json
import socket
import requests
import anthropic
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class JobPosting(BaseModel):
    """Structured job posting data."""
    title: str = ""
    company: str = ""
    location: str = ""
    salary_range: str = ""
    job_type: str = "" 
    remote_policy: str = "" 
    description: str = ""
    requirements: list[str] = []
    nice_to_have: list[str] = []
    benefits: list[str] = []
    raw_text: str = ""
    source_url: str = ""

    def to_prompt_context(self) -> str:
        """Standardizes the output for the Analyzer."""
        return f"""Title: {self.title}
        Company: {self.company}
        Location: {self.location}
        Salary: {self.salary_range}
        Job Type: {self.job_type}
        Remote Policy: {self.remote_policy}

        Description:
        {self.description}

        Requirements:
        {chr(10).join(f'- {req}' for req in self.requirements)}

        Nice to Have:
        {chr(10).join(f'- {item}' for item in self.nice_to_have)}

        Benefits:
        {chr(10).join(f'- {benefit}' for benefit in self.benefits)}"""

class JobParser:
    """Parse job postings using Claude."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
    }

    # Phrases that indicate JavaScript is required
    JS_REQUIRED_PHRASES = [
        "enable javascript",
        "javascript is required",
        "javascript must be enabled",
        "please enable javascript",
        "this site requires javascript",
    ]

    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model_id = "claude-sonnet-4-6"

    async def parse(self, source: str) -> JobPosting:
        if self._is_url(source):
            return await self.parse_url(source)
        return self.parse_text(source)

    # Private/reserved IP ranges that job URLs should never resolve to
    _BLOCKED_NETS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),  # AWS metadata / link-local
        ipaddress.ip_network("100.64.0.0/10"),   # Carrier-grade NAT
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]

    def _is_url(self, text: str) -> bool:
        try:
            result = urlparse(text.strip())
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False

    def _validate_url(self, url: str) -> None:
        """Reject non-HTTP schemes and URLs that resolve to private/internal addresses (SSRF guard)."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL has no hostname")
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            raise ValueError(f"Could not resolve hostname: {hostname}")
        for _, _, _, _, sockaddr in addr_infos:
            try:
                ip = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if any(ip in net for net in self._BLOCKED_NETS):
                raise ValueError(f"URL resolves to a blocked private/internal address")
    
    def _needs_javascript(self, text: str) -> bool:
        """Check if the page content indicates Javascript is required."""
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in self.JS_REQUIRED_PHRASES)
    
    def _scrape_with_requests(self, url: str) -> str:
        """Fast scrape using requests (no Javascript)"""
        response = requests.get(url, headers=self.HEADERS, timeout=20)
        response.raise_for_status()
        return response.text
    
    async def _scrape_with_playwright(self, url: str) -> str:
        """Slower scrape using Playwright (runs Javascript)."""
        logger.info("Page requires JavaScript, switching to Playwright")
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)
            await page.wait_for_timeout(3000)  # Fixed typo
            content = await page.content()
            await browser.close()
            return content

    async def parse_url(self, url: str) -> JobPosting:
        try:
            self._validate_url(url)
            # Try simple request first
            html = self._scrape_with_requests(url)

            # Check if JavaScript is needed
            if self._needs_javascript(html):
                html = await self._scrape_with_playwright(url)
            
            soup = BeautifulSoup(html, "html.parser")
            
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            
            raw_text = soup.get_text(separator=" ", strip=True)
            posting = self._llm_extract(raw_text)
            posting.source_url = url
            return posting
        except Exception as e:
            raise ValueError(f"Failed to parse URL: {e}")

    def parse_pdf(self, pdf_bytes: bytes) -> JobPosting:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
            return self._llm_extract(text)
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {e}")

    def parse_text(self, text: str) -> JobPosting:
        return self._llm_extract(text)

    def _llm_extract(self, raw_content: str) -> JobPosting:
        """Uses Claude to transform messy text into a structured JobPosting object."""

        prompt = f"""
        Extract job details from the following text into a structured JSON format.
        Focus on technical requirements and specific benefits.

        IMPORTANT:
        - The "company" field should be the company that is HIRING, not the platform hosting the job posting
        - Ignore platform names like Notion, Lever, Greenhouse, Workday, Ashby, BambooHR, etc.
        - If the company name is unclear, look for "About Us", "About [Company]", or "Who We Are" sections

        TEXT:
        {raw_content[:15000]} 
        
        Return only valid JSON matching this schema:
        {{
            "title": "string",
            "company": "string (the company that is hiring, NOT the job board platform)", 
            "location": "string",
            "salary_range": "string",
            "job_type": "string",
            "remote_policy": "string",
            "description": "string",
            "requirements": ["string"],
            "nice_to_have": ["string"],
            "benefits": ["string"]
        }}
        """
        
        try:
            response = self.client.messages.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.1
            )

            # A truncated response yields malformed JSON; fail loudly rather than
            # letting json.loads raise a cryptic parse error on a long posting.
            if response.stop_reason == "max_tokens":
                raise ValueError("Extraction response was truncated (max_tokens). Try again.")

            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', response.content[0].text.strip())
            data = json.loads(text)
            data["raw_text"] = raw_content[:5000] 
            return JobPosting(**data)
            
        except Exception as e:
            logger.error("Claude extraction error: %s", e)
            raise