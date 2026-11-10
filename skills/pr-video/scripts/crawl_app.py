# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.45", "pyyaml>=6"]
# ///
"""Crawl the running app into a screen catalogue: what each screen offers, as it is today.

    uv run crawl_app.py --app http://localhost:5173 --out <video folder>/catalogue.json \\
        --route /settings [--route /files ...] [--set "Mode=Advanced" ...]

For each route it records the headings, buttons, labelled controls with their current value
and every option (it opens each dropdown, reads it, and closes it — nothing is changed), the
table headers, and the first-column rows a table shows. ``--set`` picks dropdown values before
crawling, for controls that only appear in a given state; that state is stored under its own key.

The catalogue is what the storyboard's live targets are written from: names come from this
file, never from memory of the code.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import locators
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from session import SessionError, open_page, require_app, wait_idle

MAX_OPTIONS = 200
MAX_ROWS = 60
OPEN_MS = 400

SCREEN_JS = """() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight);
  const t = e => (e.innerText || '').trim().split('\\n')[0].trim();
  const uniq = a => [...new Set(a.filter(Boolean))];
  const labels = {};
  for (const l of document.querySelectorAll('label')) {
    if (!vis(l) || !t(l)) continue;
    const next = l.nextElementSibling, first = next && next.firstElementChild;
    let kind = 'other', current = '';
    if (next && next.matches('input,textarea,select')) { kind = 'input'; current = next.value || next.placeholder || ''; }
    else if (first && first.matches('[aria-haspopup=listbox]')) { kind = 'select'; current = t(first); }
    else if (first && first.querySelector('svg')) { kind = 'multiselect'; current = t(first); }
    const disabled = !!(first && getComputedStyle(first).cursor === 'not-allowed');
    labels[t(l)] = { kind, current, disabled };
  }
  const tables = [...document.querySelectorAll('table')].filter(vis);
  return {
    url: location.pathname,
    headings: uniq([...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).map(t)),
    buttons: uniq([...document.querySelectorAll('button,[role=button],[role=tab],a')].filter(vis)
                  .map(e => t(e) || e.getAttribute('aria-label') || '')),
    labels,
    tables: tables.map(tb => [...tb.querySelectorAll('th')].map(t)),
    rows: tables.map(tb => uniq([...tb.querySelectorAll('tbody tr td:first-child')].map(t)).slice(0, %d)),
    demo: [...document.querySelectorAll('[data-demo]')].map(e => e.dataset.demo),
  };
}""".replace("%d", str(MAX_ROWS))


def lines(page: Page, label: str) -> list[str]:
    text = locators.control(page, label).inner_text(timeout=3000)
    return [s.strip() for s in text.split("\n") if s.strip()]


def open_control(page: Page, label: str, kind: str) -> None:
    trig = locators.trigger(page, label)
    if kind == "multiselect":  # chips carry their own remove buttons; open from the chevron end
        box = trig.bounding_box()
        trig.click(position={"x": box["width"] - 12, "y": box["height"] / 2}, timeout=3000)
    else:
        trig.click(timeout=3000)
    page.wait_for_timeout(OPEN_MS)


def close_control(page: Page, label: str) -> None:
    page.keyboard.press("Escape")
    try:  # a click outside closes the rest; an overlay can sit over the label, which is fine
        page.locator("label").filter(has_text=locators.exact(label)).first.click(timeout=3000)
    except PlaywrightError:
        page.mouse.click(5, 5)
    page.wait_for_timeout(OPEN_MS)


def read_options(page: Page, label: str, kind: str) -> list[str]:
    """Every entry the dropdown offers. Raises when it cannot be read: an unreadable list must
    never pass for an empty one, or drift would report every option as removed."""
    last_error = None
    for _ in range(2):  # the first open can be swallowed while the page settles
        try:
            before = lines(page, label)
            open_control(page, label, kind)
            if kind == "select":
                found = locators.open_options(page, label)
            else:
                found = [s for s in lines(page, label) if s not in before] or locators.open_options(page, label)
            found = [s.strip() for s in found if s.strip()][:MAX_OPTIONS]
            if found:
                return found
            last_error = "the list opened empty"
        except PlaywrightError as err:
            last_error = str(err).splitlines()[0]
        finally:
            close_control(page, label)
    raise RuntimeError(last_error)


def apply_state(page: Page, settings: list[str]) -> None:
    for setting in settings:
        label, value = (s.strip() for s in setting.split("=", 1))
        entry = locators.option(page, value, label)
        for _ in range(2):  # a click while the page settles can be swallowed; open it once more
            locators.trigger(page, label).click()
            try:
                entry.wait_for(state="visible", timeout=locators.OPEN_TIMEOUT_MS)
                break
            except PlaywrightError:
                continue
        entry.click()
        wait_idle(page)


def crawl_route(page: Page, app: str, route: str, settings: list[str]) -> dict:
    page.goto(f"{app}{route}")
    wait_idle(page)
    apply_state(page, settings)
    screen = {"route": route, "settings": list(settings), **page.evaluate(SCREEN_JS)}
    for label, control in screen["labels"].items():
        if control["kind"] in ("select", "multiselect") and not control["disabled"]:
            try:
                control["options"] = read_options(page, label, control["kind"])
            except RuntimeError as err:
                control["options_error"] = str(err)
                print(f"{route}: could not read the options under {label!r} — {err}")
    return screen


def state_key(route: str, settings: list[str]) -> str:
    return f"{route} [{'; '.join(settings)}]" if settings else route


def summary(key: str, screen: dict) -> str:
    controls = ", ".join(f"{k} ({c['kind']}: {c['current']!r}, {len(c.get('options', []))} options)"
                         for k, c in screen["labels"].items())
    return f"{key}: {len(screen['buttons'])} buttons; {len(screen['tables'])} tables; {controls or 'no labelled controls'}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--app", required=True)
    ap.add_argument("--route", action="append", required=True)
    ap.add_argument("--set", action="append", default=[], dest="settings")
    args = ap.parse_args()
    app = args.app.rstrip("/")
    existing = json.loads(args.out.read_text()) if args.out.exists() else {"routes": {}}
    routes = dict(existing.get("routes", {}))
    try:
        require_app(app)
    except SessionError as err:
        raise SystemExit(f"NOT READY: {err}") from err
    with open_page(app) as page:
        for route in args.route:
            key = state_key(route, args.settings)
            try:
                routes[key] = crawl_route(page, app, route, args.settings)
            except Exception as err:  # noqa: BLE001 — one broken screen must not lose the rest of the crawl
                routes[key] = {"error": str(err).splitlines()[0]}
                print(f"{key}: could not crawl — {routes[key]['error']}")
                continue
            print(summary(key, routes[key]))
    catalogue = {"app": app, "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "routes": routes}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalogue, indent=1, ensure_ascii=False))
    print(f"catalogue: {args.out}")


if __name__ == "__main__":
    main()
