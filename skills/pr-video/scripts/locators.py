"""Turn a storyboard target into a Playwright locator on the live page.

Role and visible text first: nothing here needs the app's code changed. ``label`` covers custom
dropdowns whose ``<label>`` is not linked to them: "the control under label X" is the element
that follows that label, and its first child is the trigger. When a control cannot be reached
any of these ways, use ``{demo: name}`` for a ``data-demo`` attribute only if the PR itself adds
one — pr-video never edits the app under review.
"""

from __future__ import annotations

import difflib
import re

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

FIND_TIMEOUT_MS = 15_000
OPEN_TIMEOUT_MS = 3_000
VISIBLE_NAMES_JS = """() => {
  const seen = new Set();
  for (const e of document.querySelectorAll('label,button,[role=button],[role=option],[role=tab],th,h1,h2,h3,h4,a'))
    if (e.offsetWidth || e.offsetHeight) { const t = e.innerText.trim().split('\\n')[0]; if (t && t.length < 60) seen.add(t); }
  return [...seen];
}"""


class TargetNotFound(LookupError):
    """A storyboard target is not on the screen."""


def exact(text: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


def control(page: Page, label: str) -> Locator:
    """The element that follows ``<label>label</label>`` — the custom dropdown it heads. Labels
    upper-cased in CSS are recorded that way by the crawl, so the match ignores case."""
    caption = re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)
    return page.locator("label").filter(has_text=caption).first.locator("xpath=following-sibling::*[1]")


def trigger(page: Page, label: str) -> Locator:
    """What to click under a label: a plain field itself, or a custom dropdown's first child."""
    field = control(page, label)
    try:
        if field.evaluate("e => ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName)", timeout=FIND_TIMEOUT_MS):
            return field
    except PlaywrightError:
        pass
    return field.locator(":scope > *").first


def option(page: Page, value: str, label: str | None = None) -> Locator:
    """An open dropdown's entry: role=option when the component marks it, otherwise the last
    exact text match (a list renders after its trigger, so the last match is the entry, not a chip)."""
    scope = control(page, label) if label else page
    by_role = scope.get_by_role("option", name=value, exact=True)
    by_text = scope.get_by_text(value, exact=True).last
    either = by_role.first.or_(by_text)
    try:  # the list renders a beat after the click that opens it
        either.first.wait_for(state="visible", timeout=OPEN_TIMEOUT_MS)
    except PlaywrightError:
        pass
    return by_role.first if by_role.count() else by_text


def cell(page: Page, row: str, column: str) -> Locator:
    headers = page.locator("th:visible")
    header = headers.filter(has_text=exact(column))
    if not header.count():
        header = headers.filter(has_text=re.compile(rf"^\s*{re.escape(column)}"))
    if not header.count():
        raise TargetNotFound(f"no table column {column!r}{suggest(page, column)}")
    index = header.first.evaluate("e => [...e.parentElement.children].indexOf(e)")
    rows = page.locator("tbody tr").filter(has=page.locator("td:first-child").filter(has_text=exact(row)))
    if not rows.count():
        raise TargetNotFound(f"no table row {row!r} under column {column!r}")
    return rows.first.locator("td").nth(index)


STAT_SIDES = ("xpath=preceding-sibling::*[1]", "xpath=following-sibling::*[1]",
              "xpath=../preceding-sibling::*[1]", "xpath=../following-sibling::*[1]")


def stat(page: Page, label: str) -> Locator:
    """The figure printed beside a label on a stat tile: above or below it, sometimes one level up
    when the label shares a row with an icon. The first neighbour holding a digit wins. Matches
    ignore case (CSS upper-casing) and take the visible copy."""
    caption = page.get_by_text(re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)).locator("visible=true").first
    for side in STAT_SIDES:
        candidate = caption.locator(side)
        try:
            if candidate.count() and re.search(r"\d", candidate.inner_text(timeout=2000)):
                return candidate
        except PlaywrightError:
            continue
    return caption.locator(STAT_SIDES[0])  # resolve() then reports it as not on screen


def pick(matches: Locator, nth) -> Locator:
    """Which of several matches: a modal repeats labels from the page behind it, and the modal's
    copy comes later in the DOM, so ``nth: last`` reaches it."""
    if nth == "last":
        return matches.last
    return matches.nth(nth) if isinstance(nth, int) else matches.first


def resolve(page: Page, target: dict, timeout_ms: int = FIND_TIMEOUT_MS) -> Locator:
    found = resolve_now(page, target)
    try:
        found.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightError as err:
        name = next(str(v) for k, v in target.items() if k not in ("name", "at", "nth")) if "role" not in target else target["name"]
        raise TargetNotFound(f"{target} is not on screen{suggest(page, name)}") from err
    return found


def resolve_now(page: Page, target: dict) -> Locator:
    """The locator for a target, without waiting for it to appear."""
    nth = target.get("nth")
    if "label" in target:
        found = trigger(page, target["label"])
    elif "role" in target:
        found = pick(page.get_by_role(target["role"], name=target["name"], exact=True), nth)
    elif "text" in target:  # whole text, ignoring case: CSS upper-cases many labels
        found = pick(page.get_by_text(re.compile(rf"^\s*{re.escape(target['text'])}\s*$", re.IGNORECASE))
                     .locator("visible=true"), nth)
    elif "placeholder" in target:  # text fields that carry no label, only a hint
        found = pick(page.get_by_placeholder(target["placeholder"], exact=True), nth)
    elif "option" in target:
        found = option(page, target["option"])
    elif "cell" in target:
        found = cell(page, str(target["cell"]["row"]), str(target["cell"]["column"]))
    elif "stat" in target:
        found = stat(page, target["stat"])
    elif "demo" in target:
        found = page.locator(f'[data-demo="{target["demo"]}"]').first
    else:
        found = page.locator(target["css"]).first
    return found


def suggest(page: Page, name: str) -> str:
    close = difflib.get_close_matches(name, page.evaluate(VISIBLE_NAMES_JS), n=5, cutoff=0.4)
    return f" — on screen instead: {close}" if close else ""
