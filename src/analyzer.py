import os
import json
from dataclasses import dataclass, asdict
from openai import OpenAI
from dotenv import load_dotenv

from .parser import JobPosting
from .profile import Profile

load_dotenv()

@dataclass
class JobAnalysis:
    """Results of analyzing a job posting against a profile."""
    qualification_score: int
    qualification_summary: str
    matching_skills: list[str]
    missing_skills: list[str]
    should_apply: bool
    apply_reasoning: str
    salary_assessment: str
    salary_recommendation: str
    red_flags: list[str]
    green_flags: list[str]
    interview_tips: list[str]
    overall_recommendation: str

    def model_dump(self):
        return asdict(self)

class JobAnalyzer:
    """Analyze job postings using OpenAI GPT-4."""

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model_id = "gpt-4o"

    def analyze(self, job: JobPosting, profile: Profile) -> JobAnalysis:
        prompt = self._build_analysis_prompt(job, profile)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            data = json.loads(response.choices[0].message.content)
            analysis = JobAnalysis(**data)

            # Check if missing too many skills
            analysis = self._apply_skill_threshold(analysis)

            return analysis
            
        except Exception as e:
            print(f"❌ OpenAI Analysis Error: {e}")
            return self._get_empty_analysis(str(e))

    def _apply_skill_threshold(self, analysis: JobAnalysis) -> JobAnalysis:
        """Don't recommend applying if missing 50% or more skills"""
        total_skills = len(analysis.matching_skills) + len(analysis.missing_skills)

        # Avoid dividing by zero if no skills found
        if total_skills == 0:
            return analysis
        
        missing_percentage = len(analysis.missing_skills) / total_skills * 100

        if missing_percentage >= 50 and analysis.qualification_score < 70:
            missing_list = ', '.join(analysis.missing_skills)

            analysis.should_apply = False
            analysis.apply_reasoning = (
                f"You're missing {missing_percentage:.0f}% of the required skills. "
            )
            analysis.overall_recommendation = (
                f"We don't recommend applying. Focus on learning: {missing_list}"
            )
            analysis.interview_tips = [
                f"Consider learning {skill} before applying to similar roles"
                for skill in analysis.missing_skills
            ]
            analysis.salary_recommendation = "N/A - Not recommended to apply"
        
        return analysis

    def _build_analysis_prompt(self, job: JobPosting, profile: Profile) -> str:
        return f"""Analyze this job for the candidate. Return JSON.
        
        CANDIDATE: {profile.to_prompt_context()}
        JOB: {job.to_prompt_context()}

        INSTRUCTIONS:
        - qualification_score should be 0-100, weighing skills match, years of experience, relevant job history, education, and certifications
        
        JSON Schema:
        {{
            "qualification_score": integer,
            "qualification_summary": "string",
            "matching_skills": ["string"],
            "missing_skills": ["string"],
            "should_apply": boolean,
            "apply_reasoning": "string",
            "salary_assessment": "string",
            "salary_recommendation": "string",
            "red_flags": ["string"],
            "green_flags": ["string"],
            "interview_tips": ["string"],
            "overall_recommendation": "string"
        }}"""

    def _get_empty_analysis(self, error_msg: str) -> JobAnalysis:
        return JobAnalysis(0, f"Error: {error_msg}", [], [], False, "N/A", "N/A", "N/A", ["API Error"], [], [], "Analysis failed.")