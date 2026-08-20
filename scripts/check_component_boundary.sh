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

# Step 3(a) - data-library imports: pandas or numpy, anchored to the start
# of a line (leading whitespace allowed), covering the plain-import,
# dotted-submodule, comma-separated, and from-import forms. Not end-anchored:
# trailing content on the line (a comment, a `; import os`, a second
# comma-separated module) must not defeat the match — a `$`-anchored form
# was previously exploitable via `import pandas  # noqa` (CR-01).
IMPORT_RE='^[[:space:]]*(import[[:space:]]+(pandas|numpy)([.,[:space:]]|$)|import[[:space:]]+[A-Za-z0-9_, ]*\b(pandas|numpy)\b|from[[:space:]]+(pandas|numpy)(\.[A-Za-z0-9_.]*)?[[:space:]]+import[[:space:]]+)'
if HITS="$(grep -nE "${IMPORT_RE}" -- "${FILES[@]}")"; then
  echo "VIOLATION: data-library import (pandas/numpy) found in components/:" >&2
  echo "${HITS}" >&2
  VIOLATIONS=1
fi

# Step 3(b) - DataFrame-shaped method calls: operations research says must
# live behind a single `lib` call.
METHOD_RE='\.(groupby|merge|pivot|resample|apply|assign|astype|read_parquet|to_parquet|read_csv|to_csv)\('
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
