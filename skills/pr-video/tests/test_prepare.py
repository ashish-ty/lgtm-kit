"""prepare.py makes a self-ignoring workspace and a diff.json from a real git repo."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prepare


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "app.py").write_text("def run():\n    return 1\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", "feat/retry")
    (root / "app.py").write_text("def run():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("def test_run():\n    assert True\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "feat: retry uploads")
    return root


def test_folder_names_a_pr_by_number_and_a_branch_by_slug(tmp_path):
    assert prepare.folder_for(tmp_path, pr=42, head=None) == tmp_path / ".pr-videos" / "pr-42"
    assert prepare.folder_for(tmp_path, pr=None, head="feat/Retry Uploads") == tmp_path / ".pr-videos" / "feat-retry-uploads"


def test_the_workspace_ignores_itself(tmp_path):
    prepare.ensure_ignored(tmp_path)
    assert (tmp_path / ".pr-videos" / ".gitignore").read_text() == "*\n"


def test_an_existing_ignore_file_is_left_alone(tmp_path):
    (tmp_path / ".pr-videos").mkdir()
    (tmp_path / ".pr-videos" / ".gitignore").write_text("*\n# mine\n")
    prepare.ensure_ignored(tmp_path)
    assert "# mine" in (tmp_path / ".pr-videos" / ".gitignore").read_text()


def test_a_branch_diff_against_its_base(repo):
    folder = prepare.run(repo, pr=None, base="main", head="feat/retry")
    doc = json.loads((folder / "diff.json").read_text())
    assert doc["pr"]["title"] == "feat: retry uploads"
    assert (doc["pr"]["base"], doc["pr"]["head"], doc["pr"]["number"]) == ("main", "feat/retry", None)
    assert [f["path"] for f in doc["files"]] == ["app.py", "tests/test_app.py"]
    assert doc["totals"]["test"] == {"added": 2, "removed": 0}
    assert doc["checked_out"] is True
    assert git(repo, "status", "--porcelain") == ""  # nothing shows up in git


def test_the_checkout_mismatch_is_recorded(repo):
    git(repo, "switch", "-q", "main")
    doc = json.loads((prepare.run(repo, pr=None, base="main", head="feat/retry") / "diff.json").read_text())
    assert doc["checked_out"] is False


def test_an_unknown_branch_fails_clearly(repo):
    with pytest.raises(prepare.PrepareError, match="nope"):
        prepare.run(repo, pr=None, base="main", head="nope")


def test_pr_metadata_is_mapped_from_gh(monkeypatch, repo):
    meta = {"number": 7, "title": "Retry", "url": "https://github.com/acme/infra/pull/7", "body": "Fixes #3",
            "headRefName": "feat/retry", "baseRefName": "main", "headRefOid": git(repo, "rev-parse", "feat/retry")}
    diff = git(repo, "diff", "main...feat/retry")
    monkeypatch.setattr(prepare, "gh_pr", lambda root, n: (meta, diff + "\n"))
    doc = json.loads((prepare.run(repo, pr=7, base=None, head=None) / "diff.json").read_text())
    assert doc["pr"] == {"number": 7, "title": "Retry", "url": meta["url"], "repo": "acme/infra", "body": "Fixes #3",
                         "base": "main", "head": "feat/retry", "head_sha": meta["headRefOid"]}
    assert len(doc["files"]) == 2


def test_report_summarises_and_warns_off_the_pr_head(repo):
    git(repo, "switch", "-q", "main")
    text = prepare.report(prepare.run(repo, pr=None, base="main", head="feat/retry"))
    assert "2 files" in text and "NOTE: the working tree is not on feat/retry" in text


def test_main_without_a_pr_or_base_explains(monkeypatch, repo):
    monkeypatch.setattr(sys, "argv", ["prepare.py", "--repo", str(repo)])
    with pytest.raises(SystemExit, match="--pr"):
        prepare.main()


def test_a_branch_defaults_to_what_is_checked_out(repo):
    doc = json.loads((prepare.run(repo, pr=None, base="main", head=None) / "diff.json").read_text())
    assert doc["pr"]["head"] == "feat/retry"


def test_repo_slug_reads_github_urls():
    assert prepare.repo_slug("https://github.com/acme/infra/pull/7") == "acme/infra"
    assert prepare.repo_slug(None) is None


REMOTES = """\
origin\tgit@github.com:me/infra.git (fetch)
origin\tgit@github.com:me/infra.git (push)
upstream\thttps://github.com/Acme/Infra (fetch)
upstream\thttps://github.com/Acme/Infra (push)
"""


def test_the_remote_is_the_one_that_holds_the_pr():
    assert prepare.remote_for(REMOTES, "acme/infra") == "upstream"
    assert prepare.remote_for(REMOTES, "me/infra") == "origin"


def test_with_no_matching_remote_the_pr_repo_is_fetched_by_url():
    assert prepare.remote_for(REMOTES, "other/thing") == "https://github.com/other/thing.git"
    assert prepare.remote_for(REMOTES, None) == "origin"
