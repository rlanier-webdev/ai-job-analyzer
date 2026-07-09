"""Tests for /api/search endpoint — covers event loop and error handling."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


def make_search_result():
    from src.searcher import SearchResult
    return SearchResult(
        title="Software Engineer", company="Acme", location="USA Only",
        salary="$100k", remote_policy="remote", url="https://example.com/job/1",
        description_snippet="We are hiring", tags=["python"],
    )


def make_analysis(score=80):
    from src.analyzer import JobAnalysis
    return JobAnalysis(
        qualification_score=score, qualification_summary="Good match",
        matching_skills=["Python"], missing_skills=[],
        should_apply=True, apply_reasoning="Strong match",
        salary_assessment="Fair", salary_recommendation="Negotiate",
        red_flags=[], green_flags=["Remote"], interview_tips=["Prepare"],
        overall_recommendation="Apply",
    )


class TestSearchEndpoint:
    def setup_method(self):
        from src.web import app, global_data
        from src.profile import Profile
        self.client = TestClient(app)
        global_data["profile"] = Profile(
            name="Test", title="Software Engineer", years_experience=5,
            skills=["Python"], education=[], work_history=[],
            remote_preference="remote",
        )

    def test_search_returns_jobs_above_threshold(self):
        result = make_search_result()
        analysis_high = make_analysis(score=80)
        analysis_low = make_analysis(score=50)

        with patch("src.web.searcher.search", return_value=[result, result]), \
             patch("src.web.greenhouse_searcher.search", return_value=[]), \
             patch("src.web.ashby_searcher.search", return_value=[]), \
             patch("src.web.analyzer.analyze", side_effect=[analysis_high, analysis_low]):
            response = self.client.post("/api/search")

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["score"] == 80

    def test_search_requires_profile(self):
        from src.web import global_data
        global_data["profile"] = None
        response = self.client.post("/api/search")
        assert response.status_code == 400
        assert "profile" in response.json()["detail"].lower()

    def test_search_results_sorted_by_score_descending(self):
        result = make_search_result()
        analyses = [make_analysis(score=s) for s in [76, 90, 82]]

        with patch("src.web.searcher.search", return_value=[result, result, result]), \
             patch("src.web.greenhouse_searcher.search", return_value=[]), \
             patch("src.web.ashby_searcher.search", return_value=[]), \
             patch("src.web.analyzer.analyze", side_effect=analyses):
            response = self.client.post("/api/search")

        scores = [j["score"] for j in response.json()["jobs"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_returns_query_used(self):
        with patch("src.web.searcher.search", return_value=[]), \
             patch("src.web.greenhouse_searcher.search", return_value=[]), \
             patch("src.web.ashby_searcher.search", return_value=[]), \
             patch("src.web.searcher.build_query", return_value="Software Engineer"):
            response = self.client.post("/api/search")

        assert response.status_code == 200
        assert "query_used" in response.json()
