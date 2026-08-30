set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

setup:
    uv sync --dev --frozen

source-check:
    uvx --from ruff==0.16.4 ruff format --check .
    uvx --from ruff==0.16.4 ruff check .
    python scripts/check-docs.py
    python scripts/check-contracts.py

security:
    gitleaks git --redact --no-banner
    gitleaks dir . --redact --no-banner

automation-check:
    actionlint .github/workflows/*.yml
    python scripts/check-automation.py

ci-check: source-check typecheck protocol-check automation-check bump-preview

check: ci-check security test build install-check license-check

format:
    uv run ruff format .
    uv run ruff check --fix .

typecheck:
    uv run mypy

test:
    uv run pytest --cov=mcp_server --cov-report=term-missing --cov-report=xml

coverage:
    uv run pytest --cov=mcp_server --cov-report=term-missing --cov-report=xml

protocol-check:
    uv run pytest tests/test_mcp_tools_regression.py tests/test_contract.py

build:
    uv build --out-dir dist --clear

prepare-library-wheels:
    bash scripts/prepare-library-wheels.sh

prepare-image: build prepare-library-wheels

image: prepare-image
    bash scripts/build-image.sh
    bash scripts/check-image.sh

install-check: build
    bash scripts/install-check.sh

license-check:
    uv run python scripts/check-license.py
    uv run pip-licenses --fail-on "GPL-2.0-only;GPL-3.0-only;AGPL-3.0-only"

audit:
    uv run pip-audit

bump-preview:
    uv run cz bump --dry-run --changelog --yes --check-consistency

# Update local version metadata and changelog only; do not commit, tag, push, or publish.
bump:
    uv run cz bump --version-files-only --changelog --yes --check-consistency
    uv lock

release-dry-run: check prepare-image
    bash scripts/release-dry-run.sh
