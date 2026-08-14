"""Deterministic insight generation for occupation ceiling data.

This module produces the "what this means" text for occupation ceiling data
without using LLMs, scoring, ranking, or personalized predictions.
(Design spec §7)
"""

_PACE_PHRASES = {
    "rising": "the points threshold has been rising over the last three rounds",
    "falling": "the points threshold has been falling over the last three rounds",
    "steady": "the points threshold has stayed steady over the last three rounds",
}


def generate_ceiling_insight(*, issued: int, ceiling: int, direction: str) -> str:
    """Deterministic template, keyed to the data — never an LLM call
    (design spec §7). No scoring, ranking, or personalized prediction.

    Args:
        issued: Number of positions issued from this occupation's ceiling
        ceiling: Total ceiling for this occupation this program year
        direction: Direction of threshold movement ("rising", "falling", "steady")

    Returns:
        A plain-language insight describing the ceiling usage and trend,
        using only factual statements with no migration advice.
    """
    places_left = ceiling - issued
    pct_used = round(issued / ceiling * 100)
    pace_phrase = _PACE_PHRASES.get(direction, _PACE_PHRASES["steady"])

    return (
        f"{pct_used}% of this occupation's ceiling has been issued this program year "
        f"({issued} of {ceiling}), leaving {places_left} places. "
        f"{pace_phrase.capitalize()}."
    )
