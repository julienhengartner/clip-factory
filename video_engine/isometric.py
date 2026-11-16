"""Isometrische Stadtansicht von Bobstadt (kostenlos, Pillow) – passend zum #isometric/#citybuilder-Stil.

- Gebäude aus dem Stadtzustand stehen auf festen Bauplätzen (Spirale um das Zentrum).
- Zusätzliche kleine Wohnhäuser zeigen die Einwohnerzahl (1 Haus je 1.000 Einwohner, gedeckelt).
- Hervorhebung + Bau-Animation (Gebäude wächst aus dem Boden) für Bau-Episoden.
- Karten-Overlays: Statistik, Preis, Finanzierungsbalken, Abstimmung, Meilenstein.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from brain.city import DEFAULT_CATALOG, fmt_eur, fmt_int

GRID = 9
ROAD_ROWS = {4}
ROAD_COLS = {4}
SHAPES = {b.key: (b.shape, b.color) for b in DEFAULT_CATALOG}
NAMES = {b.key: b.name for b in DEFAULT_CATALOG}
HEIGHT = {"house": 0.7, "tower": 2.6, "park": 0.08, "stadium": 0.55, "hospital": 1.5, "station": 0.8, "generic": 1.0}
ACCENT = (255, 196, 0)


def _font(path: Path | None, size: int):
    if path and Path(path).is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def _fit(draw, text: str, path: Path | None, max_w: int, start: int, minimum: int = 10):
    """Schriftgrösse so wählen, dass der Text in max_w passt."""
    size = start
    while size > minimum:
        f = _font(path, size)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_w:
            return f
        size = int(size * 0.92)
    return _font(path, minimum)


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def slots() -> list[tuple[int, int]]:
    """Bauplätze spiralförmig vom Zentrum nach aussen, Strassen ausgenommen."""
    c = GRID // 2
    cells = [(i, j) for i in range(GRID) for j in range(GRID) if i not in ROAD_ROWS and j not in ROAD_COLS]
    return sorted(cells, key=lambda p: (max(abs(p[0] - c), abs(p[1] - c)), math.atan2(p[1] - c, p[0] - c)))


class IsoCanvas:
    def __init__(self, w: int, h: int, *, center_y: float = 0.56):
        self.w, self.h = w, h
        self.tw = w * 0.105
        self.th = self.tw / 2
        self.ox = w / 2
        self.oy = h * center_y - GRID * self.th / 2

    def tile(self, i: int, j: int, lift: float = 0.0) -> list[tuple[float, float]]:
        cx = self.ox + (i - j) * self.tw / 2
        cy = self.oy + (i + j) * self.th / 2 - lift
        return [(cx, cy - self.th / 2), (cx + self.tw / 2, cy), (cx, cy + self.th / 2), (cx - self.tw / 2, cy)]

    def center(self, i: int, j: int) -> tuple[float, float]:
        return self.ox + (i - j) * self.tw / 2, self.oy + (i + j) * self.th / 2


def _box(draw: ImageDraw.ImageDraw, cv: IsoCanvas, i: int, j: int, height_px: float, color, inset: float = 0.12,
         outline=None, width=0):
    t = cv.tile(i, j)
    cx, cy = cv.center(i, j)
    pts = [(cx + (x - cx) * (1 - inset), cy + (y - cy) * (1 - inset)) for x, y in t]
    top = [(x, y - height_px) for x, y in pts]
    left = [pts[3], pts[2], top[2], top[3]]
    right = [pts[2], pts[1], top[1], top[2]]
    draw.polygon(left, fill=_shade(color, 0.72))
    draw.polygon(right, fill=_shade(color, 0.55))
    draw.polygon(top, fill=_shade(color, 1.08))
    if outline:
        draw.line(top + [top[0]], fill=outline, width=width)
        draw.line([pts[3], top[3]], fill=outline, width=width)
        draw.line([pts[1], top[1]], fill=outline, width=width)
        draw.line([pts[2], top[2]], fill=outline, width=width)
    return top


def _building(draw, cv: IsoCanvas, i: int, j: int, kind: str, growth: float = 1.0, highlight: bool = False,
              rnd: random.Random | None = None):
    shape, color = SHAPES.get(kind, ("generic", (180, 180, 180)))
    rnd = rnd or random.Random(f"{kind}{i}{j}")
    full = HEIGHT[shape] * cv.tw * 0.6
    hpx = max(1.0, full * max(0.0, min(1.0, growth)))
    outline = ACCENT if highlight else None
    lw = max(2, int(cv.tw / 30))
    if shape == "park":
        draw.polygon(cv.tile(i, j, 1), fill=_shade(color, 0.95), outline=outline, width=lw if highlight else 0)
        if kind == "freibad":
            cx, cy = cv.center(i, j)
            draw.polygon([(cx, cy - cv.th * 0.3), (cx + cv.tw * 0.3, cy), (cx, cy + cv.th * 0.3), (cx - cv.tw * 0.3, cy)],
                         fill=(120, 210, 255))
        else:
            for _ in range(3 if growth >= 1 else int(3 * growth)):
                cx, cy = cv.center(i, j)
                x = cx + rnd.uniform(-cv.tw * 0.25, cv.tw * 0.25)
                y = cy + rnd.uniform(-cv.th * 0.2, cv.th * 0.2)
                r = cv.tw * 0.09
                draw.rectangle((x - r * 0.15, y - r * 0.4, x + r * 0.15, y + r * 0.2), fill=(110, 80, 50))
                draw.ellipse((x - r, y - r * 2.2, x + r, y - r * 0.2), fill=(46, 140, 70))
        return
    top = _box(draw, cv, i, j, hpx, color, inset=0.18 if shape == "tower" else 0.12, outline=outline, width=lw)
    if growth < 1.0:  # Baugerüst
        for k in range(1, 4):
            y = k * hpx / 4
            pts = cv.tile(i, j)
            draw.line([(pts[3][0], pts[3][1] - y), (pts[2][0], pts[2][1] - y), (pts[1][0], pts[1][1] - y)],
                      fill=(255, 200, 60), width=max(1, lw // 2))
        return
    if shape == "house":
        apex = ((top[0][0] + top[2][0]) / 2, (top[0][1] + top[2][1]) / 2 - cv.th * 0.7)
        draw.polygon([top[3], top[2], apex], fill=(170, 60, 50))
        draw.polygon([top[2], top[1], apex], fill=(130, 45, 40))
    elif shape == "tower":
        cx, _ = cv.center(i, j)
        for k in range(int(hpx // (cv.th * 0.45))):
            y = top[2][1] + cv.th * 0.3 + k * cv.th * 0.45
            draw.line([(cx - cv.tw * 0.28, y - cv.th * 0.25), (cx - cv.tw * 0.04, y - cv.th * 0.13)],
                      fill=(255, 240, 170), width=max(1, lw // 2))
    elif shape == "hospital":
        cx = (top[0][0] + top[2][0]) / 2
        cy = (top[0][1] + top[2][1]) / 2
        s = cv.tw * 0.12
        draw.rectangle((cx - s, cy - s / 3, cx + s, cy + s / 3), fill=(220, 40, 40))
        draw.rectangle((cx - s / 3, cy - s * 0.6, cx + s / 3, cy + s * 0.6), fill=(220, 40, 40))
    elif shape == "stadium":
        draw.polygon([((a[0] + c[0]) / 2, (a[1] + c[1]) / 2) for a, c in zip(top, top[1:] + top[:1])], fill=(60, 170, 70))


def render_city(out_path: Path | None, width: int, height: int, city: dict, *, highlight: str | None = None,
                growth: float = 1.0, overlay: str | None = None, data: dict | None = None,
                display_font: Path | None = None, bold_font: Path | None = None, palette: int = 0,
                safe_top: float = 0.12, title: str | None = None, margin: float = 0.08) -> Image.Image:
    data = data or {}
    W, H = width, height
    skies = [((24, 32, 64), (90, 140, 200)), ((30, 20, 50), (200, 110, 90)), ((10, 40, 60), (80, 170, 190))]
    top_c, bot_c = skies[palette % len(skies)]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a * (1 - t) + b * t) for a, b in zip(top_c, bot_c)))
    cv = IsoCanvas(W, H)
    # Boden und Strassen
    for s in range(2 * GRID - 1):
        for i in range(GRID):
            j = s - i
            if 0 <= j < GRID:
                road = i in ROAD_ROWS or j in ROAD_COLS
                col = (92, 96, 108) if road else ((86, 160, 80) if (i + j) % 2 else (78, 150, 74))
                d.polygon(cv.tile(i, j), fill=col, outline=(60, 110, 60) if not road else (80, 84, 96))
    # Gebäude: Bestand + Wohnhäuser nach Einwohnerzahl
    placed: dict[tuple[int, int], tuple[str, bool]] = {}
    sl = slots()
    k = 0
    for b in city.get("buildings", []):
        if b.get("status") == "built" and k < len(sl):
            placed[sl[k]] = (b["kind"], False)
            k += 1
    hl_slot = None
    if highlight and k < len(sl):
        hl_slot = sl[k]
        placed[hl_slot] = (highlight, True)
        k += 1
    houses = min(len(sl) - k, int((city.get("residents") or 0) / 1000))
    for n in range(houses):
        placed[sl[k + n]] = ("wohnviertel", False)
    for s in range(2 * GRID - 1):  # von hinten nach vorne zeichnen
        for i in range(GRID):
            j = s - i
            if (i, j) in placed:
                kind, hl = placed[(i, j)]
                _building(d, cv, i, j, kind, growth if hl else 1.0, highlight=hl)

    fb, fd = bold_font, display_font
    y_top = int(H * safe_top)
    # Marken-Pille und Statistikleiste
    pill = _font(fb, max(10, H // 60))
    label = "BÜRGERMEISTER BOB · BOBSTADT"
    bb = d.textbbox((0, 0), label, font=pill)
    pw, ph = bb[2] - bb[0] + H // 45, bb[3] - bb[1] + H // 70
    px = int(W * margin)
    d.rounded_rectangle((px, y_top, px + pw, y_top + ph), radius=ph // 2, fill=ACCENT)
    d.text((px + (pw - (bb[2] - bb[0])) // 2 - bb[0], y_top + (ph - (bb[3] - bb[1])) // 2 - bb[1]), label,
           font=pill, fill=(30, 24, 0))
    stats = f"{fmt_int(city.get('residents') or 0)} EINWOHNER   ·   KASSE {fmt_eur(city.get('available_eur') or 0).upper()}"
    sf = _fit(d, stats, fb, int(W * (1 - 2 * margin)), max(10, H // 55))
    sb = d.textbbox((0, 0), stats, font=sf)
    d.text(((W - (sb[2] - sb[0])) // 2, y_top + ph + H // 60), stats, font=sf, fill=(255, 255, 255),
           stroke_width=max(1, H // 600), stroke_fill=(0, 0, 0))
    card_y = y_top + ph + H // 18

    if hl_slot and growth >= 1.0:
        cx, cy = cv.center(*hl_slot)
        name = NAMES.get(highlight, highlight)
        f = _font(fb, max(10, H // 50))
        txt = f"NEU: {name}".upper()
        tb = d.textbbox((0, 0), txt, font=f)
        tw, th = tb[2] - tb[0] + H // 50, tb[3] - tb[1] + H // 80
        ty = cy - cv.tw * 1.4
        d.rounded_rectangle((cx - tw / 2, ty - th, cx + tw / 2, ty), radius=th // 2, fill=ACCENT)
        d.text((cx - (tb[2] - tb[0]) / 2 - tb[0], ty - th + (th - (tb[3] - tb[1])) / 2 - tb[1]), txt, font=f, fill=(30, 24, 0))

    def panel(h_frac: float):
        x0, x1 = int(W * margin), int(W * (1 - margin))
        y1 = card_y + int(H * h_frac)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((x0, card_y, x1, y1), radius=H // 60, fill=(10, 12, 20, 200))
        img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))
        return x0, x1, y1

    inner_w = int(W * (1 - 2 * margin)) - H // 30

    def centered(text, font, y, fill=(255, 255, 255)):
        b = d.textbbox((0, 0), text, font=font)
        d.text(((W - (b[2] - b[0])) // 2 - b[0], y - b[1]), text, font=font, fill=fill)
        return y + (b[3] - b[1])

    if overlay == "cost":
        panel(0.13)
        d = ImageDraw.Draw(img)
        head = (data.get("label", "") + "  " if data.get("label") else "") + str(data.get("name", "")).upper()
        y = centered(head, _fit(d, head, fd, inner_w, H // 28), card_y + H // 50, ACCENT)
        price = fmt_eur(data.get("cost") or 0)
        centered(price, _fit(d, price, fd, inner_w, H // 18), y + H // 60)
    elif overlay == "funding":
        x0, x1, _ = panel(0.12)
        d = ImageDraw.Draw(img)
        have, need = max(0, int(data.get("have", 0))), max(1, int(data.get("need", 1)))
        lab = str(data.get("label", "")).upper()
        y = centered(lab, _fit(d, lab, fd, inner_w, H // 32), card_y + H // 60, ACCENT)
        bar_y = y + H // 50
        d.rounded_rectangle((x0 + H // 40, bar_y, x1 - H // 40, bar_y + H // 40), radius=H // 80, fill=(60, 64, 80))
        frac = min(1.0, have / need)
        d.rounded_rectangle((x0 + H // 40, bar_y, x0 + H // 40 + int((x1 - x0 - H // 20) * frac), bar_y + H // 40),
                            radius=H // 80, fill=(61, 220, 151))
        amount = f"{fmt_eur(have)} / {fmt_eur(need)}"
        centered(amount, _fit(d, amount, fb, inner_w, H // 50), bar_y + H // 30)
    elif overlay == "vote":
        opts = data.get("options", [])[:3]
        panel(0.07 * max(1, len(opts)) + 0.03)
        d = ImageDraw.Draw(img)
        f1, f2 = _font(fd, H // 34), _font(fb, H // 55)
        for n, o in enumerate(opts):
            y = card_y + H // 50 + n * int(H * 0.07)
            d.text((int(W * (margin + 0.05)), y), f"{'ABC'[n]}  {str(o['name']).upper()}", font=f1, fill=ACCENT if n == 0 else (255, 255, 255))
            if o.get("cost"):
                d.text((int(W * (margin + 0.05)), y + H // 30), fmt_eur(o["cost"]), font=f2, fill=(200, 205, 220))
    elif overlay == "milestone":
        centered(str(data.get("number", "")), _font(fd, H // 8), card_y, (255, 255, 255))
        centered("EINWOHNER", _font(fd, H // 22), card_y + H // 7, ACCENT)
    elif overlay == "keyword" and (data.get("keyword") or title):
        kw = str(data.get("keyword") or title).upper()
        centered(kw, _fit(d, kw, fd, inner_w, H // 14), card_y + H // 50, ACCENT)

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "PNG")
    return img


def render_build_frames(out_dir: Path, width: int, height: int, city: dict, highlight: str, frames: int,
                        **kw) -> Path:
    """Bau-Animation: Gebäude wächst in den ersten 70 % der Frames, danach Schild 'NEU'."""
    out_dir.mkdir(parents=True, exist_ok=True)
    grow_frames = max(1, int(frames * 0.7))
    for n in range(frames):
        g = min(1.0, (n + 1) / grow_frames)
        render_city(out_dir / f"f_{n:04d}.png", width, height, city, highlight=highlight, growth=g,
                    safe_top=0.07, **kw)
    return out_dir
