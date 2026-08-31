"""Regression coverage for image provenance source validation."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
BASH = shutil.which("bash")


def _required_executable(executable: str | None, name: str) -> str:
    if executable is None:
        raise RuntimeError(f"required test executable is unavailable: {name}")
    return executable


def _source_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "check-image-source.sh", scripts)
    (repository / "tracked.txt").write_text("committed\n", encoding="utf-8")
    git = _required_executable(GIT, "git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True)  # noqa: S603
    subprocess.run([git, "add", "."], cwd=repository, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [
            git,
            "-c",
            "user.name=GrooveMap Test",
            "-c",
            "user.email=test@groovemap.music",
            "commit",
            "--quiet",
            "-m",
            "test: establish image source",
        ],
        cwd=repository,
        check=True,
    )
    return repository


def _run_source_check(repository: Path, *, library_repo: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if library_repo is None:
        environment.pop("GROOVEMAP_LIBRARIES_REPO", None)
    else:
        environment["GROOVEMAP_LIBRARIES_REPO"] = str(library_repo)
    return subprocess.run(  # noqa: S603
        [_required_executable(BASH, "bash"), "scripts/check-image-source.sh"],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _nested_dependency_checkout(repository: Path) -> Path:
    dependency = repository / "python-libraries"
    dependency.mkdir()
    (dependency / "README.md").write_text("workflow-injected dependency\n", encoding="utf-8")
    git = _required_executable(GIT, "git")
    subprocess.run([git, "init", "--quiet"], cwd=dependency, check=True)  # noqa: S603
    subprocess.run([git, "add", "."], cwd=dependency, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [
            git,
            "-c",
            "user.name=GrooveMap Test",
            "-c",
            "user.email=test@groovemap.music",
            "commit",
            "--quiet",
            "-m",
            "test: establish injected dependency",
        ],
        cwd=dependency,
        check=True,
    )
    return dependency


def test_build_delegates_to_source_check_and_excludes_injected_checkout() -> None:
    build_script = (ROOT / "scripts" / "build-image.sh").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert 'bash "${repo_root}/scripts/check-image-source.sh"' in build_script
    assert "python-libraries" in dockerignore


def test_source_check_allows_explicit_hosted_dependency_checkout(tmp_path: Path) -> None:
    repository = _source_repository(tmp_path)
    dependency = _nested_dependency_checkout(repository)

    result = _run_source_check(repository, library_repo=dependency)

    assert result.returncode == 0, result.stderr


def test_source_check_rejects_unconfigured_dependency_checkout(tmp_path: Path) -> None:
    repository = _source_repository(tmp_path)
    dependency = repository / "python-libraries"
    dependency.mkdir()
    (dependency / "README.md").write_text("unexpected dependency\n", encoding="utf-8")

    result = _run_source_check(repository)

    assert result.returncode == 2
    assert "untracked source: python-libraries/README.md" in result.stderr


def test_source_check_rejects_untracked_first_party_source(tmp_path: Path) -> None:
    repository = _source_repository(tmp_path)
    dependency = repository / "python-libraries"
    dependency.mkdir()
    (dependency / "README.md").write_text("workflow-injected dependency\n", encoding="utf-8")
    (repository / "mcp_server.py").write_text("uncommitted = True\n", encoding="utf-8")

    result = _run_source_check(repository, library_repo=dependency)

    assert result.returncode == 2
    assert "untracked source: mcp_server.py" in result.stderr


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged", "staged"])
def test_source_check_rejects_modified_tracked_source(tmp_path: Path, staged: bool) -> None:
    repository = _source_repository(tmp_path)
    (repository / "tracked.txt").write_text("modified\n", encoding="utf-8")
    if staged:
        subprocess.run(  # noqa: S603
            [_required_executable(GIT, "git"), "add", "tracked.txt"], cwd=repository, check=True
        )

    result = _run_source_check(repository)

    assert result.returncode == 2
    assert "modified tracked source" in result.stderr
