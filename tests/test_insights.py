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
