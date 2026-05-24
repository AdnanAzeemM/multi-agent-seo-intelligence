from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import BusinessProfile, PipelineRun, DiscoveredQuery, ContentRecommendation
from ..services.pipeline import run_pipeline

profiles_bp = Blueprint("profiles", __name__)

REQUIRED_FIELDS = ["name", "domain", "industry"]


def _error(message: str, code: int):
    return jsonify({"error": message, "code": code}), code


# ── GET /api/v1/profiles ─────────────────────────────────────────────────────

@profiles_bp.get("/profiles")
def list_profiles():
    profiles = BusinessProfile.query.order_by(BusinessProfile.created_at.desc()).all()
    return jsonify({
        "profiles": [p.to_dict() for p in profiles],
        "total": len(profiles),
    }), 200


# ── POST /api/v1/profiles ────────────────────────────────────────────────────

@profiles_bp.post("/profiles")
def create_profile():
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be valid JSON", 400)

    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        return _error(f"Missing required fields: {', '.join(missing)}", 422)

    if not isinstance(data.get("competitors", []), list):
        return _error("'competitors' must be a list of domain strings", 422)

    existing = BusinessProfile.query.filter_by(domain=data["domain"]).first()
    if existing:
        return _error(f"Profile for domain '{data['domain']}' already exists", 409)

    profile = BusinessProfile(
        name=data["name"],
        domain=data["domain"],
        industry=data["industry"],
        description=data.get("description"),
        competitors=data.get("competitors", []),
    )
    db.session.add(profile)
    db.session.commit()

    return jsonify({
        "profile_uuid": profile.uuid,
        "name": profile.name,
        "domain": profile.domain,
        "status": profile.status,
        "created_at": profile.created_at.isoformat(),
    }), 201


# ── GET /api/v1/profiles/<uuid> ──────────────────────────────────────────────

@profiles_bp.get("/profiles/<string:profile_uuid>")
def get_profile(profile_uuid: str):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return _error("Profile not found", 404)

    total_queries = DiscoveredQuery.query.filter_by(profile_uuid=profile_uuid).count()
    avg_score = db.session.query(func.avg(DiscoveredQuery.opportunity_score)).filter_by(
        profile_uuid=profile_uuid
    ).scalar()
    visible_count = DiscoveredQuery.query.filter_by(profile_uuid=profile_uuid, domain_visible=True).count()
    total_runs = PipelineRun.query.filter_by(profile_uuid=profile_uuid).count()

    result = profile.to_dict()
    result["stats"] = {
        "total_queries": total_queries,
        "avg_opportunity_score": round(float(avg_score), 4) if avg_score else 0.0,
        "visible_queries": visible_count,
        "not_visible_queries": total_queries - visible_count,
        "total_runs": total_runs,
    }
    return jsonify(result), 200


# ── POST /api/v1/profiles/<uuid>/run ────────────────────────────────────────

@profiles_bp.post("/profiles/<string:profile_uuid>/run")
def trigger_pipeline(profile_uuid: str):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return _error("Profile not found", 404)

    active_run = PipelineRun.query.filter_by(profile_uuid=profile_uuid, status="running").first()
    if active_run:
        return _error("A pipeline run is already in progress for this profile", 409)

    pipeline_run = run_pipeline(profile)

    # Top 3 queries by opportunity score
    top_queries = (
        DiscoveredQuery.query
        .filter_by(run_uuid=pipeline_run.uuid)
        .order_by(DiscoveredQuery.opportunity_score.desc())
        .limit(3)
        .all()
    )

    recommendations = ContentRecommendation.query.filter_by(run_uuid=pipeline_run.uuid).all()

    return jsonify({
        "run_uuid": pipeline_run.uuid,
        "profile_uuid": profile.uuid,
        "status": pipeline_run.status,
        "queries_discovered": pipeline_run.queries_discovered,
        "queries_scored": pipeline_run.queries_scored,
        "tokens_used": pipeline_run.tokens_used,
        "top_3_queries": [
            {
                "query_uuid": q.uuid,
                "query_text": q.query_text,
                "opportunity_score": q.opportunity_score,
                "domain_visible": q.domain_visible,
                "estimated_search_volume": q.estimated_search_volume,
                "competitive_difficulty": q.competitive_difficulty,
            }
            for q in top_queries
        ],
        "recommendations": [r.to_dict() for r in recommendations],
        "error_message": pipeline_run.error_message,
        "started_at": pipeline_run.started_at.isoformat(),
        "completed_at": pipeline_run.completed_at.isoformat() if pipeline_run.completed_at else None,
    }), 200


# ── GET /api/v1/profiles/<uuid>/queries ─────────────────────────────────────

@profiles_bp.get("/profiles/<string:profile_uuid>/queries")
def get_queries(profile_uuid: str):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return _error("Profile not found", 404)

    query = DiscoveredQuery.query.filter_by(profile_uuid=profile_uuid)

    min_score = request.args.get("min_score", type=float)
    if min_score is not None:
        query = query.filter(DiscoveredQuery.opportunity_score >= min_score)

    status_filter = request.args.get("status")
    if status_filter == "visible":
        query = query.filter(DiscoveredQuery.domain_visible == True)
    elif status_filter == "not_visible":
        query = query.filter(DiscoveredQuery.domain_visible == False)
    elif status_filter == "unknown":
        query = query.filter(DiscoveredQuery.domain_visible == None)

    query = query.order_by(DiscoveredQuery.opportunity_score.desc())

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "queries": [q.to_dict() for q in paginated.items],
        "pagination": {
            "page": paginated.page,
            "per_page": per_page,
            "total": paginated.total,
            "pages": paginated.pages,
        },
    }), 200


# ── GET /api/v1/profiles/<uuid>/recommendations ──────────────────────────────

@profiles_bp.get("/profiles/<string:profile_uuid>/recommendations")
def get_recommendations(profile_uuid: str):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return _error("Profile not found", 404)

    recs = (
        ContentRecommendation.query
        .filter_by(profile_uuid=profile_uuid)
        .order_by(ContentRecommendation.created_at.desc())
        .all()
    )
    return jsonify({"recommendations": [r.to_dict() for r in recs]}), 200
