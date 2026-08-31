#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

if ! git -C "${repo_root}" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "Refusing to label an image without a verifiable source revision." >&2
  exit 2
fi

if ! git -C "${repo_root}" diff --quiet HEAD --; then
  echo "Refusing to label an image from modified tracked source." >&2
  exit 2
fi

# The reusable workflow checks out the pinned private library inside the
# workspace. That checkout is build input, not first-party source, and its
# cleanliness and revision are verified by prepare-library-wheels.sh. Permit
# only that explicitly configured directory; every other untracked path fails
# closed so the image revision continues to identify its complete source.
allowed_dependency=
if [[ -n "${GROOVEMAP_LIBRARIES_REPO:-}" ]]; then
  case "${GROOVEMAP_LIBRARIES_REPO}" in
  "${repo_root}"/*)
    allowed_dependency="${GROOVEMAP_LIBRARIES_REPO#"${repo_root}"/}"
    allowed_dependency="${allowed_dependency%/}"
    ;;
  esac
fi

while IFS= read -r -d '' untracked_path; do
  if [[ -n "${allowed_dependency}" ]] &&
    { [[ "${untracked_path}" == "${allowed_dependency}" ]] ||
      [[ "${untracked_path}" == "${allowed_dependency}/"* ]]; }; then
    continue
  fi
  echo "Refusing to label an image with untracked source: ${untracked_path}" >&2
  exit 2
done < <(git -C "${repo_root}" ls-files --others --exclude-standard -z)
