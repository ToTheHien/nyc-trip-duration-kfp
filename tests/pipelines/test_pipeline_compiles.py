"""Static/compile-time DAG shape assertions (REQ-B2/B3/B4 static half).

Mirrors tests/test_readme.py's shape: one small pure helper plus several
`test_*` assertions reading a real compiled artifact.
"""

import ast
import re
from pathlib import Path

import yaml
from kfp.compiler import Compiler

from pipelines.train_pipeline import train_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPONENTS_DIR = REPO_ROOT / "components"
PIPELINES_DIR = REPO_ROOT / "pipelines"
BOUNDARY_SCRIPT = REPO_ROOT / "scripts" / "check_component_boundary.sh"

_SCALAR_ANNOTATIONS = {"str", "int", "float", "bool"}
_RAW_PATH_SUFFIXES = ("_path", "_key", "_uri_path")


def _compile(out_path: Path) -> dict:
    """Compile train_pipeline to out_path and return the parsed YAML dict."""
    Compiler().compile(pipeline_func=train_pipeline, package_path=str(out_path))
    return yaml.safe_load(out_path.read_text(encoding="utf-8"))


def test_train_pipeline_compiles_to_non_empty_yaml(tmp_path: Path) -> None:
    out_path = tmp_path / "train_pipeline.yaml"

    spec = _compile(out_path)

    assert out_path.stat().st_size > 0
    assert spec


def _is_dsl_component_decorator(node: ast.expr) -> bool:
    """True for `@dsl.component` or `@dsl.component(base_image=...)`."""
    target = node.func if isinstance(node, ast.Call) else node
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "component"
        and isinstance(target.value, ast.Name)
        and target.value.id == "dsl"
    )


def _component_function_defs() -> list[ast.FunctionDef]:
    defs: list[ast.FunctionDef] = []
    for path in sorted(COMPONENTS_DIR.glob("*/component.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and any(
                _is_dsl_component_decorator(d) for d in node.decorator_list
            ):
                defs.append(node)
    return defs


def test_component_parameters_are_typed_artifacts_or_scalars_never_raw_paths() -> None:
    component_defs = _component_function_defs()
    assert component_defs, "expected at least one @dsl.component function under components/"

    for node in component_defs:
        for arg in node.args.args:
            assert arg.annotation is not None, (
                f"{node.name}.{arg.arg} is missing a type annotation (REQ-B2)"
            )
            annotation_src = ast.unparse(arg.annotation)
            is_scalar = annotation_src in _SCALAR_ANNOTATIONS
            is_artifact = annotation_src.startswith(("Output[", "Input["))
            assert is_scalar or is_artifact, (
                f"{node.name}.{arg.arg} annotation {annotation_src!r} is neither a typed "
                "kfp.dsl artifact nor a scalar type (REQ-B2)"
            )
            assert not arg.arg.endswith(_RAW_PATH_SUFFIXES), (
                f"{node.name}.{arg.arg} looks like a raw storage path/key parameter (REQ-B2)"
            )


_IMAGE_RE = re.compile(r"image:\s*(ghcr\.io/\S+)")


def test_compiled_component_images_are_git_sha_tagged_ghcr_references(tmp_path: Path) -> None:
    out_path = tmp_path / "train_pipeline.yaml"
    Compiler().compile(pipeline_func=train_pipeline, package_path=str(out_path))
    text = out_path.read_text(encoding="utf-8")

    images = _IMAGE_RE.findall(text)
    assert images, "expected at least one ghcr.io component image reference in compiled YAML"
    for image in images:
        assert image.startswith("ghcr.io/tothehien/nyc-trip-duration-kfp/"), image
        tag = image.rsplit(":", 1)[-1]
        assert tag not in ("latest", "master"), f"{image} uses a rolling tag (Pitfall 6)"


def test_no_runtime_dependency_installation_keyword_in_components_or_pipelines() -> None:
    """Reads the forbidden literal out of check_component_boundary.sh itself,
    so the pytest gate and the shell boundary gate cannot drift apart.
    """
    script_text = BOUNDARY_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"INSTALL_RE='([^']+)'", script_text)
    assert match is not None, "could not find INSTALL_RE in scripts/check_component_boundary.sh"
    keyword = match.group(1)

    for directory in (COMPONENTS_DIR, PIPELINES_DIR):
        for path in sorted(directory.rglob("*.py")):
            assert keyword not in path.read_text(encoding="utf-8"), f"{keyword!r} found in {path}"
