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


def generate_ceiling_insight(*, issued: int, ceiling: int, direction: str | None) -> str:
    """Deterministic template, keyed to the data — never an LLM call
    (design spec §7). No scoring, ranking, or personalized prediction.

    Args:
        issued: Number of positions issued from this occupation's ceiling
        ceiling: Total ceiling for this occupation this program year
        direction: Direction of threshold movement ("rising", "falling", "steady"),
            or None when fewer than three eoi_rounds exist yet. When None, the
            trend sentence is omitted entirely rather than fabricated — every
            generated string must describe a published fact, never an
            invented one.

    Returns:
        A plain-language insight describing the ceiling usage and, when a
        real trend is known, the trend — using only factual statements with
        no migration advice.

    Raises:
        ValueError: if ceiling <= 0 — such data is nonsensical (and would
            otherwise raise an unhandled ZeroDivisionError below) and should
            have been rejected earlier, at the seed loader / DB layer.
    """
    if ceiling <= 0:
        raise ValueError(f"ceiling must be > 0, got {ceiling!r}")

    places_left = ceiling - issued
    pct_used = round(issued / ceiling * 100)

    base = (
        f"{pct_used}% of this occupation's ceiling has been issued this program year "
        f"({issued} of {ceiling}), leaving {places_left} places."
    )
    if direction is None:
        return base

    if direction not in _PACE_PHRASES:
        raise ValueError(f"unrecognized momentum direction: {direction!r}")
    pace_phrase = _PACE_PHRASES[direction]

    return f"{base} {pace_phrase.capitalize()}."
