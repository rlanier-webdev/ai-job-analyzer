import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from .profile import Profile


class SearchResult(BaseModel):
    title: str
    company: str
    location: str
    salary: str
    remote_policy: str
    url: str
    description_snippet: str
    tags: list[str]


class JobSearcher:
    REMOTIVE_URL = "https://remotive.com/api/remote-jobs"

    USA_LOCATION_TERMS = {"usa", "us", "united states", "america", "worldwide", "anywhere", ""}

    def search(self, profile: Profile, limit: int = 20) -> list[SearchResult]:
        query = self.build_query(profile)
        response = requests.get(
            self.REMOTIVE_URL,
            params={"search": query, "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
        results = [self._to_result(j) for j in jobs]
        return [r for r in results if self._is_usa_eligible(r.location)]

    def build_query(self, profile: Profile) -> str:
        return profile.title

    def _is_usa_eligible(self, location: str) -> bool:
        loc = location.lower().strip()
        return any(term in loc for term in self.USA_LOCATION_TERMS)

    def _to_result(self, job: dict) -> SearchResult:
        raw_description = job.get("description", "")
        snippet = BeautifulSoup(raw_description, "html.parser").get_text()[:500].strip()
        return SearchResult(
            title=job.get("title", ""),
            company=job.get("company_name", ""),
            location=job.get("candidate_required_location", "Remote"),
            salary=job.get("salary", "") or "",
            remote_policy="remote",
            url=job.get("url", ""),
            description_snippet=snippet,
            tags=job.get("tags", []),
        )
