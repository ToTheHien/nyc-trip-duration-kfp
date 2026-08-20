#!/usr/bin/env bash
set -uo pipefail

# Locate ourselves so the scan is always rooted at the repo, regardless of
# whether we're invoked via `qa.sh boundary` or directly.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

SCAN_PATH="components"

# Step 1 - collect the scan set. Only tracked files: an untracked scratch
# file must not be able to fail this gate, and a deleted file must not
# linger in the scan.
mapfile -t FILES < <(git ls-files -- "${SCAN_PATH}/*.py" "${SCAN_PATH}/**/*.py" | sort -u)

# Step 2 - the non-vacuous guard, BEFORE any pattern check. A gate whose
# scan target has been renamed, emptied, or misspelled must fail loudly;
# silently reporting success is exactly the failure mode this gate exists
# to prevent.
if [ "${#FILES[@]}" -eq 0 ]; then
  echo "REFUSED: no tracked Python modules found under '${SCAN_PATH}/' - the boundary gate cannot pass vacuously." >&2
  exit 1
fi

VIOLATIONS=0

# Step 3(a) - data-library imports: pandas or numpy, covering the
# plain-import, dotted-submodule, comma-separated, from-import,
# star-import, and dynamic-import (__import__ / importlib.import_module)
# forms. Not anchored to line-start and not end-anchored: neither leading
# nor trailing content on the line may defeat the match. Two prior bypass
# classes are closed here:
#   - CR-01: `import pandas  # noqa` — a `$`-anchored plain-import form
#     was defeated by trailing content (comment/semicolon/comma-list).
#   - Compound/dynamic bypass: `import os; import pandas`, `try: import
#     pandas`, `if True: import pandas`, `from pandas import*`,
#     `__import__("pandas")` — a `^`-anchored plain-import form only ever
#     matched a statement that was first on its physical line, so any
#     import preceded by `;` or `:` on the same line, or expressed via the
#     dynamic-import builtins, evaded detection entirely.
# The statement-boundary alternation `(^|[;:])[[:space:]]*` replaces the
# line-start anchor: it matches at the true start of the line OR
# immediately after a `;`/`:` that begins a new logical statement, so a
# compound or conditional one-liner no longer hides the import.
IMPORT_RE='(^|[;:])[[:space:]]*(import[[:space:]]+(pandas|numpy)([.,[:space:]]|$)|import[[:space:]]+[A-Za-z0-9_, ]*\b(pandas|numpy)\b|from[[:space:]]+(pandas|numpy)(\.[A-Za-z0-9_.]*)?[[:space:]]+import\b)'
DYNAMIC_IMPORT_RE="(__import__[[:space:]]*\([[:space:]]*[\"']|importlib\.import_module[[:space:]]*\([[:space:]]*[\"'])(pandas|numpy)\\b"
HITS="$(grep -nE "${IMPORT_RE}" -- "${FILES[@]}")"
DYNAMIC_HITS="$(grep -nE "${DYNAMIC_IMPORT_RE}" -- "${FILES[@]}")"
if [ -n "${HITS}" ] || [ -n "${DYNAMIC_HITS}" ]; then
  echo "VIOLATION: data-library import (pandas/numpy) found in components/:" >&2
  [ -n "${HITS}" ] && echo "${HITS}" >&2
  [ -n "${DYNAMIC_HITS}" ] && echo "${DYNAMIC_HITS}" >&2
  VIOLATIONS=1
fi

# Step 3(b) - DataFrame-shaped method calls and constructors: operations
# research says must live behind a single `lib` call. Includes the
# DataFrame/Series constructors themselves (e.g. `pd.DataFrame(...)`),
# not just the transformation methods called on an existing frame.
METHOD_RE='\.(groupby|merge|pivot|resample|apply|assign|astype|read_parquet|to_parquet|read_csv|to_csv|DataFrame|Series)\('
if HITS="$(grep -nE "${METHOD_RE}" -- "${FILES[@]}")"; then
  echo "VIOLATION: DataFrame-shaped method call found in components/:" >&2
  echo "${HITS}" >&2
  VIOLATIONS=1
fi

# Step 3(c) - runtime dependency installation inside a component. Forbidden
# for this project: component dependencies come from the CI-built image,
# never from a pip install at pod start.
INSTALL_RE='packages_to_install' # planner-discipline-allow: packages_to_install
if HITS="$(grep -nE "${INSTALL_RE}" -- "${FILES[@]}")"; then
  echo "VIOLATION: packages_to_install found in components/ (runtime dependency installation is forbidden):" >&2
  echo "${HITS}" >&2
  VIOLATIONS=1
fi

if [ "${VIOLATIONS}" -ne 0 ]; then
  exit 1
fi

echo "OK: boundary gate passed - ${#FILES[@]} module(s) scanned under ${SCAN_PATH}/"
exit 0
