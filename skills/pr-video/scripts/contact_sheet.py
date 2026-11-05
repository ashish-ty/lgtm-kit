"""A quick record of a capture: one row per beat, its shots side by side, the cursor's landing
point ringed (amber for a click, blue for a hover), and the beat's narration or caption.
Card beats show as a labelled tile; the real card is drawn by Remotion.

    contact_sheet.py <video folder>/captures
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THUMB_W = 480
MAX_SHOTS = 4
PAD = 16
TEXT_H = 84
PAPER, INK, ACCENT, CLICK, MUTED, CODE_BG = "#f6f7f9", "#14171c", "#2563eb", "#d97706", "#6b7280", "#1e2229"
FONTS = ("/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
CSS_WIDTH = 1920


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def thumb(captures: Path, shot: dict, crop: list | None = None) -> Image.Image:
    image = Image.open(captures / shot["image"]).convert("RGB")
    small = image.resize((THUMB_W, round(image.height * THUMB_W / image.width)))
    draw = ImageDraw.Draw(small)
    if crop:  # what the frame will show of this screen
        x, y, w, h = (v * THUMB_W / CSS_WIDTH for v in crop)
        draw.rectangle([x, y, x + w, y + h], outline=ACCENT, width=2)
    if shot.get("cursor"):
        x, y = (v * THUMB_W / CSS_WIDTH for v in shot["cursor"])
        draw.ellipse([x - 10, y - 10, x + 10, y + 10], outline=CLICK if shot.get("click", True) else ACCENT, width=3)
    return small


def card_tile(beat: dict, height: int) -> Image.Image:
    tile = Image.new("RGB", (THUMB_W, height), CODE_BG)
    draw = ImageDraw.Draw(tile)
    card = beat["card"]
    if beat["do"] == "code":
        label = f"{card['file']}  ·  hunk {card['hunk'] + 1}/{card['hunks']}  ·  {len(card['rows'])} rows"
    elif beat["do"] == "tests":
        label = f"tests  ·  {len(card['files']) + card['more']} files  ·  {card['total_names']} tests"
    else:
        label = "overview  ·  " + ", ".join(f"{g['name']} {len(g['files']) + g['more']}" for g in card["groups"])
    draw.text((16, 16), label, fill="#e5e7eb", font=font(16))
    for i, row in enumerate((card.get("rows") or [])[:10]):
        colour = {"+": "#4ade80", "-": "#f87171"}.get(row["kind"], "#9ca3af")
        draw.text((16, 48 + i * 22), f"{row['kind']} {row['text'][:52]}", fill=colour, font=font(14))
    return tile


def build(captures: Path, manifest: dict) -> Path:
    beats = manifest["beats"]
    thumb_h = round(THUMB_W * 9 / 16)
    row_h = thumb_h + TEXT_H + PAD
    sheet = Image.new("RGB", (PAD + MAX_SHOTS * (THUMB_W + PAD), PAD + max(1, len(beats)) * row_h), PAPER)
    draw = ImageDraw.Draw(sheet)
    title, body = font(20), font(16)
    for row, beat in enumerate(beats):
        top = PAD + row * row_h
        if "card" in beat:
            sheet.paste(card_tile(beat, thumb_h), (PAD, top))
        else:
            shots = beat["shots"][-MAX_SHOTS:]  # a long multiselect keeps its last picks and the result
            for col, shot in enumerate(shots):
                crop = beat.get("crop") if col == len(shots) - 1 else None
                sheet.paste(thumb(captures, shot, crop), (PAD + col * (THUMB_W + PAD), top))
        seconds = (beat.get("voice") or {}).get("seconds")
        spoken = f" · voice {seconds:.1f}s" if seconds else ""
        draw.text((PAD, top + thumb_h + 8), f"{beat['id']} · {beat['do']} · hold {beat['hold']:.1f}s{spoken}",
                  fill=ACCENT, font=title)
        words = beat.get("say") or beat.get("caption") or "(silent)"
        draw.text((PAD, top + thumb_h + 34), "\n".join(textwrap.wrap(words, 200)[:2]),
                  fill=INK if words != "(silent)" else MUTED, font=body)
    out = captures / "contact-sheet.png"
    sheet.save(out)
    return out


def main() -> None:
    captures = Path(sys.argv[1])
    print(build(captures, json.loads((captures / "manifest.json").read_text())))


if __name__ == "__main__":
    main()
