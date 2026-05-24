"""
Opportunity Score Formula (0.0 – 1.0)

Weights:
  35% — Search Volume   : normalized against 10,000 monthly searches
  25% — Ease Score      : inverse of keyword difficulty (low competition = easier win)
  25% — Visibility Gap  : max when domain is not visible at all
  15% — Commercial Intent: comparison/best-of queries score highest

Final score is clamped to [0.0, 1.0].
"""

HIGH_INTENT_SIGNALS = [
    "best", "vs", "versus", "compare", "comparison", "top", "review",
    "reviews", "alternative", "alternatives", "pricing", "cost", "buy",
    "purchase", "recommend", "recommended", "ranked", "ranking",
]

MEDIUM_INTENT_SIGNALS = [
    "how to", "guide", "tutorial", "tool", "software", "platform",
    "use", "using", "features", "benefits",
]


def detect_commercial_intent(query_text: str) -> float:
    text = query_text.lower()
    if any(signal in text for signal in HIGH_INTENT_SIGNALS):
        return 1.0
    if any(signal in text for signal in MEDIUM_INTENT_SIGNALS):
        return 0.6
    return 0.3


def calculate_opportunity_score(
    search_volume: int,
    competitive_difficulty: int,
    domain_visible: bool | None,
    visibility_position: int | None,
    query_text: str,
) -> float:
    # Factor 1: Volume (35%) — normalize against 10k cap
    volume_score = min(search_volume / 10_000, 1.0)

    # Factor 2: Ease (25%) — lower difficulty = easier to capture
    ease_score = 1.0 - (min(max(competitive_difficulty, 0), 100) / 100)

    # Factor 3: Visibility Gap (25%)
    if domain_visible is None or not domain_visible:
        visibility_gap = 1.0
    elif visibility_position and visibility_position > 5:
        visibility_gap = 0.5
    else:
        visibility_gap = 0.1

    # Factor 4: Commercial Intent (15%)
    intent_score = detect_commercial_intent(query_text)

    raw_score = (
        volume_score * 0.35
        + ease_score * 0.25
        + visibility_gap * 0.25
        + intent_score * 0.15
    )

    return round(min(max(raw_score, 0.0), 1.0), 4)
