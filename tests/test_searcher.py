"""Tests for JobSearcher — covers USA eligibility filtering."""
import pytest
from unittest.mock import patch, MagicMock
from src.searcher import JobSearcher, SearchResult
from src.profile import Profile


def make_profile(**kwargs):
    defaults = dict(
        name="Test User", title="Software Engineer", years_experience=5,
        skills=["Python", "SQL"], education=[], work_history=[],
        remote_preference="remote",
    )
    defaults.update(kwargs)
    return Profile(**defaults)


def make_remotive_job(**kwargs):
    defaults = dict(
        title="Software Engineer", company_name="Acme", salary="$100k",
        candidate_required_location="USA Only", url="https://example.com/job/1",
        description="<p>We are hiring</p>", tags=["python"],
        job_type="full-time",
    )
    defaults.update(kwargs)
    return defaults


class TestJobSearcherUSAFilter:
    def setup_method(self):
        self.searcher = JobSearcher()

    def test_usa_location_passes(self):
        assert self.searcher._is_usa_eligible("USA Only") is True

    def test_us_location_passes(self):
        assert self.searcher._is_usa_eligible("US") is True

    def test_united_states_passes(self):
        assert self.searcher._is_usa_eligible("United States") is True

    def test_worldwide_passes(self):
        assert self.searcher._is_usa_eligible("Worldwide") is True

    def test_anywhere_passes(self):
        assert self.searcher._is_usa_eligible("Anywhere") is True

    def test_empty_location_passes(self):
        assert self.searcher._is_usa_eligible("") is True

    def test_europe_only_filtered(self):
        assert self.searcher._is_usa_eligible("Europe Only") is False

    def test_uk_only_filtered(self):
        assert self.searcher._is_usa_eligible("UK Only") is False

    def test_canada_only_filtered(self):
        assert self.searcher._is_usa_eligible("Canada Only") is False

    def test_search_filters_non_usa_jobs(self):
        """Non-USA jobs must be excluded from search results."""
        jobs = [
            make_remotive_job(candidate_required_location="Europe Only"),
            make_remotive_job(candidate_required_location="USA Only"),
            make_remotive_job(candidate_required_location="UK Only"),
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"jobs": jobs}
        mock_response.raise_for_status = MagicMock()

        with patch("src.searcher.requests.get", return_value=mock_response):
            results = self.searcher.search(make_profile(), limit=10)

        assert len(results) == 1
        assert results[0].location == "USA Only"

    def test_build_query_uses_title_only(self):
        """Query must be the profile title — not title + skills (caused irrelevant results)."""
        profile = make_profile(title="Software Support Specialist", skills=["Python", "Go", "SQL"])
        assert self.searcher.build_query(profile) == "Software Support Specialist"

    def test_to_result_strips_html_from_description(self):
        """description_snippet must be plain text, not raw HTML."""
        job = make_remotive_job(description="<p><strong>We are hiring</strong></p>")
        result = self.searcher._to_result(job)
        assert "<" not in result.description_snippet
        assert "We are hiring" in result.description_snippet
