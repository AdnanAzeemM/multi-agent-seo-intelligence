import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from ..extensions import db
from ..models import DiscoveredQuery, BusinessProfile
from ..agents import VisibilityScoringAgent
from ..utils.serpapi import get_serp_data

logger = logging.getLogger(__name__)
queries_bp = Blueprint("queries", __name__)


def _error(message: str, code: int):
    return jsonify({"error": message, "code": code}), code


# ── POST /api/v1/queries/<uuid>/recheck ──────────────────────────────────────

@queries_bp.post("/queries/<string:query_uuid>/recheck")
def recheck_query(query_uuid: str):
    dq = DiscoveredQuery.query.get(query_uuid)
    if not dq:
        return _error("Query not found", 404)

    profile = BusinessProfile.query.get(dq.profile_uuid)
    if not profile:
        return _error("Associated profile not found", 404)

    try:
        serp_data = get_serp_data(query=dq.query_text, domain=profile.domain)

        agent = VisibilityScoringAgent()
        score_result, tokens = agent.run(
            query_text=dq.query_text,
            domain=profile.domain,
            industry=profile.industry,
            competitors=profile.competitors or [],
            serp_data=serp_data,
        )

        dq.estimated_search_volume = score_result["estimated_search_volume"]
        dq.competitive_difficulty = score_result["competitive_difficulty"]
        dq.domain_visible = score_result["domain_visible"]
        dq.visibility_position = score_result["visibility_position"]
        dq.visibility_reasoning = score_result["visibility_reasoning"]
        dq.visibility_confidence = score_result["visibility_confidence"]
        dq.opportunity_score = score_result["opportunity_score"]
        dq.last_checked_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            "query_uuid": dq.uuid,
            "query_text": dq.query_text,
            "serp_data": serp_data,
            "updated_scores": dq.to_dict(),
            "tokens_used": tokens,
        }), 200

    except Exception as e:
        logger.exception("Recheck failed for query %s: %s", query_uuid, e)
        return _error(f"Recheck failed: {str(e)}", 500)
