"""Standing regression tests that README.md's data-backed sections stay data-backed.

REQ-C5 requires a real before/after benchmark table (numbers, not prose claims)
and REQ-D1 requires README to state the pinned ingest window and the
March-2020 drift rationale. These were verified once by hand during phase
execution (02-05); these tests guard against a future edit silently
stripping either section.

REQ-E1/E2/E3 join REQ-C5/REQ-D1 as the sections these tests guard: the
Architecture diagram (REQ-E1), the ADR set (REQ-E2), the Next Steps
deferred-scope statement (REQ-E3), and the Cluster Deployment runbook
(03-03-PLAN.md's must_haves) added in phase 03-03.
"""

import os
from pathlib import Path

README_PATH = Path(__file__).resolve().parent.parent / "README.md"
COMPONENTS_DIR = Path(__file__).resolve().parent.parent / "components"
DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy"


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


def test_architecture_section_contains_a_rendered_diagram() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## Architecture")

    assert "```mermaid" in body

    # Derived from the filesystem, not hardcoded, so a renamed/added component
    # directory makes this test speak up rather than silently going stale.
    # __pycache__ (and any other dunder-named cache dir) is excluded - it is
    # a build artifact, not a pipeline stage.
    component_names = sorted(
        p.name for p in COMPONENTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("__")
    )
    assert len(component_names) == 9
    for name in component_names:
        assert name in body, f"component directory {name!r} not named in the Architecture diagram"


def test_architecture_heading_does_not_alias_the_contract_section() -> None:
    text = README_PATH.read_text(encoding="utf-8")

    architecture_body = _section_body(text, "## Architecture")
    contract_body = _section_body(text, "## Architectural Contract")

    assert architecture_body != contract_body


def test_adr_section_covers_every_recorded_decision() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## ADRs")

    adr_headings = [line for line in body.splitlines() if line.startswith("### ADR-")]
    assert len(adr_headings) >= 10

    for decision_id in ("D-10", "D-11", "D-12", "D-13"):
        assert decision_id in body


def test_next_steps_section_names_deferred_scope() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## Next Steps")

    bullet_lines = [line for line in body.splitlines() if line.strip().startswith("- ")]
    assert len(bullet_lines) >= 10

    body_lower = body.lower()
    assert "kserve" in body_lower
    assert "dashboard" in body_lower
    assert "recurring" in body_lower


def test_cluster_deployment_section_names_every_deploy_script() -> None:
    if not DEPLOY_DIR.is_dir():
        # deploy/ is created by a sibling plan (03-04) landing in the same
        # wave as this plan; skip cleanly rather than failing on a directory
        # that does not exist yet.
        return

    text = README_PATH.read_text(encoding="utf-8")
    body = _section_body(text, "## Cluster Deployment")

    deploy_scripts = sorted(
        p.name for p in DEPLOY_DIR.iterdir() if p.is_file() and os.access(p, os.X_OK)
    )
    assert deploy_scripts, "deploy/ exists but contains no executable script"
    for script_name in deploy_scripts:
        assert script_name in body, f"deploy script {script_name!r} not named in Cluster Deployment"
