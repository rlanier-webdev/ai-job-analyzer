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

    USA_LOCATION_TERMS = {"usa", "us", "united states", "america", "worldwide", "anywhere"}

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
        title = profile.title or ""
        stopwords = {
            "senior", "sr", "junior", "jr", "lead", "principal", "staff",
            "associate", "entry", "mid", "level", "i", "ii", "iii", "iv",
            "manager", "director", "head", "chief", "vp",
        }
        words = [w for w in title.split() if w.lower() not in stopwords]
        return " ".join(words[:3]) if words else title

    def _is_usa_eligible(self, location: str) -> bool:
        loc = location.lower().strip()
        if not loc:
            return True
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


class GreenhouseSearcher:
    """Fetches open jobs directly from a company's public Greenhouse job board."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    def search(self, company_slug: str) -> list[SearchResult]:
        try:
            response = requests.get(
                self.BASE_URL.format(slug=company_slug),
                params={"content": "true"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []
        jobs = response.json().get("jobs", [])
        return [self._to_result(j, company_slug) for j in jobs]

    def _to_result(self, job: dict, company_slug: str) -> SearchResult:
        raw_description = job.get("content", "")
        snippet = BeautifulSoup(raw_description, "html.parser").get_text()[:500].strip()
        return SearchResult(
            title=job.get("title", ""),
            company=company_slug,
            location=(job.get("location") or {}).get("name", "Remote"),
            salary="",
            remote_policy="remote",
            url=job.get("absolute_url", ""),
            description_snippet=snippet,
            tags=[],
        )


class AshbySearcher:
    """Fetches open jobs directly from a company's public Ashby job board."""

    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

    def search(self, company_slug: str) -> list[SearchResult]:
        try:
            response = requests.get(self.BASE_URL.format(slug=company_slug), timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            return []
        jobs = response.json().get("jobs", [])
        return [self._to_result(j, company_slug) for j in jobs]

    def _to_result(self, job: dict, company_slug: str) -> SearchResult:
        raw_description = job.get("descriptionHtml", "")
        snippet = BeautifulSoup(raw_description, "html.parser").get_text()[:500].strip()
        return SearchResult(
            title=job.get("title", ""),
            company=company_slug,
            location=job.get("location", "Remote"),
            salary="",
            remote_policy="remote",
            url=job.get("jobUrl", ""),
            description_snippet=snippet,
            tags=[],
        )
