"""
Unit tests for agent logic using mocked LLM responses.
Run with: python -m pytest tests/ -v
"""
import json
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_PROFILE = {
    "name": "Frase",
    "domain": "frase.io",
    "industry": "SEO Content Tools",
    "description": "AI-powered content briefs and SEO research",
    "competitors": ["surferseo.com", "marketmuse.com", "clearscope.io"],
}


# ── Agent 1 Tests ────────────────────────────────────────────────────────────

class TestQueryDiscoveryAgent:
    def _make_agent(self, mock_response: dict):
        from app.agents.discovery import QueryDiscoveryAgent
        agent = QueryDiscoveryAgent.__new__(QueryDiscoveryAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=(json.dumps(mock_response), 500))
        return agent

    def test_returns_queries_list(self):
        mock = {"queries": [
            {"query_text": "best SEO content tool", "query_type": "best_of", "commercial_intent": "high"},
            {"query_text": "Frase vs Surfer SEO", "query_type": "comparison", "commercial_intent": "high"},
        ]}
        agent = self._make_agent(mock)
        queries, tokens = agent.run(SAMPLE_PROFILE)
        assert len(queries) == 2
        assert queries[0]["query_text"] == "best SEO content tool"
        assert tokens == 500

    def test_filters_empty_query_text(self):
        mock = {"queries": [
            {"query_text": "valid query", "query_type": "best_of", "commercial_intent": "high"},
            {"query_text": "", "query_type": "informational", "commercial_intent": "low"},
            {"query_text": None, "query_type": "informational"},
        ]}
        agent = self._make_agent(mock)
        queries, _ = agent.run(SAMPLE_PROFILE)
        assert len(queries) == 1

    def test_handles_malformed_json_with_fallback(self):
        from app.agents.discovery import QueryDiscoveryAgent
        agent = QueryDiscoveryAgent.__new__(QueryDiscoveryAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=("not json at all %%$$", 100))
        queries, _ = agent.run(SAMPLE_PROFILE)
        assert queries == []

    def test_handles_missing_queries_key(self):
        mock = {"something_else": []}
        agent = self._make_agent(mock)
        queries, _ = agent.run(SAMPLE_PROFILE)
        assert queries == []


# ── Agent 2 Tests ────────────────────────────────────────────────────────────

SAMPLE_SERP_DATA = {
    "domain_in_serp": False,
    "serp_position": None,
    "competitive_difficulty": 40,
    "estimated_search_volume": 5000,
    "total_results": 50_000_000,
    "ads_count": 3,
    "has_knowledge_graph": False,
}


class TestVisibilityScoringAgent:
    def _make_agent(self, mock_response: dict):
        from app.agents.scoring import VisibilityScoringAgent
        agent = VisibilityScoringAgent.__new__(VisibilityScoringAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=(json.dumps(mock_response), 300))
        return agent

    def test_scores_non_visible_query(self):
        mock = {
            "domain_visible": False,
            "visibility_position": None,
            "visibility_reasoning": "Frase.io is not well-known enough to appear.",
            "visibility_confidence": "high",
        }
        agent = self._make_agent(mock)
        result, tokens = agent.run(
            query_text="best AI SEO tool",
            domain="frase.io",
            industry="SEO Content Tools",
            competitors=["surferseo.com"],
            serp_data=SAMPLE_SERP_DATA,
        )
        assert result["domain_visible"] is False
        assert result["visibility_position"] is None
        assert result["opportunity_score"] > 0.0
        assert tokens == 300

    def test_scores_visible_query(self):
        mock = {
            "domain_visible": True,
            "visibility_position": 2,
            "visibility_reasoning": "Frase.io is commonly mentioned.",
            "visibility_confidence": "medium",
        }
        serp_visible = {**SAMPLE_SERP_DATA, "domain_in_serp": True, "serp_position": 2,
                        "estimated_search_volume": 1000, "competitive_difficulty": 30}
        agent = self._make_agent(mock)
        result, _ = agent.run(
            query_text="frase io review",
            domain="frase.io",
            industry="SEO Content Tools",
            competitors=[],
            serp_data=serp_visible,
        )
        assert result["domain_visible"] is True
        assert result["visibility_position"] == 2
        assert result["opportunity_score"] < 0.5  # visible query has lower opportunity

    def test_opportunity_score_in_range(self):
        mock = {"domain_visible": False, "visibility_position": None,
                "visibility_reasoning": "n/a", "visibility_confidence": "low"}
        agent = self._make_agent(mock)
        low_serp = {**SAMPLE_SERP_DATA, "estimated_search_volume": 0, "competitive_difficulty": 100}
        result, _ = agent.run("test query", "frase.io", "SEO", [], low_serp)
        assert 0.0 <= result["opportunity_score"] <= 1.0

    def test_handles_malformed_json_with_fallback(self):
        from app.agents.scoring import VisibilityScoringAgent
        agent = VisibilityScoringAgent.__new__(VisibilityScoringAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=("INVALID JSON", 100))
        result, _ = agent.run("test", "frase.io", "SEO", [], SAMPLE_SERP_DATA)
        assert result["domain_visible"] is False  # fallback value
        assert "opportunity_score" in result


# ── Agent 3 Tests ────────────────────────────────────────────────────────────

class TestContentRecommendationAgent:
    def _make_agent(self, mock_response: dict):
        from app.agents.recommendation import ContentRecommendationAgent
        agent = ContentRecommendationAgent.__new__(ContentRecommendationAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=(json.dumps(mock_response), 400))
        return agent

    def test_returns_recommendations(self):
        mock = {"recommendations": [{
            "target_query_index": 0,
            "content_type": "blog_post",
            "title": "Frase vs Surfer SEO: Complete 2025 Comparison",
            "rationale": "Direct comparison content gets cited by AI assistants.",
            "target_keywords": ["frase vs surfer seo", "seo content tool comparison"],
            "priority": "high",
            "estimated_word_count": 2000,
        }]}
        target_queries = [{"query_text": "frase vs surfer seo", "opportunity_score": 0.82, "query_uuid": "uuid-1"}]
        agent = self._make_agent(mock)
        recs, tokens = agent.run(SAMPLE_PROFILE, target_queries)
        assert len(recs) == 1
        assert recs[0]["query_uuid"] == "uuid-1"
        assert recs[0]["content_type"] == "blog_post"
        assert tokens == 400

    def test_returns_empty_for_no_queries(self):
        from app.agents.recommendation import ContentRecommendationAgent
        agent = ContentRecommendationAgent.__new__(ContentRecommendationAgent)
        agent.total_tokens_used = 0
        recs, tokens = agent.run(SAMPLE_PROFILE, [])
        assert recs == []
        assert tokens == 0

    def test_skips_invalid_query_index(self):
        mock = {"recommendations": [{
            "target_query_index": 99,  # out of bounds
            "content_type": "blog_post",
            "title": "Some Title",
            "rationale": "Some rationale",
            "target_keywords": ["kw"],
            "priority": "high",
        }]}
        target_queries = [{"query_text": "query", "opportunity_score": 0.8, "query_uuid": "uuid-1"}]
        agent = self._make_agent(mock)
        recs, _ = agent.run(SAMPLE_PROFILE, target_queries)
        assert recs == []

    def test_handles_malformed_json_with_fallback(self):
        from app.agents.recommendation import ContentRecommendationAgent
        agent = ContentRecommendationAgent.__new__(ContentRecommendationAgent)
        agent.total_tokens_used = 0
        agent._chat = MagicMock(return_value=("BAD JSON", 100))
        recs, _ = agent.run(SAMPLE_PROFILE, [{"query_text": "q", "opportunity_score": 0.5, "query_uuid": "u"}])
        assert recs == []


# ── Opportunity Score Tests ───────────────────────────────────────────────────

class TestOpportunityScoreFormula:
    def test_high_volume_not_visible_high_intent_scores_high(self):
        from app.utils.scoring import calculate_opportunity_score
        score = calculate_opportunity_score(
            search_volume=9000,
            competitive_difficulty=20,
            domain_visible=False,
            visibility_position=None,
            query_text="best SEO content tool vs competitors",
        )
        assert score >= 0.8

    def test_zero_volume_scores_low(self):
        from app.utils.scoring import calculate_opportunity_score
        score = calculate_opportunity_score(
            search_volume=0,
            competitive_difficulty=80,
            domain_visible=True,
            visibility_position=1,
            query_text="what is seo",
        )
        assert score < 0.4

    def test_score_always_in_range(self):
        from app.utils.scoring import calculate_opportunity_score
        for vol in [0, 100, 5000, 50000]:
            for diff in [0, 50, 100]:
                score = calculate_opportunity_score(vol, diff, False, None, "test query")
                assert 0.0 <= score <= 1.0

    def test_not_visible_scores_higher_than_visible(self):
        from app.utils.scoring import calculate_opportunity_score
        visible = calculate_opportunity_score(1000, 50, True, 2, "best tool")
        not_visible = calculate_opportunity_score(1000, 50, False, None, "best tool")
        assert not_visible > visible
