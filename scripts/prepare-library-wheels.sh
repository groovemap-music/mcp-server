#!/usr/bin/env bash
set -euo pipefail
expected="28fa329702bc76896cc54ab8d05ec5b1bd3d929e"
library_repo="${GROOVEMAP_LIBRARIES_REPO:-../python-libraries}"
library_checkout=

library_is_valid() {
  [[ -d "${library_repo}/.git" ]] &&
    [[ "$(git -C "${library_repo}" rev-parse HEAD)" = "${expected}" ]] &&
    [[ -z "$(git -C "${library_repo}" status --short)" ]]
}

if ! library_is_valid; then
  if [[ -n "${GROOVEMAP_LIBRARIES_REPO:-}" ]]; then
    echo "GROOVEMAP_LIBRARIES_REPO must be a clean checkout at ${expected}." >&2
    exit 2
  fi
  library_checkout="$(mktemp -d)"
  case "${library_checkout}" in
  /tmp/* | /private/tmp/* | /var/folders/*) ;;
  *)
    echo "Unexpected temporary checkout path: ${library_checkout}" >&2
    exit 2
    ;;
  esac
  trap 'rm -rf -- "${library_checkout}"' EXIT
  library_repo="${library_checkout}/python-libraries"
  git clone --quiet --filter=blob:none --no-checkout \
    https://github.com/groovemap-music/python-libraries.git "${library_repo}"
  git -C "${library_repo}" checkout --quiet "${expected}"
fi

mkdir -p .build/libraries
find .build/libraries -type f -name '*.whl' -delete
uv build --wheel --out-dir .build/libraries "${library_repo}"
uv build --wheel --out-dir .build/libraries "${library_repo}/agent-tools"
