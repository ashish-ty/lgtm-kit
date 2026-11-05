# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Make the PR's video folder and read its diff into ``diff.json``.

    uv run prepare.py --repo <repo> --pr 42
    uv run prepare.py --repo <repo> --base main [--head feat/x]     # a branch with no PR yet

The folder is ``<repo>/.pr-videos/pr-42/`` (or ``.pr-videos/<branch>/``). ``.pr-videos/`` holds
a ``.gitignore`` of ``*``, so it ignores itself and everything in it: nothing shows up in git,
and nothing is deleted for you — remove old videos by hand. A PR's diff comes from
``gh pr diff``; when GitHub won't serve it (very large PRs), the PR head is fetched and diffed
with git. ``diff.json`` records whether the working tree is on the PR head, because live beats
film the app the person started, from whatever is checked out.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import diff_map

WORKSPACE = ".pr-videos"
PR_FIELDS = "number,title,url,body,headRefName,baseRefName,headRefOid"
GIT_DIFF = ("diff", "--no-color", "--no-ext-diff", "-M", "--unified=3")


class PrepareError(RuntimeError):
    """The repo, PR or branch can't be read."""


def sh(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as err:
        raise PrepareError(f"`{' '.join(args)}` failed: {(err.stderr or err.stdout).strip()}") from err
    except FileNotFoundError as err:
        raise PrepareError(f"{args[0]} is not installed") from err


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "branch"


def folder_for(root: Path, pr: int | None, head: str | None) -> Path:
    return root / WORKSPACE / (f"pr-{pr}" if pr else slug(head or "head"))


def ensure_ignored(root: Path) -> None:
    ignore = root / WORKSPACE / ".gitignore"
    ignore.parent.mkdir(parents=True, exist_ok=True)
    if not ignore.exists():
        ignore.write_text("*\n")


def repo_slug(url: str | None) -> str | None:
    found = re.search(r"github\.com/([^/]+/[^/]+)/pull/", url or "")
    return found.group(1) if found else None


def gh_pr(root: Path, number: int) -> tuple[dict, str]:
    meta = json.loads(sh(["gh", "pr", "view", str(number), "--json", PR_FIELDS], root))
    try:
        diff = sh(["gh", "pr", "diff", str(number), "--color", "never"], root)
    except PrepareError:  # GitHub refuses diffs past its size limit; git has no such limit
        ref = f"refs/pr-video/{number}"
        sh(["git", "fetch", "-q", "origin", f"pull/{number}/head:{ref}", meta["baseRefName"]], root)
        diff = sh(["git", *GIT_DIFF, f"origin/{meta['baseRefName']}...{ref}"], root)
    return meta, diff


def branch_pr(root: Path, base: str, head: str) -> tuple[dict, str]:
    sha = sh(["git", "rev-parse", "--verify", "--quiet", f"{head}^{{commit}}"], root).strip()
    sh(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], root)
    meta = {"number": None, "title": sh(["git", "log", "-1", "--format=%s", head], root).strip(), "url": None,
            "body": "", "headRefName": head, "baseRefName": base, "headRefOid": sha}
    return meta, sh(["git", *GIT_DIFF, f"{base}...{head}"], root)


def resolve_head(root: Path, head: str | None) -> str:
    if head:
        return head
    name = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], root).strip()
    return name if name != "HEAD" else sh(["git", "rev-parse", "HEAD"], root).strip()


def document(meta: dict, diff: str, worktree_sha: str) -> dict:
    files = diff_map.parse(diff)
    return {
        "pr": {"number": meta["number"], "title": meta["title"], "url": meta["url"], "repo": repo_slug(meta["url"]),
               "body": meta.get("body") or "", "base": meta["baseRefName"], "head": meta["headRefName"],
               "head_sha": meta["headRefOid"]},
        "checked_out": worktree_sha == meta["headRefOid"],
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "totals": diff_map.totals(files), "files": files,
    }


def run(repo: Path, pr: int | None, base: str | None, head: str | None) -> Path:
    root = Path(sh(["git", "rev-parse", "--show-toplevel"], repo).strip())
    if pr:
        meta, diff = gh_pr(root, pr)
    elif base:
        try:
            meta, diff = branch_pr(root, base, resolve_head(root, head))
        except PrepareError as err:
            raise PrepareError(f"can't diff {head or 'HEAD'} against {base}: {err}") from err
    else:
        raise PrepareError("name a PR with --pr, or a branch's base with --base")
    doc = document(meta, diff, sh(["git", "rev-parse", "HEAD"], root).strip())
    ensure_ignored(root)
    folder = folder_for(root, pr, meta["headRefName"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "diff.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    return folder


def report(folder: Path) -> str:
    doc = json.loads((folder / "diff.json").read_text())
    t = doc["totals"]
    lines = [(f"{folder}/diff.json — {t['files']} files; code +{t['code']['added']} −{t['code']['removed']}, "
             f"tests +{t['test']['added']} −{t['test']['removed']}, "
             f"generated +{t['generated']['added']} −{t['generated']['removed']}")]
    if not doc["checked_out"]:
        lines.append(f"NOTE: the working tree is not on {doc['pr']['head']} — live beats film the app as it runs "
                     "from what is checked out; check out the PR head before starting the app")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--pr", type=int)
    ap.add_argument("--base")
    ap.add_argument("--head")
    args = ap.parse_args()
    try:
        print(report(run(args.repo.resolve(), args.pr, args.base, args.head)))
    except PrepareError as err:
        raise SystemExit(f"NOT PREPARED: {err}") from err


if __name__ == "__main__":
    main()
