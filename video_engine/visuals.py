"""Prozedurale Motion-Graphics-Hintergründe (kostenlos, lokal, Pillow).

Bilder werden 20 % grösser als das Video erzeugt, damit Kamerafahrten/Zooms Spielraum haben.
Alle wichtigen Elemente liegen im sicheren Bereich (oberes Drittel bis Mitte); unten bleiben
Untertitel und die TikTok-Bedienelemente frei.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OVERSCAN = 1.2

# (oben, unten, Akzent, Text) – dunkle, moderne Paletten
PALETTES: list[tuple[tuple[int, int, int], ...]] = [
    ((18, 24, 48), (52, 22, 74), (255, 196, 0), (255, 255, 255)),
    ((10, 38, 52), (8, 90, 96), (255, 112, 67), (255, 255, 255)),
    ((40, 14, 24), (110, 24, 48), (255, 215, 64), (255, 255, 255)),
    ((14, 30, 22), (24, 88, 56), (180, 255, 120), (255, 255, 255)),
    ((22, 22, 30), (60, 60, 84), (0, 200, 255), (255, 255, 255)),
    ((44, 26, 6), (120, 64, 10), (255, 236, 179), (255, 255, 255)),
]


def oversized(width: int, height: int) -> tuple[int, int]:
    w, h = int(width * OVERSCAN), int(height * OVERSCAN)
    return w + w % 2, h + h % 2


def _font(path: Path | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path and Path(path).is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def _gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = (np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t)
    return Image.fromarray(np.repeat(arr, w, axis=1).astype(np.uint8))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> list[str] | None:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        test = f"{cur} {wd}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = wd
            if draw.textlength(cur, font=font) > max_w:
                return None
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


def _fit(draw, text: str, font_path: Path | None, max_w: int, start: int, minimum: int, max_lines: int):
    size = start
    while size >= minimum:
        font = _font(font_path, size)
        lines = _wrap(draw, text, font, max_w, max_lines)
        if lines:
            return font, lines
        size = int(size * 0.9)
    font = _font(font_path, minimum)
    return font, (_wrap(draw, text, font, max_w, 99) or [text])[:max_lines]


def _draw_lines(draw, lines, font, cx: int, top: int, fill, stroke=0, stroke_fill=(0, 0, 0), spacing=1.1) -> int:
    y = top
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - lw // 2 - bbox[0], y - bbox[1]), line, font=font, fill=fill, stroke_width=stroke,
                  stroke_fill=stroke_fill)
        y += int(lh * spacing) + 4
    return y


def render_background(out_path: Path, width: int, height: int, *, style: str, keyword: str = "", number: str | None = None,
                      title: str = "", palette: int = 0, variant: int = 0, display_font: Path | None = None,
                      bold_font: Path | None = None, brand: str = "BÜRGERMEISTER BOB") -> Path:
    W, H = oversized(width, height)
    top, bottom, accent, text_col = PALETTES[palette % len(PALETTES)]
    rnd = random.Random(f"{style}|{keyword}|{palette}|{variant}")
    img = _gradient(W, H, top, bottom)

    # Bokeh-Kreise (weichgezeichnet)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for _ in range(10):
        r = rnd.randint(W // 14, W // 4)
        x, y = rnd.randint(-r, W + r), rnd.randint(-r, H + r)
        col = accent if rnd.random() < 0.35 else text_col
        ld.ellipse((x - r, y - r, x + r, y + r), fill=(*col, rnd.randint(14, 38)))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=W // 40))
    # diagonale Lichtstreifen
    stripes = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    offset = rnd.randint(0, W)
    for i in range(-3, 6):
        x0 = offset + i * W // 3
        sd.polygon([(x0, 0), (x0 + W // 10, 0), (x0 - W // 2 + W // 10, H), (x0 - W // 2, H)], fill=(*text_col, 10))
    img = Image.alpha_composite(img.convert("RGBA"), layer)
    img = Image.alpha_composite(img, stripes)
    draw = ImageDraw.Draw(img)

    # Sicherer Bereich = Schnittmenge aller möglichen Bildausschnitte bei Kamerafahrten:
    # Ausschnitt ist 1/1.2 = 83,3 % gross -> sichtbar ist immer [16,7 %, 83,3 %] (+ kleiner Rand)
    safe_l, safe_r = int(W * 0.19), int(W * 0.81)
    safe_w, cx = safe_r - safe_l, W // 2
    y0 = int(H * 0.25)

    # Marken-Pille oben links
    pill_font = _font(bold_font, max(12, H // 70))
    pb = draw.textbbox((0, 0), brand, font=pill_font)
    pw, ph = pb[2] - pb[0] + H // 50, pb[3] - pb[1] + H // 80
    px, py = safe_l, int(H * 0.19)
    draw.rounded_rectangle((px, py, px + pw, py + ph), radius=ph // 2, fill=accent)
    draw.text((px + (pw - (pb[2] - pb[0])) // 2 - pb[0], py + (ph - (pb[3] - pb[1])) // 2 - pb[1]), brand,
              font=pill_font, fill=top)

    kw = (keyword or title or "").strip()
    big, mid = H // 9, H // 16
    stroke = max(2, H // 300)
    if style == "number" and number:
        font, lines = _fit(draw, number, display_font, safe_w, int(H / 4.5), H // 12, 1)
        y = _draw_lines(draw, lines, font, cx, y0 + H // 30, text_col, stroke, top)
        if kw:
            f2, l2 = _fit(draw, kw.upper(), display_font, safe_w, mid, H // 30, 2)
            _draw_lines(draw, l2, f2, cx, y + H // 60, accent, stroke, top)
    elif style == "question":
        font, lines = _fit(draw, "?", display_font, safe_w, int(H / 3.6), H // 10, 1)
        y = _draw_lines(draw, lines, font, cx, y0, accent, stroke * 2, top)
        if kw:
            f2, l2 = _fit(draw, kw.upper(), display_font, safe_w, mid, H // 30, 2)
            _draw_lines(draw, l2, f2, cx, y + H // 80, text_col, stroke, top)
    elif style == "quote":
        qf = _font(display_font, int(H / 4))
        y = _draw_lines(draw, ["“"], qf, cx, y0, accent)
        f2, l2 = _fit(draw, kw.upper() or "BOB", display_font, safe_w, big, H // 28, 2)
        _draw_lines(draw, l2, f2, cx, y + H // 40, text_col, stroke, top)
    elif style == "cta":
        f1, l1 = _fit(draw, "FOLG BOB!", display_font, safe_w, big, H // 24, 1)
        bb = draw.textbbox((0, 0), l1[0], font=f1)
        bw, bh = bb[2] - bb[0] + H // 16, bb[3] - bb[1] + H // 24
        draw.rounded_rectangle((cx - bw // 2, y0 + H // 20, cx + bw // 2, y0 + H // 20 + bh), radius=bh // 3, fill=accent)
        _draw_lines(draw, l1, f1, cx, y0 + H // 20 + H // 48, top)
        f2, l2 = _fit(draw, "SCHREIB'S IN DIE KOMMENTARE", bold_font, safe_w, H // 32, H // 60, 2)
        _draw_lines(draw, l2, f2, cx, y0 + H // 20 + bh + H // 30, text_col)
    elif style in ("hook", "title"):
        label = "AUFGEPASST" if style == "hook" else "BOB ERKLÄRT"
        f0 = _font(bold_font, H // 40)
        _draw_lines(draw, [label], f0, cx, y0, accent)
        f1, l1 = _fit(draw, (kw or title).upper(), display_font, safe_w, int(big * 1.15), H // 30, 3)
        _draw_lines(draw, l1, f1, cx, y0 + H // 22, text_col if style == "title" else accent, stroke, top)
    else:  # keyword
        f1, l1 = _fit(draw, kw.upper() or "BOB", display_font, safe_w, big, H // 30, 2)
        y = _draw_lines(draw, l1, f1, cx, y0 + H // 20, text_col, stroke, top)
        bar_w = int(safe_w * (0.3 + 0.2 * (variant % 3)))
        draw.rounded_rectangle((cx - bar_w // 2, y + H // 80, cx + bar_w // 2, y + H // 80 + H // 120),
                               radius=H // 240, fill=accent)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=False)
    return out_path


def cover_resize(src: Path, out_path: Path, width: int, height: int) -> Path:
    """Fremdbild (z. B. KI-generiert) auf das Overscan-Format zuschneiden."""
    W, H = oversized(width, height)
    im = Image.open(src).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1), Image.LANCZOS)
    left, top = (im.width - W) // 2, (im.height - H) // 2
    im.crop((left, top, left + W, top + H)).save(out_path, "PNG")
    return Path(out_path)
