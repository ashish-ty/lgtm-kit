# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.45", "pyyaml>=6"]
# ///
"""Open the locally running app in a capture-sized browser.

    uv run session.py check --app http://localhost:5173
    uv run session.py login --app http://localhost:5173     # sign in by hand, once

The person (or the coding agent) starts the app from the PR head; this only checks it answers.
Capture runs in an on-disk Chrome profile **outside the repo**, one per app origin
(``~/.pr-video/chrome-profile/<host>-<port>``), so a sign-in made with ``login`` persists between
runs and no session token is ever committed. Without Google Chrome installed, Playwright's own
Chromium is used.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from storyboard import DEFAULT_BUSY

PROFILES = Path.home() / ".pr-video" / "chrome-profile"
VIEWPORT = {"width": 1920, "height": 1080}
SCALE = 2
REACH_TIMEOUT_S = 15
QUIET_MS = 1500
BUSY_TIMEOUT_MS = 120_000
NETWORK_IDLE_MS = 15_000
MANUAL_LOGIN_TIMEOUT_MS = 300_000


class SessionError(RuntimeError):
    """The app is not reachable."""


def profile_for(app: str) -> Path:
    url = urlparse(app)
    return PROFILES / re.sub(r"[^a-z0-9]+", "-", f"{url.hostname}-{url.port or url.scheme}".lower())


@contextmanager
def open_page(app: str, headless: bool = True, scale: int = SCALE):
    profile = profile_for(app)
    profile.mkdir(parents=True, exist_ok=True)
    options = {"headless": headless, "viewport": VIEWPORT, "device_scale_factor": scale, "locale": "en-US"}
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(str(profile), channel="chrome", **options)
        except PlaywrightError:  # no Google Chrome: Playwright's bundled Chromium
            context = p.chromium.launch_persistent_context(str(profile), **options)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            yield page
        finally:
            context.close()


IDLE_JS = """([sel, quiet]) => {
  const busy = [...document.querySelectorAll(sel)].some(e => e.offsetWidth || e.offsetHeight);
  if (busy) { window.__prVideoIdleSince = undefined; return false; }
  window.__prVideoIdleSince ??= performance.now();
  return performance.now() - window.__prVideoIdleSince >= quiet;
}"""


def wait_idle(page: Page, busy: str = DEFAULT_BUSY, settle_ms: int = 1200) -> None:
    """Wait until requests stop, nothing busy has shown for a moment, and charts have drawn."""
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
    except PlaywrightError:  # long-polling pages never go idle; the busy check still applies
        pass
    page.evaluate("() => { window.__prVideoIdleSince = undefined; }")
    page.wait_for_function(IDLE_JS, arg=[busy, QUIET_MS], polling=200, timeout=BUSY_TIMEOUT_MS)
    page.wait_for_timeout(settle_ms)


def reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=REACH_TIMEOUT_S) as response:
            return response.status < 500
    except Exception:  # noqa: BLE001 — any failure means "not answering"
        return False


def require_app(app: str) -> None:
    if not reachable(app):
        raise SessionError(f"the app is not answering at {app} — start it from the PR head, then rerun")


def login(app: str) -> None:
    require_app(app)
    with open_page(app, headless=False, scale=1) as page:
        page.goto(app)
        print("Sign in in the browser window that just opened, then close it (waiting up to 5 minutes) …")
        try:
            page.wait_for_event("close", timeout=MANUAL_LOGIN_TIMEOUT_MS)
        except PlaywrightError:
            pass
    print(f"session kept in {profile_for(app)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["check", "login"])
    ap.add_argument("--app", required=True)
    args = ap.parse_args()
    app = args.app.rstrip("/")
    try:
        if args.command == "login":
            login(app)
        else:
            require_app(app)
            print(f"ready: {app} is answering")
    except SessionError as err:
        sys.exit(f"NOT READY: {err}")


if __name__ == "__main__":
    main()
