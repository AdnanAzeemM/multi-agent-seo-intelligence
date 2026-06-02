import logging
from datetime import datetime, timezone

from ..extensions import db
from ..models import BusinessProfile, PipelineRun, DiscoveredQuery, ContentRecommendation
from ..agents import QueryDiscoveryAgent, VisibilityScoringAgent, ContentRecommendationAgent
from ..utils.serpapi import get_serp_data

logger = logging.getLogger(__name__)


def run_pipeline(profile: BusinessProfile) -> PipelineRun:
    """
    Orchestrates the 3-agent pipeline for a given business profile.
    Agent 1 → SerpAPI (per query) → Agent 2 (per query, skips failures) → Agent 3
    Persists all results and returns the completed PipelineRun.
    """
    pipeline_run = PipelineRun(profile_uuid=profile.uuid, status="running")
    db.session.add(pipeline_run)
    db.session.commit()
    logger.info("[run=%s] Pipeline started for domain=%s", pipeline_run.uuid, profile.domain)

    total_tokens = 0
    profile_dict = {
        "name": profile.name,
        "domain": profile.domain,
        "industry": profile.industry,
        "description": profile.description,
        "competitors": profile.competitors or [],
    }

    try:
        # ── Agent 1: Query Discovery ──────────────────────────────────────────
        logger.info("[run=%s] Agent 1: discovering queries", pipeline_run.uuid)
        discovery_agent = QueryDiscoveryAgent()
        raw_queries, tokens1 = discovery_agent.run(profile_dict)
        total_tokens += tokens1

        if not raw_queries:
            raise RuntimeError("Agent 1 returned no queries")

        # Persist discovered queries (pre-scoring)
        saved_queries: list[DiscoveredQuery] = []
        for q in raw_queries:
            dq = DiscoveredQuery(
                profile_uuid=profile.uuid,
                run_uuid=pipeline_run.uuid,
                query_text=q["query_text"],
                query_type=q.get("query_type", "informational"),
            )
            db.session.add(dq)
            saved_queries.append(dq)

        db.session.flush()
        pipeline_run.queries_discovered = len(saved_queries)
        db.session.commit()
        logger.info("[run=%s] Agent 1: saved %d queries", pipeline_run.uuid, len(saved_queries))

        # ── SerpAPI + Agent 2: Visibility Scoring (per query) ────────────────
        logger.info("[run=%s] Agent 2: scoring %d queries via SerpAPI + GPT-4o", pipeline_run.uuid, len(saved_queries))
        scoring_agent = VisibilityScoringAgent()
        scored_count = 0

        for dq in saved_queries:
            try:
                # Real SERP data for this query
                serp_data = get_serp_data(query=dq.query_text, domain=profile.domain)

                # GPT-4o assesses AI visibility using SERP context
                score_result, tokens2 = scoring_agent.run(
                    query_text=dq.query_text,
                    domain=profile.domain,
                    industry=profile.industry,
                    competitors=profile.competitors or [],
                    serp_data=serp_data,
                )
                total_tokens += tokens2

                dq.estimated_search_volume = score_result["estimated_search_volume"]
                dq.competitive_difficulty = score_result["competitive_difficulty"]
                dq.domain_visible = score_result["domain_visible"]
                dq.visibility_position = score_result["visibility_position"]
                dq.visibility_reasoning = score_result["visibility_reasoning"]
                dq.visibility_confidence = score_result["visibility_confidence"]
                dq.opportunity_score = score_result["opportunity_score"]
                dq.last_checked_at = datetime.now(timezone.utc)
                scored_count += 1

            except Exception as e:
                # Partial failure: log and continue — do not crash the pipeline
                logger.error(
                    "[run=%s] Agent 2 failed for query '%s': %s",
                    pipeline_run.uuid,
                    dq.query_text[:60],
                    e,
                )

        pipeline_run.queries_scored = scored_count
        db.session.commit()
        logger.info("[run=%s] Agent 2: scored %d/%d queries", pipeline_run.uuid, scored_count, len(saved_queries))

        # ── Agent 3: Content Recommendations ─────────────────────────────────
        non_visible = sorted(
            [
                dq for dq in saved_queries
                if dq.domain_visible is False
                or (dq.domain_visible is True and (dq.visibility_position or 0) > 5)
            ],
            key=lambda x: x.opportunity_score,
            reverse=True,
        )[:10]

        # Fallback: if domain is visible everywhere, use lowest-scored queries as improvement targets
        if not non_visible:
            non_visible = sorted(saved_queries, key=lambda x: x.opportunity_score)[:5]
            logger.info("[run=%s] Agent 3: all queries visible — using bottom 5 by score as improvement targets", pipeline_run.uuid)

        logger.info("[run=%s] Agent 3: generating recommendations for %d queries", pipeline_run.uuid, len(non_visible))
        rec_agent = ContentRecommendationAgent()
        agent3_input = [
            {"query_text": dq.query_text, "opportunity_score": dq.opportunity_score, "query_uuid": dq.uuid}
            for dq in non_visible
        ]
        raw_recs, tokens3 = rec_agent.run(profile_dict, agent3_input)
        total_tokens += tokens3

        for rec in raw_recs:
            cr = ContentRecommendation(
                profile_uuid=profile.uuid,
                query_uuid=rec["query_uuid"],
                run_uuid=pipeline_run.uuid,
                content_type=rec.get("content_type", "blog_post"),
                title=rec.get("title", ""),
                rationale=rec.get("rationale", ""),
                target_keywords=rec.get("target_keywords", []),
                priority=rec.get("priority", "medium"),
                estimated_word_count=rec.get("estimated_word_count"),
            )
            db.session.add(cr)

        # ── Finalize ──────────────────────────────────────────────────────────
        pipeline_run.status = "completed"
        pipeline_run.tokens_used = total_tokens
        pipeline_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("[run=%s] Pipeline completed. tokens_used=%d", pipeline_run.uuid, total_tokens)

    except Exception as e:
        logger.exception("[run=%s] Pipeline failed: %s", pipeline_run.uuid, e)
        pipeline_run.status = "failed"
        pipeline_run.error_message = str(e)
        pipeline_run.tokens_used = total_tokens
        pipeline_run.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    return pipeline_run
