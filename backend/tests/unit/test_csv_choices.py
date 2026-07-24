"""WP3 S12 (#82) — CSV → choice-value parsing.

The import gate: a well-formed ``code,label`` CSV parses to ordered rows;
anything malformed (bad encoding, missing header, empty codes, duplicate
codes, no data rows, oversize) is rejected with a message the route maps
to a 422.
"""

import pytest

from app.core.csv_choices import CSV_MAX_BYTES, CsvChoiceError, parse_choice_csv


def test_parses_code_label_rows_in_order() -> None:
    rows = parse_choice_csv(b"code,label\nsvc-a,Service A\nsvc-b,Service B\n")
    assert rows == [("svc-a", "Service A"), ("svc-b", "Service B")]


def test_header_is_case_insensitive_and_extra_columns_ignored() -> None:
    rows = parse_choice_csv(b"Label,Code,Comment\nService A,svc-a,ignored\n")
    assert rows == [("svc-a", "Service A")]


def test_blank_lines_are_skipped() -> None:
    rows = parse_choice_csv(b"code,label\n\nsvc-a,Service A\n\n")
    assert rows == [("svc-a", "Service A")]


def test_label_defaults_to_code_when_empty() -> None:
    rows = parse_choice_csv(b"code,label\nsvc-a,\n")
    assert rows == [("svc-a", "svc-a")]


def test_values_are_stripped() -> None:
    rows = parse_choice_csv(b"code,label\n  svc-a  ,  Service A  \n")
    assert rows == [("svc-a", "Service A")]


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"\xff\xfe\x00bad", "UTF-8"),  # undecodable bytes
        (b"", "header"),  # empty file
        (b"name,value\nx,y\n", "header"),  # wrong header
        (b"code,label\n", "no data rows"),  # header only
        (b"code,label\n,Service A\n", "empty code"),
        (b"code,label\nsvc-a,A\nsvc-a,B\n", "duplicate"),
    ],
)
def test_malformed_csv_rejected(data: bytes, match: str) -> None:
    with pytest.raises(CsvChoiceError, match=match):
        parse_choice_csv(data)


def test_oversize_rejected() -> None:
    padding = b"code,label\n" + b"x,y\n" * (CSV_MAX_BYTES // 4)
    with pytest.raises(CsvChoiceError, match="too large"):
        parse_choice_csv(padding)
