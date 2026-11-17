"""Canonical starting state of Bobbington (becomes Bobbington_City_v001).

Pure Python – no Blender needed. Every element of the town is recorded as a data object with a stable ID,
group (e.g. 'main_street/house_3'), category, exact transform/dimensions, material and text. Blender scenes are
built FROM this data (blender/city_scene.py); after v001 the town only changes through story events
(bobbington/citystate.py).
"""
from __future__ import annotations

import math
import random
from contextlib import contextmanager

OFFSETS = {"mayors_office": 0.0, "council_chamber": 40.0, "main_street": 80.0, "pub": 120.0, "title_card": 160.0}
GEORGIA = "C:/Windows/Fonts/georgiab.ttf"


def mat(name: str, colour: str, rough: float = 0.6, metal: float = 0.0, emission: float = 0.0) -> dict:
    return {"name": name, "colour": colour, "rough": rough, "metal": metal, "emission": emission}


class Recorder:
    """Records primitives as data. Signatures mirror blender/characters.py so templates read naturally."""

    def __init__(self):
        self.objects: list[dict] = []
        self.location = ""
        self._group: str | None = None
        self._category = "structure"
        self._counts: dict[str, int] = {}

    @contextmanager
    def group(self, name: str, category: str = "structure"):
        prev = (self._group, self._category)
        self._group, self._category = name, category
        try:
            yield
        finally:
            self._group, self._category = prev

    def _add(self, kind: str, name: str, **params) -> dict:
        group = self._group or name
        key = f"{self.location}/{group}/{name}"
        n = self._counts.get(key, 0)
        self._counts[key] = n + 1
        obj = {"id": f"{key}#{n}", "location": self.location, "group": f"{self.location}/{group}", "name": name,
               "kind": kind, "category": self._category if self._group else _category_of(name), "condition": "intact",
               **{k: _round(v) for k, v in params.items()}}
        self.objects.append(obj)
        return obj

    def cube(self, name, loc, scale, m, bevel=0.0):
        return self._add("cube", name, loc=loc, scale=scale, material=m, bevel=bevel)

    def cylinder(self, name, loc, radius, depth, m, rot=(0, 0, 0), vertices=24, scale=(1, 1, 1)):
        return self._add("cylinder", name, loc=loc, radius=radius, depth=depth, material=m, rot=rot, vertices=vertices,
                         scale=scale)

    def cone(self, name, loc, r1, r2, depth, m, rot=(0, 0, 0), vertices=24):
        return self._add("cone", name, loc=loc, r1=r1, r2=r2, depth=depth, material=m, rot=rot, vertices=vertices)

    def sphere(self, name, loc, scale, m):
        return self._add("sphere", name, loc=loc, scale=scale, material=m)

    def torus(self, name, loc, major, minor, m, rot=(0, 0, 0)):
        return self._add("torus", name, loc=loc, major=major, minor=minor, material=m, rot=rot)

    def text(self, name, body, loc, size=0.1, colour="ink", extrude=0.003, font=GEORGIA,
             rot=(math.radians(90), 0, 0)):
        return self._add("text", name, body=body, loc=loc, size=size, colour=colour, extrude=extrude, font=font, rot=rot)

    def light(self, name, loc, target, energy, size, color):
        return self._add("light", name, loc=loc, target=target, energy=energy, size=size, color=color)


def _round(v):
    if isinstance(v, float):
        return round(v, 5)
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    return v


def _category_of(name: str) -> str:
    for cat, words in (("light", ("_key", "_fill", "_rim", "_warm", "_window")),
                       ("sign", ("sign", "fascia", "label", "plaque")),
                       ("vegetation", ("tree", "hedge")),
                       ("street_furniture", ("lamp", "bin", "bench", "post")),
                       ("furniture", ("desk", "chair", "shelf", "stool", "bar", "lectern")),
                       ("decoration", ("flag", "banner", "portrait", "book", "bottle", "rug", "bunt"))):
        if any(w in name for w in words):
            return cat
    return "structure"


def room(k: Recorder, ox, wall, lower, floor, width=9.0, depth=6.0, height=7.0):
    with k.group("room", "structure"):
        k.cube("floor", (ox, depth / 2 - 2.5, -0.05), (width, depth + 4, 0.1), mat(f"floor_{floor}", floor, 0.7))
        k.cube("wall_back", (ox, depth - 2.5, height / 2), (width, 0.2, height), mat(f"wall_{wall}", wall, 0.85))
        k.cube("wainscot", (ox, depth - 2.62, 0.55), (width, 0.1, 1.1), mat(f"wains_{lower}", lower, 0.5))
        k.cube("rail", (ox, depth - 2.68, 1.12), (width, 0.06, 0.06), mat("gold", "gold", 0.3, 1.0))
        for s in (-1, 1):
            k.cube("wall_side", (ox + s * width / 2, depth / 2 - 2.5, height / 2), (0.2, depth + 4, height),
                   mat(f"wall_{wall}", wall, 0.85))
    return depth - 2.5


def window(k: Recorder, x, y, z, w=1.2, h=1.6):
    with k.group("window", "structure"):
        k.cube("win_frame", (x, y - 0.05, z), (w + 0.16, 0.1, h + 0.16), mat("cream_frame", "cream", 0.4))
        k.cube("win_glass", (x, y - 0.11, z), (w, 0.02, h), mat("sky_glass", "sky_day", 0.1, emission=1.2))
        k.cube("win_bar_v", (x, y - 0.13, z), (0.05, 0.02, h), mat("cream_frame", "cream", 0.4))
        k.cube("win_bar_h", (x, y - 0.13, z), (w, 0.02, 0.05), mat("cream_frame", "cream", 0.4))


def mayors_office(k: Recorder):
    k.location = "mayors_office"
    ox = OFFSETS[k.location]
    back = room(k, ox, "cream", "burgundy_dark", "#5A3A26")
    window(k, ox + 2.6, back, 2.2)
    with k.group("portrait", "decoration"):
        k.cube("portrait_frame", (ox - 1.6, back - 0.05, 2.5), (1.1, 0.08, 1.4), mat("gold", "gold", 0.3, 1.0))
        k.cube("portrait", (ox - 1.6, back - 0.1, 2.5), (0.9, 0.04, 1.2), mat("portrait_bg", "racing_green", 0.8))
        k.sphere("portrait_head", (ox - 1.6, back - 0.15, 2.65), (0.22, 0.04, 0.24), mat("portrait_skin", "#E9B99A", 0.7))
        k.cube("portrait_tash", (ox - 1.6, back - 0.18, 2.55), (0.4, 0.03, 0.06), mat("portrait_tash", "#E4DED3", 0.8))
        k.text("portrait_label", "A SELF-PORTRAIT", (ox - 1.6, back - 0.12, 1.88), size=0.07, colour="gold")
    wood = mat("wood_desk", "#6B3F22", 0.45)
    with k.group("desk", "furniture"):
        k.cube("desk", (ox, 0.55, 0.42), (2.4, 0.95, 0.84), wood, bevel=0.03)
        k.cube("desk_top", (ox, 0.55, 0.86), (2.5, 1.05, 0.05), mat("desk_leather", "racing_green", 0.5))
        k.cube("desk_trim", (ox, 0.05, 0.6), (2.4, 0.02, 0.06), mat("gold", "gold", 0.3, 1.0))
        k.cylinder("inkwell", (ox - 0.8, 0.5, 0.95), 0.07, 0.12, mat("ink", "ink", 0.2))
        k.cube("papers", (ox + 0.7, 0.45, 0.9), (0.4, 0.3, 0.03), mat("paper", "cream", 0.9))
        k.text("desk_label", "MAYOR", (ox, 0.04, 0.6), size=0.12, colour="gold")
    with k.group("chair", "furniture"):
        k.cube("chair_back", (ox, 1.55, 1.25), (0.9, 0.15, 1.4), mat("chair_red", "burgundy", 0.5), bevel=0.05)
    with k.group("flag", "decoration"):
        k.cylinder("flagpole", (ox + 3.6, back - 0.4, 1.5), 0.03, 3.0, mat("gold", "gold", 0.3, 1.0))
        k.cube("flag_b", (ox + 3.2, back - 0.4, 2.55), (0.8, 0.02, 0.55), mat("flag_burgundy", "burgundy", 0.8))
        k.cube("flag_g", (ox + 3.2, back - 0.42, 2.55), (0.8, 0.02, 0.12), mat("gold_cloth", "gold", 0.6))
    with k.group("bookshelf", "furniture"):
        k.cube("shelf", (ox - 3.6, back - 0.3, 1.4), (1.2, 0.4, 2.8), wood)
        rnd = random.Random(1)
        for r in range(4):
            x = ox - 4.1
            while x < ox - 3.1:
                w = rnd.uniform(0.06, 0.12)
                k.cube("book", (x + w / 2, back - 0.5, 0.4 + r * 0.65 + 0.2), (w, 0.25, rnd.uniform(0.3, 0.45)),
                       mat(f"book{rnd.randint(0, 3)}", rnd.choice(["burgundy", "racing_green", "gold", "slate"]), 0.7))
                x += w + 0.01
    with k.group("rug", "decoration"):
        k.cube("rug", (ox, -0.6, 0.005), (4.0, 2.4, 0.01), mat("rug", "burgundy", 0.9))
    with k.group("lighting", "light"):
        k.light("office_key", (ox - 2.0, -3.0, 3.2), (ox, 0.5, 1.4), 650, 3.0, (1.0, 0.9, 0.78))
        k.light("office_fill", (ox + 2.5, -2.0, 2.0), (ox, 0.5, 1.4), 220, 4.0, (0.85, 0.9, 1.0))
        k.light("office_window", (ox + 2.6, back - 0.6, 2.4), (ox, 0.6, 1.2), 160, 1.5, (0.9, 0.95, 1.0))


def council_chamber(k: Recorder):
    k.location = "council_chamber"
    ox = OFFSETS[k.location]
    back = room(k, ox, "cream", "racing_green", "#4A3324", width=11)
    with k.group("motto", "sign"):
        k.cube("frame", (ox, back - 0.04, 3.1), (3.52, 0.06, 0.72), mat("gold", "gold", 0.3, 1.0))
        k.cube("frame_bg", (ox, back - 0.08, 3.1), (3.4, 0.04, 0.6), mat("bg_burgundy_dark", "burgundy_dark", 0.7))
        k.text("motto", "EX ERRORE GLORIA", (ox, back - 0.11, 3.1), size=0.28, colour="gold")
    with k.group("columns", "structure"):
        for x in (-4.6, 4.6):
            k.cylinder("column", (ox + x, back - 0.3, 2.1), 0.22, 4.2, mat("stone", "stone", 0.6))
    with k.group("dais", "furniture"):
        k.cube("dais", (ox, 1.5, 0.15), (3.2, 1.6, 0.3), mat("wood_dais", "#5C3720", 0.5))
        k.cube("lectern", (ox, 0.95, 0.75), (1.1, 0.5, 0.9), mat("wood_desk", "#6B3F22", 0.45), bevel=0.03)
        k.cube("lectern_crest", (ox, 0.69, 0.85), (0.5, 0.02, 0.4), mat("flag_burgundy", "burgundy", 0.8))
        k.torus("crest_ring", (ox, 0.67, 0.85), 0.15, 0.02, mat("gold", "gold", 0.3, 1.0), rot=(math.pi / 2, 0, 0))
    with k.group("gavel", "furniture"):
        k.cylinder("gavel_handle", (ox + 0.35, 0.95, 1.27), 0.03, 0.7, mat("wood_desk", "#6B3F22", 0.45),
                   rot=(0, math.pi / 2.3, 0))
        k.cylinder("gavel_head", (ox + 0.62, 0.95, 1.37), 0.12, 0.34, mat("wood_dark", "#3E2414", 0.4))
    with k.group("clerk_desk", "furniture"):
        k.cube("clerk_desk", (ox - 1.6, 0.35, 0.42), (1.0, 0.6, 0.84), mat("wood_desk", "#6B3F22", 0.45), bevel=0.02)
        k.cube("stamps", (ox - 1.85, 0.25, 0.9), (0.35, 0.15, 0.08), mat("ink", "ink", 0.3))
        k.text("clerk_label", "CLERK", (ox - 1.6, 0.04, 0.5), size=0.09, colour="gold")
    green = mat("bench_green", "racing_green", 0.45)
    for row in range(2):
        with k.group(f"bench_{row}", "furniture"):
            k.cube("bench", (ox + 2.6, 1.0 + row * 1.2, 0.45), (2.2, 0.6, 0.45), green, bevel=0.05)
            k.cube("bench_back", (ox + 2.6, 1.28 + row * 1.2, 0.85), (2.2, 0.12, 0.8), green, bevel=0.05)
    for i, x in enumerate((-1.6, 1.6)):
        with k.group(f"banner_{i}", "decoration"):
            k.cube("banner", (ox + x, back - 0.12, 2.6), (0.6, 0.04, 1.6), mat("flag_burgundy", "burgundy", 0.8))
            k.cube("banner_band", (ox + x, back - 0.15, 2.0), (0.6, 0.02, 0.12), mat("gold_cloth", "gold", 0.6))
    with k.group("lighting", "light"):
        k.light("chamber_key", (ox - 2.5, -3.5, 3.6), (ox, 0.6, 1.4), 900, 4.0, (1.0, 0.9, 0.78))
        k.light("chamber_fill", (ox + 3.5, -2.5, 2.5), (ox + 1, 0.5, 1.2), 330, 4.0, (0.85, 0.9, 1.0))
        k.light("chamber_rim", (ox, back - 1.0, 3.5), (ox, 0.8, 1.4), 300, 3.0, (1.0, 0.85, 0.6))


def main_street(k: Recorder):
    k.location = "main_street"
    ox = OFFSETS[k.location]
    with k.group("road", "street"):
        k.cube("road", (ox, 2.0, -0.05), (30, 14, 0.1), mat("cobbles", "slate", 0.85))
        k.cube("pavement", (ox, 3.2, 0.06), (30, 2.0, 0.12), mat("pavement", "stone", 0.8))
    rnd = random.Random(7)
    cols = ["brick", "cream", "racing_green", "burgundy", "#C9B79C", "brick"]
    doors = ["racing_green", "burgundy", "slate", "gold", "burgundy", "ink"]
    shops = ["BISCUIT ROW", "PUDDLE END POST OFFICE", "CRUMBS & CO.", "BOBBINGTON BAKERY", "TEAS", "IRONMONGER"]
    for i in range(6):
        x = ox - 7.5 + i * 3.0
        h = rnd.uniform(4.2, 5.4)
        with k.group(f"house_{i}", "building"):
            k.cube("house", (x, 5.6, h / 2), (2.9, 3.0, h), mat(f"house_{cols[i]}", cols[i], 0.85))
            k.cone("roof", (x, 5.6, h + 0.55), 2.2, 0.05, 1.1, mat("roof", "#4A4E57", 0.7), rot=(0, 0, math.pi / 4),
                   vertices=4)
            k.cube("door", (x - 0.6, 4.08, 0.6), (0.6, 0.06, 1.2), mat(f"door_{doors[i]}", doors[i], 0.4))
            k.cube("shopwin", (x + 0.5, 4.06, 0.9), (1.1, 0.06, 1.0), mat("sky_glass", "sky_day", 0.1, emission=0.6))
            k.cube("upwin", (x, 4.06, h * 0.7), (0.9, 0.06, 0.9), mat("sky_glass", "sky_day", 0.1, emission=0.6))
            k.cube("fascia", (x, 4.0, 1.7), (2.7, 0.08, 0.32), mat("fascia", "racing_green" if i % 2 else "burgundy", 0.5))
            k.text("shop_sign", shops[i], (x, 3.95, 1.7), size=0.13, colour="gold")
    with k.group("bunting", "decoration"):
        for j in range(28):
            x = ox - 7.5 + j * 0.55
            z = 3.4 - 0.25 * math.sin(math.pi * (j % 7) / 6)
            k.cone("flaglet", (x, 3.6, z), 0.12, 0.0, 0.25,
                   mat(f"bunt{j % 3}", ["burgundy", "cream", "racing_green"][j % 3], 0.7), rot=(math.pi, 0, 0), vertices=3)
    with k.group("historic_puddle", "landmark"):
        k.cylinder("puddle", (ox + 0.6, -0.4, 0.01), 0.9, 0.01, mat("puddle", "#6E8FA8", 0.05), scale=(1.4, 0.8, 1))
        k.cylinder("puddle_sign_post", (ox + 2.3, 0.4, 0.6), 0.03, 1.2, mat("ink", "ink", 0.3))
        k.cube("puddle_sign", (ox + 2.3, 0.38, 1.25), (0.9, 0.04, 0.4), mat("cream_board", "cream", 0.6))
        k.text("puddle_label", "HISTORIC PUDDLE\nEST. 1953", (ox + 2.3, 0.35, 1.25), size=0.07, colour="burgundy_dark")
    for j, x in enumerate((-3.4, -2.8, -2.2)):
        with k.group(f"bin_{j}", "street_furniture"):
            k.cylinder("bin", (ox + x, 3.0, 0.5), 0.26, 0.8, mat("bin", "#2E4F3E", 0.5))
            k.sphere("rubbish", (ox + x, 3.0, 0.98), (0.3, 0.3, 0.2),
                     mat(f"rubbish{j}", ["#8A7F6A", "#B9AE9A", "#6B5E4A"][j], 0.9))
    for j, x in enumerate((-6.0, 5.0)):
        with k.group(f"lamp_{j}", "street_furniture"):
            k.cylinder("lamp", (ox + x, 2.6, 1.6), 0.05, 3.2, mat("ink", "ink", 0.3))
            k.sphere("lamp_glass", (ox + x, 2.6, 3.25), (0.18, 0.18, 0.18), mat("lamp_glow", "gold_light", 0.2, emission=3.0))
    with k.group("lighting", "light"):
        k.light("street_fill", (ox, -4.0, 3.0), (ox, 1.0, 1.2), 500, 6.0, (1.0, 0.96, 0.9))


def pub(k: Recorder):
    k.location = "pub"
    ox = OFFSETS[k.location]
    back = room(k, ox, "#7A5A3A", "#3E2414", "#3B2416", width=8, height=3.6)
    wood = mat("bar_wood", "#5A3418", 0.4)
    with k.group("bar", "furniture"):
        k.cube("bar", (ox, 0.2, 0.55), (4.5, 0.8, 1.1), wood, bevel=0.03)
        k.cube("bar_top", (ox, 0.2, 1.12), (4.7, 0.95, 0.06), mat("bar_top", "#3E2414", 0.25))
        for j in range(3):
            k.cylinder("tap", (ox + 1.3 + j * 0.3, 0.05, 1.35), 0.03, 0.4, mat("brass", "gold", 0.25, 1.0))
    with k.group("back_shelf", "furniture"):
        k.cube("back_shelf", (ox, back - 0.25, 1.9), (4.5, 0.35, 0.06), wood)
        for j in range(16):
            k.cylinder("bottle", (ox - 2.0 + j * 0.27, back - 0.25, 2.1), 0.05, 0.36,
                       mat(f"bottle{j % 4}", ["#2F5A2F", "#6B3A1A", "#8C8C3A", "#3A2A5A"][j % 4], 0.1))
    with k.group("chalkboard", "sign"):
        k.cube("chalkboard", (ox + 2.2, back - 0.12, 2.3), (1.4, 0.05, 1.0), mat("chalk", "#1E2A24", 0.9))
        k.cube("chalk_frame", (ox + 2.2, back - 0.09, 2.3), (1.55, 0.04, 1.15), wood)
        k.text("chalk_text", "TODAY'S SPECIAL:\nDISAPPOINTMENT", (ox + 2.2, back - 0.16, 2.3), size=0.11, colour="cream",
               font="C:/Windows/Fonts/segoeprb.ttf")
    with k.group("pub_sign", "sign"):
        k.cube("pub_sign", (ox - 2.3, back - 0.12, 2.6), (1.6, 0.05, 0.5), mat("fascia", "racing_green", 0.5))
        k.text("pub_name", "THE LEANING PICKLE", (ox - 2.3, back - 0.16, 2.6), size=0.11, colour="gold")
    for j, x in enumerate((-1.5, 0.0, 1.5)):
        with k.group(f"stool_{j}", "furniture"):
            k.cylinder("stool", (ox + x, -0.55, 0.35), 0.18, 0.7, mat("stool", "burgundy", 0.5))
    with k.group("lighting", "light"):
        k.light("pub_warm", (ox - 1.5, -2.5, 3.0), (ox, 0.6, 1.3), 520, 3.0, (1.0, 0.75, 0.45))
        k.light("pub_fill", (ox + 2.5, -2.0, 2.0), (ox, 0.6, 1.2), 160, 3.0, (0.9, 0.85, 1.0))


def title_card(k: Recorder):
    """Series identity card (episode title texts are overlays added per episode, not town state)."""
    k.location = "title_card"
    ox = OFFSETS[k.location]
    with k.group("backdrop", "identity"):
        k.cube("title_bg", (ox, 3.0, 2.0), (12, 0.2, 10), mat("title_bg", "burgundy", 0.8))
    with k.group("coat_of_arms", "identity"):
        k.cube("shield", (ox, 2.85, 2.95), (0.9, 0.06, 1.0), mat("gold", "gold", 0.3, 1.0), bevel=0.08)
        k.cube("shield_in", (ox, 2.8, 2.95), (0.78, 0.04, 0.88), mat("flag_burgundy", "burgundy_dark", 0.6), bevel=0.06)
        for x, z in ((-0.2, 3.15), (0.2, 3.15), (0.0, 2.75)):
            k.cylinder("cup", (ox + x, 2.76, z), 0.08, 0.1, mat("cream_cup", "cream", 0.3), rot=(math.pi / 2, 0, 0))
        k.cone("crest_cone", (ox, 2.85, 3.68), 0.15, 0.02, 0.32, mat("cone", "#E8742C", 0.5))
        k.text("tagline", "A TOWN FULL OF BAD DECISIONS", (ox, 2.7, 1.1), size=0.08, colour="gold_light")
    with k.group("lighting", "light"):
        k.light("title_key", (ox, -2.0, 3.0), (ox, 2.7, 2.2), 600, 5.0, (1.0, 0.92, 0.8))


MARKS = {
    "mayors_office": {"desk": [0.0, 1.05, 0, 0.0], "door": [-2.2, -0.2, 20, 0.0], "front": [0.0, -0.6, 0, 0.0]},
    "council_chamber": {"dais": [40.0, 1.55, 0, 0.3], "clerk_desk": [38.55, 0.95, 18, 0.0],
                        "bench_left": [41.35, 0.55, -22, 0.0], "centre": [40.0, -0.5, 0, 0.0]},
    "main_street": {"pavement_left": [78.9, 0.6, 15, 0.0], "pavement_right": [80.7, 0.4, -15, 0.0],
                    "centre": [80.0, 0.5, 0, 0.0]},
    "pub": {"behind_bar": [120.0, 0.95, 0, 0.0], "bar_front": [120.8, -0.6, 160, 0.0]},
    "title_card": {"centre": [160.0, 0.0, 0, 0.0]},
}
# fixed reference cameras – identical in every version, so renders are directly comparable
REF_CAMERAS = {
    "mayors_office": {"loc": [0.0, -5.5, 2.2], "target": [0.0, 1.0, 1.5], "lens": 24},
    "council_chamber": {"loc": [40.0, -6.0, 2.4], "target": [40.0, 1.0, 1.6], "lens": 24},
    "main_street": {"loc": [80.0, -7.5, 2.6], "target": [80.0, 3.0, 1.8], "lens": 24},
    "pub": {"loc": [120.0, -5.0, 2.0], "target": [120.0, 1.5, 1.6], "lens": 24},
    "title_card": {"loc": [160.0, -3.0, 2.1], "target": [160.0, 2.7, 2.15], "lens": 35},
}
ENVIRONMENT = {"season": "autumn", "weather": "overcast, dry", "time_of_day": "late morning",
               "sun": {"energy": 2.2, "rotation_deg": [50, 0, 30], "colour": [1.0, 0.95, 0.85]},
               "world": {"colour": [0.55, 0.62, 0.7], "strength": 0.6}}


def seed_state() -> dict:
    k = Recorder()
    for build in (mayors_office, council_chamber, main_street, pub, title_card):
        build(k)
    return {"objects": k.objects, "marks": MARKS, "ref_cameras": REF_CAMERAS, "environment": ENVIRONMENT}
