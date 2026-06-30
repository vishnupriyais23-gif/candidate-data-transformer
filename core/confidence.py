from typing import List, Dict, Any, Optional

def calculate_field_confidence(
    contributions: List[Dict[str, Any]],
    resolved_value: Any
) -> float:
    """
    Calculates confidence score for a single-value field.
    base_score = source trust level (0.45 - 0.85) of the resolved value's source
    bonus: +0.10 if value confirmed by 2+ sources
    penalty: -0.15 if value conflicts across sources (different non-null values)
    penalty: -0.10 if resolved value was extracted via heuristic/regex
    floor/cap: 0.0 to 1.0
    """
    if not contributions or resolved_value is None:
        return 0.0

    # Find the contribution that matches the resolved value and has the highest trust
    resolved_contrib = None
    for c in contributions:
        if c["value"] == resolved_value:
            if resolved_contrib is None or c["trust"] > resolved_contrib["trust"]:
                resolved_contrib = c

    if not resolved_contrib:
        resolved_contrib = contributions[0]

    base_score = resolved_contrib["trust"]
    score = base_score

    # Check for confirmation: same value from other sources
    unique_confirming_sources = set(
        c["source"] for c in contributions
        if c["value"] == resolved_value
    )
    if len(unique_confirming_sources) >= 2:
        score += 0.10

    # Check for conflict: different non-null values from other sources
    has_conflict = False
    for c in contributions:
        if c["value"] is not None and c["value"] != resolved_value:
            has_conflict = True
            break
    if has_conflict:
        score -= 0.15

    # Check for heuristic/regex penalty (-0.10)
    if resolved_contrib.get("method") in ["regex", "heuristic"]:
        score -= 0.10

    return max(0.0, min(1.0, round(score, 3)))


def calculate_skill_confidence(contributions: List[Dict[str, Any]]) -> float:
    """
    Calculates confidence for an individual skill.
    base_score = max trust of the contributing sources
    bonus: +0.10 if confirmed by 2+ sources
    penalty: -0.10 if only extracted via heuristic/regex (no direct_extract or api source)
    """
    if not contributions:
        return 0.0

    max_contrib = max(contributions, key=lambda c: c["trust"])
    base_score = max_contrib.get("confidence") if max_contrib.get("confidence") is not None else max_contrib["trust"]
    score = base_score

    unique_sources = set(c["source"] for c in contributions)
    if len(unique_sources) >= 2:
        score += 0.10

    # If all sources are heuristic or regex, apply penalty (-0.10)
    all_heuristic = all(c.get("method") in ["regex", "heuristic"] for c in contributions)
    if all_heuristic:
        score -= 0.10

    return max(0.0, min(1.0, round(score, 3)))


def calculate_overall_confidence(field_confidences: Dict[str, float]) -> float:
    """
    Calculates overall confidence as a weighted average of field confidences.
    Required fields (full_name, emails) are weighted higher (2.0), others are 1.0.
    Ensures result is strictly between 0.0 and 1.0.
    """
    weights = {
        "full_name": 2.0,
        "emails": 2.0,
        "phones": 1.0,
        "location": 1.0,
        "links": 1.0,
        "headline": 1.0,
        "years_experience": 1.0,
        "skills": 1.0,
        "experience": 1.0,
        "education": 1.0
    }

    total_weight = 0.0
    weighted_sum = 0.0

    for field, score in field_confidences.items():
        weight = weights.get(field, 1.0)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0.0:
        return 0.0

    overall = weighted_sum / total_weight
    return max(0.0, min(1.0, round(overall, 3)))
