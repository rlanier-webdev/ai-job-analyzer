import os
import json
from pathlib import Path
from pydantic import BaseModel
from openai import OpenAI
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
        """Convert profile to a clean JSON string for OpenAI."""
        return self.model_dump_json(indent=2, exclude_none=True)


class ProfileManager:
    """Handles loading, saving, and auto-generating profiles using OpenAI GPT-4."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            print("⚠️ Warning: No OpenAI API Key found. Profile generation will fail.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model_id = "gpt-4o"

    def create_profile_from_resume(self, resume_text: str) -> Profile:
        """Use OpenAI GPT-4 to parse a raw resume and turn it into a Profile object."""
        if not self.api_key:
            raise ValueError("API Key is missing. Please add OPENAI_API_KEY to your .env file.")

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
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            data = json.loads(response.choices[0].message.content)
            
            # Add default preferences that aren't usually in a resume
            data.setdefault("preferred_locations", [])
            data.setdefault("remote_preference", "flexible")
            
            return Profile(**data)
        except Exception as e:
            print(f"❌ Error parsing resume with OpenAI: {e}")
            raise

def load_profile(path: str | Path) -> Profile:
    with open(path) as f:
        return Profile(**json.load(f))

def save_profile(profile: Profile, path: str | Path) -> None:
    with Path(path).open("w") as f:
        f.write(profile.model_dump_json(indent=2))