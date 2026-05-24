import uuid
from datetime import datetime, timezone
from ..extensions import db


class DiscoveredQuery(db.Model):
    __tablename__ = "discovered_queries"

    uuid = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.uuid"), nullable=False)
    run_uuid = db.Column(db.String(36), db.ForeignKey("pipeline_runs.uuid"), nullable=False)
    query_text = db.Column(db.Text, nullable=False)
    query_type = db.Column(db.String(50), nullable=True)  # comparison|best_of|how_to|informational|pricing
    estimated_search_volume = db.Column(db.Integer, default=0)
    competitive_difficulty = db.Column(db.Integer, default=50)  # 0-100
    opportunity_score = db.Column(db.Float, default=0.0)  # 0.0-1.0
    domain_visible = db.Column(db.Boolean, nullable=True)
    visibility_position = db.Column(db.Integer, nullable=True)
    visibility_reasoning = db.Column(db.Text, nullable=True)
    visibility_confidence = db.Column(db.String(20), nullable=True)  # high|medium|low
    discovered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_checked_at = db.Column(db.DateTime, nullable=True)

    recommendations = db.relationship(
        "ContentRecommendation", backref="parent_query", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "query_uuid": self.uuid,
            "profile_uuid": self.profile_uuid,
            "run_uuid": self.run_uuid,
            "query_text": self.query_text,
            "query_type": self.query_type,
            "estimated_search_volume": self.estimated_search_volume,
            "competitive_difficulty": self.competitive_difficulty,
            "opportunity_score": self.opportunity_score,
            "domain_visible": self.domain_visible,
            "visibility_position": self.visibility_position,
            "visibility_reasoning": self.visibility_reasoning,
            "visibility_confidence": self.visibility_confidence,
            "discovered_at": self.discovered_at.isoformat(),
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
        }
