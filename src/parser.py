import io
import os
import json
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pydantic import BaseModel
from pypdf import PdfReader
from openai import OpenAI
from dotenv import load_dotenv
from playwright.async_api import async_playwright

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
    """Parse job postings using OpenAI GPT-4."""

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
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model_id = "gpt-4o"

    async def parse(self, source: str) -> JobPosting:
        if self._is_url(source):
            return await self.parse_url(source)
        return self.parse_text(source)

    def _is_url(self, text: str) -> bool:
        try:
            result = urlparse(text.strip())
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False
    
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
        print("🔄 Page requires JavaScript, using Playwright...")
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
        """Uses OpenAI GPT-4 to transform messy text into a structured JobPosting object."""

        # Debug: see the first 500 characters being sent
        print("=" * 50)
        print("RAW CONTENT PREVIEW:")
        print(raw_content[:500])
        print("=" * 50)

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
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            data = json.loads(response.choices[0].message.content)

            # Debug: see what GPT-4 extracted
            print("EXTRACTED DATA:")
            print(f"Company: {data.get('company')}")
            print(f"Title: {data.get('title')}")
            print("=" * 50)

            data["raw_text"] = raw_content[:5000] 
            return JobPosting(**data)
            
        except Exception as e:
            print(f"❌ OpenAI Extraction Error: {e}")
            raise