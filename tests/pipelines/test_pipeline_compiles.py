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
# The ExitHandler exit task's backend-injected status object (REQ-B9) -
# neither a typed kfp.dsl artifact nor a plain scalar, but a legitimate
# third parameter kind KFP itself defines.
_SPECIAL_ANNOTATIONS = {"PipelineTaskFinalStatus"}


def _compile(out_path: Path) -> dict:
    """Compile train_pipeline to out_path and return the parsed pipeline-spec
    YAML document.

    kfp.kubernetes.use_secret_as_env (used on every credential-consuming
    task in train_pipeline.py) makes the compiler emit a second `---`
    document holding the Kubernetes-specific platformSpec - safe_load_all
    and taking the first document (the PipelineSpec itself) is required
    once any task carries platform-specific config; a plain safe_load
    raises ComposerError the moment a second document exists.
    """
    Compiler().compile(pipeline_func=train_pipeline, package_path=str(out_path))
    docs = list(yaml.safe_load_all(out_path.read_text(encoding="utf-8")))
    return docs[0]


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
            is_special = annotation_src in _SPECIAL_ANNOTATIONS
            assert is_scalar or is_artifact or is_special, (
                f"{node.name}.{arg.arg} annotation {annotation_src!r} is neither a typed "
                "kfp.dsl artifact, a scalar type, nor a recognized special KFP type (REQ-B2)"
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


# --- Full-DAG shape gates (plan 03-02 Task 3): REQ-B4/B5/B6/B7/B9 ----------


def test_compiled_executors_cover_all_nine_component_images(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")

    component_dirs = {p.parent.name for p in COMPONENTS_DIR.glob("*/component.py")}
    assert len(component_dirs) == 9, (
        f"expected 9 components/*/component.py dirs, found {component_dirs}"
    )

    executor_image_names = {
        ex["container"]["image"].rsplit("/", 1)[-1].split(":", 1)[0]
        for ex in spec["deploymentSpec"]["executors"].values()
    }
    assert executor_image_names == component_dirs


def test_parallel_for_parallelism_capped(tmp_path: Path) -> None:
    """Static REQ-B5 gate: the compiled parallelismLimit must be 1-3.

    This test has teeth: temporarily setting pipelines.train_pipeline.PARALLELISM
    to 12 and re-running makes this test fail (restore to 2 afterwards) - the
    compiled value is read directly off the module constant, not hardcoded here.
    """
    out_path = tmp_path / "train_pipeline.yaml"
    spec = _compile(out_path)
    text = out_path.read_text(encoding="utf-8")

    match = re.search(r"parallelismLimit:\s*(\d+)", text)
    assert match is not None, "expected a parallelismLimit field in the compiled YAML (REQ-B5)"
    parallelism = int(match.group(1))
    assert 1 <= parallelism <= 3, f"parallelism {parallelism} is outside the 1-3 cap (REQ-B5)"
    assert spec  # keep the compiled spec referenced, not just the raw text


def test_pipeline_source_uses_dsl_collected_with_no_manual_stitching() -> None:
    source = (PIPELINES_DIR / "train_pipeline.py").read_text(encoding="utf-8")
    assert "dsl.Collected(" in source, "expected a dsl.Collected( fan-in call (REQ-B6)"
    assert ".append(" not in source, "found manual per-month artifact list construction (REQ-B6)"


def _dag_by_component_name(spec: dict, name: str) -> dict:
    return spec["components"][name]["dag"]  # type: ignore[no-any-return]


def test_exit_handler_group_present_with_notify_as_exit_task(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")

    root_tasks = spec["root"]["dag"]["tasks"]
    exit_handler_task_names = [
        name for name, task in root_tasks.items() if task["taskInfo"]["name"] == "exit-handler"
    ]
    assert exit_handler_task_names, "expected an exit-handler DAG group in the root DAG (REQ-B9)"

    notify_task = root_tasks["notify"]
    assert notify_task["dependentTasks"] == exit_handler_task_names
    assert (
        notify_task["inputs"]["parameters"]["status"]["taskFinalStatus"]["producerTask"]
        == exit_handler_task_names[0]
    ), "expected notify to be wired as the ExitHandler's exit task via taskFinalStatus (REQ-B9)"


def test_register_only_reachable_inside_beats_champion_condition_group(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")

    assert "register" not in spec["root"]["dag"]["tasks"], (
        "register must not appear in the root DAG (REQ-B7)"
    )

    # The exit-handler component name is discovered from the root DAG's
    # exit-handler task's componentRef, not assumed by literal name.
    root_tasks = spec["root"]["dag"]["tasks"]
    exit_handler_ref = next(
        task["componentRef"]["name"]
        for task in root_tasks.values()
        if task["taskInfo"]["name"] == "exit-handler"
    )
    exit_handler_tasks = _dag_by_component_name(spec, exit_handler_ref)["tasks"]
    assert "register" not in exit_handler_tasks, (
        "register must not appear directly inside the exit-handler DAG (REQ-B7)"
    )

    condition_task_names = [
        name
        for name, task in exit_handler_tasks.items()
        if task["taskInfo"]["name"] == "beats-champion"
    ]
    assert condition_task_names, "expected a beats-champion condition group (REQ-B7)"
    condition_ref = exit_handler_tasks[condition_task_names[0]]["componentRef"]["name"]
    condition_tasks = _dag_by_component_name(spec, condition_ref)["tasks"]
    assert set(condition_tasks) == {"register"}, (
        f"expected only register in the beats-champion group, found {set(condition_tasks)}"
    )


def test_every_executor_declares_a_memory_limit(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")

    executors = spec["deploymentSpec"]["executors"]
    assert executors
    for name, executor in executors.items():
        resources = executor["container"].get("resources", {})
        assert resources.get("memoryLimit"), (
            f"{name} is missing an explicit memory limit (PITFALLS.md Pitfall 2)"
        )


_STAGE_TASK_NAMES = {
    "expand-months",
    "ingest",
    "validate",
    "build-features-component",
    "merge-features",
    "train",
    "evaluate",
    "register",
    "notify",
}


def _all_task_names(spec: dict) -> set:
    names: set = set()
    dags = [spec["root"]["dag"]]
    dags.extend(comp["dag"] for comp in spec["components"].values() if "dag" in comp)
    for dag in dags:
        for task in dag.get("tasks", {}).values():
            names.add(task["taskInfo"]["name"])
    return names


def test_task_name_set_covers_all_nine_stages(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")
    assert _all_task_names(spec) >= _STAGE_TASK_NAMES


def test_task_dependency_chain_matches_req_b4_order(tmp_path: Path) -> None:
    spec = _compile(tmp_path / "train_pipeline.yaml")

    for_loop_tasks = next(
        _dag_by_component_name(spec, comp)["tasks"]
        for comp, definition in spec["components"].items()
        if "dag" in definition and "ingest" in definition["dag"]["tasks"]
    )
    assert for_loop_tasks["validate"]["dependentTasks"] == ["ingest"]
    assert for_loop_tasks["build-features-component"]["dependentTasks"] == ["validate"]

    exit_handler_ref = next(
        task["componentRef"]["name"]
        for task in spec["root"]["dag"]["tasks"].values()
        if task["taskInfo"]["name"] == "exit-handler"
    )
    exit_handler_tasks = _dag_by_component_name(spec, exit_handler_ref)["tasks"]
    for_loop_ref = next(
        name
        for name, task in exit_handler_tasks.items()
        if "for-loop" in name or "for_loop" in name
    )
    merge_task = next(
        t for t in exit_handler_tasks.values() if t["taskInfo"]["name"] == "merge-features"
    )
    assert merge_task["dependentTasks"] == [for_loop_ref]

    train_task = next(t for t in exit_handler_tasks.values() if t["taskInfo"]["name"] == "train")
    assert train_task["dependentTasks"] == ["merge-features"]

    evaluate_task = next(
        t for t in exit_handler_tasks.values() if t["taskInfo"]["name"] == "evaluate"
    )
    assert set(evaluate_task["dependentTasks"]) == {"merge-features", "train"}

    condition_task = next(
        t for t in exit_handler_tasks.values() if t["taskInfo"]["name"] == "beats-champion"
    )
    assert set(condition_task["dependentTasks"]) == {"evaluate", "train"}
