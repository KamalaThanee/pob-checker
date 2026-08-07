import pytest

from main import parse_ocr


def test_parse_ocr_valid_output():
    parsed = parse_ocr("2 LR-1 B401A|AKARANET SA")

    assert parsed == [{
        "raw": "2 LR-1 B401A|AKARANET SA",
        "cabin": "B-401",
        "bed": "A",
        "cabin_bed": "B-401A",
        "name_tag": "AKARANET SA",
    }]


def test_parse_ocr_multiple_lines():
    parsed = parse_ocr(
        "2 LR-1 B401A|AKARANET SA\n"
        "2 LR-1 B401B|NOPPHAKORN YI"
    )

    assert [item["cabin_bed"] for item in parsed] == ["B-401A", "B-401B"]
    assert [item["name_tag"] for item in parsed] == ["AKARANET SA", "NOPPHAKORN YI"]


def test_parse_ocr_ignores_lines_without_pipe():
    parsed = parse_ocr("heading\nB401A|AKARANET SA\nnot a record")

    assert len(parsed) == 1
    assert parsed[0]["cabin_bed"] == "B-401A"


@pytest.mark.parametrize("cabin", ["B401A", "B-401A"])
def test_parse_ocr_normalizes_supported_cabin_formats(cabin):
    parsed = parse_ocr(f"{cabin}|AKARANET SA")

    assert parsed[0]["cabin"] == "B-401"
    assert parsed[0]["bed"] == "A"
    assert parsed[0]["cabin_bed"] == "B-401A"


def test_parse_ocr_normalizes_lowercase_fields():
    parsed = parse_ocr("b401a|akaranet sa")

    assert parsed[0]["cabin_bed"] == "B-401A"
    assert parsed[0]["name_tag"] == "AKARANET SA"


@pytest.mark.parametrize(
    ("raw", "expected_cabin", "expected_bed", "expected_cabin_bed"),
    [
        ("|AKARANET SA", "", "", ""),
        ("B401|AKARANET SA", "B401", "", "B401"),
        ("UNKNOWN CABIN|AKARANET SA", "UNKNOWN CABIN", "", "UNKNOWN CABIN"),
    ],
)
def test_parse_ocr_preserves_missing_or_incomplete_cabin_identifiers(
    raw, expected_cabin, expected_bed, expected_cabin_bed
):
    parsed = parse_ocr(raw)

    assert parsed[0]["cabin"] == expected_cabin
    assert parsed[0]["bed"] == expected_bed
    assert parsed[0]["cabin_bed"] == expected_cabin_bed
