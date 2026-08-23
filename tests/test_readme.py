"""Standing regression tests that README.md's data-backed sections stay data-backed.

REQ-C5 requires a real before/after benchmark table (numbers, not prose claims)
and REQ-D1 requires README to state the pinned ingest window and the
March-2020 drift rationale. These were verified once by hand during phase
execution (02-05); these tests guard against a future edit silently
stripping either section.
"""

from pathlib import Path

README_PATH = Path(__file__).resolve().parent.parent / "README.md"


def _section_body(readme_text: str, heading: str) -> str:
    """Return the text between `heading` and the next '## ' heading (exclusive)."""
    start = readme_text.index(heading)
    rest = readme_text[start + len(heading) :]
    next_heading_idx = rest.find("\n## ")
    body = rest if next_heading_idx == -1 else rest[:next_heading_idx]
    return body


def test_feature_engineering_benchmark_section_contains_a_real_numeric_table() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## Feature Engineering Benchmark")

    rows = [line for line in body.splitlines() if line.startswith("|")]

    assert len(rows) >= 6
    assert sum(any(c.isdigit() for c in row) for row in rows) >= 4


def test_dataset_and_drift_window_section_names_pinned_window_and_covid_rationale() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## Dataset and Drift Window")

    assert "2019-07" in body
    assert "2020-06" in body
    assert "March-2020" in body or "March 2020" in body or "COVID" in body
