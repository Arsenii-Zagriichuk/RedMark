"""A results file's recorded commit must hold the code and config that wrote it."""

import subprocess

import pytest

from locate.horizon.sources import UncommittedCode, git_commit


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "build.py").write_text("print('v1')\n")
    (tmp_path / "landmarks.yaml").write_text("a: 1\n")
    (tmp_path / "notes.md").write_text("notes\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_a_clean_script_and_config_give_the_commit_they_are_at(repo):
    assert git_commit("build.py", "landmarks.yaml", repo=repo) == git(repo, "rev-parse", "HEAD")


def test_an_edited_script_is_refused(repo):
    (repo / "build.py").write_text("print('v2')\n")
    with pytest.raises(UncommittedCode, match="build.py"):
        git_commit("build.py", "landmarks.yaml", repo=repo)


def test_a_script_not_yet_committed_is_refused(repo):
    (repo / "plot.py").write_text("print('new')\n")
    with pytest.raises(UncommittedCode, match="plot.py"):
        git_commit("*.py", repo=repo)


def test_edits_outside_the_named_paths_are_allowed(repo):
    (repo / "notes.md").write_text("more notes\n")
    assert git_commit("build.py", "landmarks.yaml", repo=repo) == git(repo, "rev-parse", "HEAD")


def test_naming_no_paths_is_refused(repo):
    # Every caller must say which code and config its results depend on.
    with pytest.raises(ValueError):
        git_commit(repo=repo)
