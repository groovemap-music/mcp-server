#!/usr/bin/env bash
set -euo pipefail
library_repo="${GROOVEMAP_LIBRARIES_REPO:-../python-libraries}"
expected="28fa329702bc76896cc54ab8d05ec5b1bd3d929e"
test -d "${library_repo}/.git"
test "$(git -C "${library_repo}" rev-parse HEAD)" = "${expected}"
test -z "$(git -C "${library_repo}" status --short)"
mkdir -p .build/libraries
find .build/libraries -type f -name '*.whl' -delete
uv build --wheel --out-dir .build/libraries "${library_repo}"
uv build --wheel --out-dir .build/libraries "${library_repo}/agent-tools"
