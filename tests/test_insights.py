import pytest

from koshi.insights import generate_ceiling_insight

BANNED_PHRASES = [
    "you should",
    "you can",
    "you're eligible",
    "you are eligible",
    "you qualify",
    "you will",
]


def test_ceiling_insight_never_uses_advice_language():
    for direction in ("rising", "falling", "steady"):
        text = generate_ceiling_insight(issued=3200, ceiling=5000, direction=direction)
        lowered = text.lower()
        for phrase in BANNED_PHRASES:
            assert phrase not in lowered, f"banned phrase {phrase!r} found in: {text!r}"


def test_ceiling_insight_reports_correct_numbers():
    text = generate_ceiling_insight(issued=3200, ceiling=5000, direction="falling")
    assert "3200" in text
    assert "5000" in text
    assert "1800" in text  # places left = ceiling - issued
    assert "falling" in text.lower()


def test_ceiling_insight_reports_percent_used():
    text = generate_ceiling_insight(issued=2500, ceiling=5000, direction="steady")
    assert "50%" in text


def test_ceiling_insight_omits_trend_sentence_when_direction_is_none():
    # Fewer than three eoi_rounds exist yet — no trend claim may be
    # fabricated (regulatory posture: only published facts, never invented).
    text = generate_ceiling_insight(issued=2500, ceiling=5000, direction=None)
    lowered = text.lower()
    assert "round" not in lowered
    assert "threshold has" not in lowered


def test_ceiling_insight_rejects_unrecognized_direction():
    with pytest.raises(ValueError):
        generate_ceiling_insight(issued=2500, ceiling=5000, direction="sideways")


def test_ceiling_insight_rejects_zero_ceiling_instead_of_dividing_by_zero():
    with pytest.raises(ValueError):
        generate_ceiling_insight(issued=0, ceiling=0, direction=None)
