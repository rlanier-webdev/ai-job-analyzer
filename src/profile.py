import os
import re
import json
import anthropic
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Profile(BaseModel):
    """User profile containing skills, experience, and preferences."""
    name: str
    title: str
    years_experience: int
    skills: list[str]
    education: list[str]
    work_history: list[dict]
    preferred_locations: list[str] = []
    remote_preference: str = "remote" 
    min_salary: int | None = None
    max_commute_minutes: int | None = None
    industries: list[str] = []
    summary: str = ""

    def to_prompt_context(self) -> str:
        """Convert profile to a clean JSON string for Claude."""
        return self.model_dump_json(indent=2, exclude_none=True)


class ProfileManager:
    """Handles loading, saving, and auto-generating profiles using Claude."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            print("⚠️ Warning: No Anthropic API Key found. Profile generation will fail.")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model_id = "claude-sonnet-4-6"

    def create_profile_from_resume(self, resume_text: str) -> Profile:
        """Use Claude to parse a raw resume and turn it into a Profile object."""
        if not self.api_key:
            raise ValueError("API Key is missing. Please add ANTHROPIC_API_KEY to your .env file.")

        prompt = f"""
        Extract information from this resume into a structured JSON format. 
        Ensure 'years_experience' is an integer.
        
        Resume Content:
        {resume_text}

        Return only valid JSON matching this schema:
        {{
            "name": "Full Name",
            "title": "Current Professional Title",
            "years_experience": integer,
            "skills": ["skill1", "skill2"],
            "education": ["degree and school"],
            "work_history": [
                {{"title": "Role", "company": "Company", "duration": "Years", "description": "Short summary"}}
            ],
            "summary": "Brief professional bio"
        }}
        """
        
        try:
            response = self.client.messages.create(
                model=self.model_id,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )

            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', response.content[0].text.strip())
            data = json.loads(text)
            
            # Add default preferences that aren't usually in a resume
            data.setdefault("preferred_locations", [])
            data.setdefault("remote_preference", "flexible")
            
            return Profile(**data)
        except Exception as e:
            print(f"❌ Error parsing resume with Claude: {e}")
            raise

def load_profile(path: str | Path) -> Profile:
    with open(path) as f:
        return Profile(**json.load(f))

def save_profile(profile: Profile, path: str | Path) -> None:
    with Path(path).open("w") as f:
        f.write(profile.model_dump_json(indent=2))