"""Bobbington sets (reusable environments). Each set is built at its own X offset in one scene, so a whole
episode renders in a single pass (one shader compilation). Every set exposes named marks for the cast.

Palette: burgundy, racing green, cream, warm gold + brick/stone/slate (bobbington/bible.py).
"""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from characters import colour, cone, cube, cylinder, material, sphere, torus
from scene_kit import area_light, label

OFFSETS = {"mayors_office": 0.0, "council_chamber": 40.0, "main_street": 80.0, "pub": 120.0, "title_card": 160.0}


def _m(name, col, rough=0.6, metallic=0.0, palette=None, emission=0.0):
    return material(f"set_{name}", colour(col, palette), rough, metallic=metallic, emission=emission)


class SetBuilder:
    def __init__(self, palette: dict):
        self.p = palette
        self.marks: dict[str, dict[str, tuple[float, float, float]]] = {}   # set -> mark -> (x, y, facing_deg)
        self.props: dict[str, bpy.types.Object] = {}

    def m(self, name, col, rough=0.6, metallic=0.0, emission=0.0):
        return _m(name, col, rough, metallic, self.p, emission)

    # ------------------------------------------------------------------------------------------
    def room(self, ox: float, wall: str, lower: str, floor: str, width=9.0, depth=6.0, height=7.0):
        cube("floor", (ox, depth / 2 - 2.5, -0.05), (width, depth + 4, 0.1), self.m(f"floor_{floor}", floor, 0.7))
        cube("wall_back", (ox, depth - 2.5, height / 2), (width, 0.2, height), self.m(f"wall_{wall}", wall, 0.85))
        cube("wainscot", (ox, depth - 2.62, 0.55), (width, 0.1, 1.1), self.m(f"wains_{lower}", lower, 0.5))
        cube("rail", (ox, depth - 2.68, 1.12), (width, 0.06, 0.06), self.m("gold", "gold", 0.3, 1.0))
        for s in (-1, 1):
            cube("wall_side", (ox + s * width / 2, depth / 2 - 2.5, height / 2), (0.2, depth + 4, height),
                 self.m(f"wall_{wall}", wall, 0.85))
        return depth - 2.5

    def window(self, x, y, z, w=1.2, h=1.6):
        cube("win_frame", (x, y - 0.05, z), (w + 0.16, 0.1, h + 0.16), self.m("cream_frame", "cream", 0.4))
        cube("win_glass", (x, y - 0.11, z), (w, 0.02, h), self.m("sky_glass", "sky_day", 0.1, emission=1.2))
        cube("win_bar_v", (x, y - 0.13, z), (0.05, 0.02, h), self.m("cream_frame", "cream", 0.4))
        cube("win_bar_h", (x, y - 0.13, z), (w, 0.02, 0.05), self.m("cream_frame", "cream", 0.4))

    def frame_text(self, text, x, y, z, w, h, size, bg="burgundy_dark", fg="gold"):
        cube("frame", (x, y - 0.04, z), (w + 0.12, 0.06, h + 0.12), self.m("gold", "gold", 0.3, 1.0))
        cube("frame_bg", (x, y - 0.08, z), (w, 0.04, h), self.m(f"bg_{bg}", bg, 0.7))
        return label(text, (x, y - 0.11, z), size=size, colour_name=fg)

    # --- sets --------------------------------------------------------------------------------------
    def mayors_office(self):
        ox = OFFSETS["mayors_office"]
        back = self.room(ox, "cream", "burgundy_dark", "#5A3A26")
        self.window(ox + 2.6, back, 2.2)
        # portrait of Winston painted by Winston
        cube("portrait_frame", (ox - 1.6, back - 0.05, 2.5), (1.1, 0.08, 1.4), self.m("gold", "gold", 0.3, 1.0))
        cube("portrait", (ox - 1.6, back - 0.1, 2.5), (0.9, 0.04, 1.2), self.m("portrait_bg", "racing_green", 0.8))
        sphere("portrait_head", (ox - 1.6, back - 0.15, 2.65), (0.22, 0.04, 0.24), self.m("portrait_skin", "#E9B99A", 0.7))
        cube("portrait_tash", (ox - 1.6, back - 0.18, 2.55), (0.4, 0.03, 0.06), self.m("portrait_tash", "#E4DED3", 0.8))
        label("A SELF-PORTRAIT", (ox - 1.6, back - 0.12, 1.88), size=0.07, colour_name="gold")
        # desk + chair
        wood = self.m("wood_desk", "#6B3F22", 0.45)
        cube("desk", (ox, 0.55, 0.42), (2.4, 0.95, 0.84), wood, bevel=0.03)
        cube("desk_top", (ox, 0.55, 0.86), (2.5, 1.05, 0.05), self.m("desk_leather", "racing_green", 0.5))
        cube("desk_trim", (ox, 0.05, 0.6), (2.4, 0.02, 0.06), self.m("gold", "gold", 0.3, 1.0))
        cube("chair_back", (ox, 1.55, 1.25), (0.9, 0.15, 1.4), self.m("chair_red", "burgundy", 0.5), bevel=0.05)
        cylinder("inkwell", (ox - 0.8, 0.5, 0.95), 0.07, 0.12, self.m("ink", "ink", 0.2))
        cube("papers", (ox + 0.7, 0.45, 0.9), (0.4, 0.3, 0.03), self.m("paper", "cream", 0.9))
        label("MAYOR", (ox, 0.04, 0.6), size=0.12, colour_name="gold")
        # flag
        cylinder("flagpole", (ox + 3.6, back - 0.4, 1.5), 0.03, 3.0, self.m("gold", "gold", 0.3, 1.0))
        cube("flag_b", (ox + 3.2, back - 0.4, 2.55), (0.8, 0.02, 0.55), self.m("flag_burgundy", "burgundy", 0.8))
        cube("flag_g", (ox + 3.2, back - 0.42, 2.55), (0.8, 0.02, 0.12), self.m("gold_cloth", "gold", 0.6))
        # bookshelf
        cube("shelf", (ox - 3.6, back - 0.3, 1.4), (1.2, 0.4, 2.8), wood)
        rnd = random.Random(1)
        for r in range(4):
            x = ox - 4.1
            while x < ox - 3.1:
                w = rnd.uniform(0.06, 0.12)
                cube("book", (x + w / 2, back - 0.5, 0.4 + r * 0.65 + 0.2), (w, 0.25, rnd.uniform(0.3, 0.45)),
                     self.m(f"book{rnd.randint(0, 3)}", rnd.choice(["burgundy", "racing_green", "gold", "slate"]), 0.7))
                x += w + 0.01
        # plaque (appears in the punchline)
        plaque = cube("plaque", (ox + 0.75, 0.15, 1.05), (0.7, 0.05, 0.32), self.m("brass", "gold", 0.25, 1.0))
        txt = label("MONDAYS WERE BRIEFLY\nABOLISHED HERE", (ox + 0.75, 0.12, 1.05), size=0.045, colour_name="burgundy_dark")
        self.props["plaque"] = plaque
        self.props["plaque_text"] = txt
        cube("rug", (ox, -0.6, 0.005), (4.0, 2.4, 0.01), self.m("rug", "burgundy", 0.9))
        area_light("office_key", (ox - 2.0, -3.0, 3.2), (ox, 0.5, 1.4), 650, 3.0, (1.0, 0.9, 0.78))
        area_light("office_fill", (ox + 2.5, -2.0, 2.0), (ox, 0.5, 1.4), 220, 4.0, (0.85, 0.9, 1.0))
        area_light("office_window", (ox + 2.6, back - 0.6, 2.4), (ox, 0.6, 1.2), 160, 1.5, (0.9, 0.95, 1.0))
        self.marks["mayors_office"] = {"desk": (ox, 1.05, 0), "door": (ox - 2.2, -0.2, 20), "front": (ox, -0.6, 0)}

    def council_chamber(self):
        ox = OFFSETS["council_chamber"]
        back = self.room(ox, "cream", "racing_green", "#4A3324", width=11)
        self.frame_text("EX ERRORE GLORIA", ox, back, 3.1, 3.4, 0.6, 0.28)
        for x in (-4.6, 4.6):
            cylinder("column", (ox + x, back - 0.3, 2.1), 0.22, 4.2, self.m("stone", "stone", 0.6))
        # dais & mayor's lectern
        cube("dais", (ox, 1.5, 0.15), (3.2, 1.6, 0.3), self.m("wood_dais", "#5C3720", 0.5))
        cube("lectern", (ox, 0.95, 0.75), (1.1, 0.5, 0.9), self.m("wood_desk", "#6B3F22", 0.45), bevel=0.03)
        cube("lectern_crest", (ox, 0.69, 0.85), (0.5, 0.02, 0.4), self.m("flag_burgundy", "burgundy", 0.8))
        torus("crest_ring", (ox, 0.67, 0.85), 0.15, 0.02, self.m("gold", "gold", 0.3, 1.0), rot=(math.pi / 2, 0, 0))
        # the slightly-too-large gavel
        cylinder("gavel_handle", (ox + 0.35, 0.95, 1.27), 0.03, 0.7, self.m("wood_desk", "#6B3F22", 0.45), rot=(0, math.pi / 2.3, 0))
        cylinder("gavel_head", (ox + 0.62, 0.95, 1.37), 0.12, 0.34, self.m("wood_dark", "#3E2414", 0.4))
        # clerk desk (Margaret) and green benches
        cube("clerk_desk", (ox - 1.6, 0.35, 0.42), (1.0, 0.6, 0.84), self.m("wood_desk", "#6B3F22", 0.45), bevel=0.02)
        cube("stamps", (ox - 1.85, 0.25, 0.9), (0.35, 0.15, 0.08), self.m("ink", "ink", 0.3))
        label("CLERK", (ox - 1.6, 0.04, 0.5), size=0.09, colour_name="gold")
        green = self.m("bench_green", "racing_green", 0.45)
        for row in range(2):
            cube("bench", (ox + 2.6, 1.0 + row * 1.2, 0.45), (2.2, 0.6, 0.45), green, bevel=0.05)
            cube("bench_back", (ox + 2.6, 1.28 + row * 1.2, 0.85), (2.2, 0.12, 0.8), green, bevel=0.05)
        for x in (-1.6, 1.6):
            cube("banner", (ox + x, back - 0.12, 2.6), (0.6, 0.04, 1.6), self.m("flag_burgundy", "burgundy", 0.8))
            cube("banner_band", (ox + x, back - 0.15, 2.0), (0.6, 0.02, 0.12), self.m("gold_cloth", "gold", 0.6))
        area_light("chamber_key", (ox - 2.5, -3.5, 3.6), (ox, 0.6, 1.4), 900, 4.0, (1.0, 0.9, 0.78))
        area_light("chamber_fill", (ox + 3.5, -2.5, 2.5), (ox + 1, 0.5, 1.2), 330, 4.0, (0.85, 0.9, 1.0))
        area_light("chamber_rim", (ox, back - 1.0, 3.5), (ox, 0.8, 1.4), 300, 3.0, (1.0, 0.85, 0.6))
        self.marks["council_chamber"] = {"dais": (ox, 1.55, 0, 0.3), "clerk_desk": (ox - 1.45, 0.95, 18),
                                         "bench_left": (ox + 1.35, 0.55, -22), "centre": (ox, -0.5, 0)}

    def main_street(self):
        ox = OFFSETS["main_street"]
        cube("road", (ox, 2.0, -0.05), (30, 14, 0.1), self.m("cobbles", "slate", 0.85))
        cube("pavement", (ox, 3.2, 0.06), (30, 2.0, 0.12), self.m("pavement", "stone", 0.8))
        rnd = random.Random(7)
        cols = ["brick", "cream", "racing_green", "burgundy", "#C9B79C", "brick"]
        doors = ["racing_green", "burgundy", "slate", "gold", "burgundy", "ink"]
        shops = ["BISCUIT ROW", "PUDDLE END POST OFFICE", "CRUMBS & CO.", "BOBBINGTON BAKERY", "TEAS", "IRONMONGER"]
        for i in range(6):
            x = ox - 7.5 + i * 3.0
            h = rnd.uniform(4.2, 5.4)
            cube("house", (x, 5.6, h / 2), (2.9, 3.0, h), self.m(f"house_{cols[i]}", cols[i], 0.85))
            cone("roof", (x, 5.6, h + 0.55), 2.2, 0.05, 1.1, self.m("roof", "#4A4E57", 0.7), rot=(0, 0, math.pi / 4), vertices=4)
            cube("door", (x - 0.6, 4.08, 0.6), (0.6, 0.06, 1.2), self.m(f"door_{doors[i]}", doors[i], 0.4))
            cube("shopwin", (x + 0.5, 4.06, 0.9), (1.1, 0.06, 1.0), self.m("sky_glass", "sky_day", 0.1, emission=0.6))
            cube("upwin", (x, 4.06, h * 0.7), (0.9, 0.06, 0.9), self.m("sky_glass", "sky_day", 0.1, emission=0.6))
            cube("fascia", (x, 4.0, 1.7), (2.7, 0.08, 0.32), self.m("fascia", "racing_green" if i % 2 else "burgundy", 0.5))
            label(shops[i], (x, 3.95, 1.7), size=0.13, colour_name="gold")
        # bunting
        for k in range(28):
            x = ox - 7.5 + k * 0.55
            z = 3.4 - 0.25 * math.sin(math.pi * (k % 7) / 6)
            cone("flaglet", (x, 3.6, z), 0.12, 0.0, 0.25, self.m(f"bunt{k % 3}", ["burgundy", "cream", "racing_green"][k % 3], 0.7),
                 rot=(math.pi, 0, 0), vertices=3)
        # the Historic Puddle and the overflowing bins (episode gag)
        cylinder("puddle", (ox + 0.6, -0.4, 0.01), 0.9, 0.01, self.m("puddle", "#6E8FA8", 0.05), scale=(1.4, 0.8, 1))
        cylinder("puddle_sign_post", (ox + 2.3, 0.4, 0.6), 0.03, 1.2, self.m("ink", "ink", 0.3))
        cube("puddle_sign", (ox + 2.3, 0.38, 1.25), (0.9, 0.04, 0.4), self.m("cream_board", "cream", 0.6))
        label("HISTORIC PUDDLE\nEST. 1953", (ox + 2.3, 0.35, 1.25), size=0.07, colour_name="burgundy_dark")
        for j, x in enumerate((-3.4, -2.8, -2.2)):
            cylinder("bin", (ox + x, 3.0, 0.5), 0.26, 0.8, self.m("bin", "#2E4F3E", 0.5))
            sphere("rubbish", (ox + x, 3.0, 0.98), (0.3, 0.3, 0.2), self.m(f"rubbish{j}", ["#8A7F6A", "#B9AE9A", "#6B5E4A"][j], 0.9))
        for x in (-6.0, 5.0):
            cylinder("lamp", (ox + x, 2.6, 1.6), 0.05, 3.2, self.m("ink", "ink", 0.3))
            sphere("lamp_glass", (ox + x, 2.6, 3.25), (0.18,) * 3, self.m("lamp_glow", "gold_light", 0.2, emission=3.0))
        area_light("street_fill", (ox, -4.0, 3.0), (ox, 1.0, 1.2), 500, 6.0, (1.0, 0.96, 0.9))
        self.marks["main_street"] = {"pavement_left": (ox - 1.1, 0.6, 15), "pavement_right": (ox + 0.7, 0.4, -15),
                                     "centre": (ox, 0.5, 0)}

    def pub(self, chalkboard: str = ""):
        ox = OFFSETS["pub"]
        back = self.room(ox, "#7A5A3A", "#3E2414", "#3B2416", width=8, height=3.6)
        wood = self.m("bar_wood", "#5A3418", 0.4)
        cube("bar", (ox, 0.2, 0.55), (4.5, 0.8, 1.1), wood, bevel=0.03)
        cube("bar_top", (ox, 0.2, 1.12), (4.7, 0.95, 0.06), self.m("bar_top", "#3E2414", 0.25))
        for k in range(3):
            cylinder("tap", (ox + 1.3 + k * 0.3, 0.05, 1.35), 0.03, 0.4, self.m("brass", "gold", 0.25, 1.0))
        cube("back_shelf", (ox, back - 0.25, 1.9), (4.5, 0.35, 0.06), wood)
        rnd = random.Random(3)
        for k in range(16):
            cylinder("bottle", (ox - 2.0 + k * 0.27, back - 0.25, 2.1), 0.05, 0.36,
                     self.m(f"bottle{k % 4}", ["#2F5A2F", "#6B3A1A", "#8C8C3A", "#3A2A5A"][k % 4], 0.1))
        cube("chalkboard", (ox + 2.2, back - 0.12, 2.3), (1.4, 0.05, 1.0), self.m("chalk", "#1E2A24", 0.9))
        cube("chalk_frame", (ox + 2.2, back - 0.09, 2.3), (1.55, 0.04, 1.15), wood)
        if chalkboard:
            label(chalkboard, (ox + 2.2, back - 0.16, 2.3), size=0.12, colour_name="cream",
                  font_path="C:/Windows/Fonts/segoeprb.ttf")
        cube("pub_sign", (ox - 2.3, back - 0.12, 2.6), (1.6, 0.05, 0.5), self.m("fascia", "racing_green", 0.5))
        label("THE LEANING PICKLE", (ox - 2.3, back - 0.16, 2.6), size=0.11, colour_name="gold")
        for x in (-1.5, 0.0, 1.5):
            cylinder("stool", (ox + x, -0.55, 0.35), 0.18, 0.7, self.m("stool", "burgundy", 0.5))
        area_light("pub_warm", (ox - 1.5, -2.5, 3.0), (ox, 0.6, 1.3), 520, 3.0, (1.0, 0.75, 0.45))
        area_light("pub_fill", (ox + 2.5, -2.0, 2.0), (ox, 0.6, 1.2), 160, 3.0, (0.9, 0.85, 1.0))
        self.marks["pub"] = {"behind_bar": (ox, 0.95, 0), "bar_front": (ox + 0.8, -0.6, 160)}

    def title_card(self, title: str, subtitle: str):
        ox = OFFSETS["title_card"]
        cube("title_bg", (ox, 3.0, 2.0), (12, 0.2, 10), self.m("title_bg", "burgundy", 0.8))
        # coat of arms: shield, chevron, three cream teacups
        cube("shield", (ox, 2.85, 2.95), (0.9, 0.06, 1.0), self.m("gold", "gold", 0.3, 1.0), bevel=0.08)
        cube("shield_in", (ox, 2.8, 2.95), (0.78, 0.04, 0.88), self.m("flag_burgundy", "burgundy_dark", 0.6), bevel=0.06)
        for x, z in ((-0.2, 3.15), (0.2, 3.15), (0.0, 2.75)):
            cylinder("cup", (ox + x, 2.76, z), 0.08, 0.1, self.m("cream_cup", "cream", 0.3), rot=(math.pi / 2, 0, 0))
        cone("crest_cone", (ox, 2.85, 3.68), 0.15, 0.02, 0.32, self.m("cone", "#E8742C", 0.5))
        t1 = label(title, (ox, 2.7, 2.0), size=0.42, colour_name="gold", extrude=0.03)
        t2 = label(subtitle, (ox, 2.7, 1.45), size=0.17, colour_name="cream")
        t3 = label("A TOWN FULL OF BAD DECISIONS", (ox, 2.7, 1.1), size=0.08, colour_name="gold_light")
        self.props.update({"title_main": t1, "title_sub": t2, "title_tag": t3})
        area_light("title_key", (ox, -2.0, 3.0), (ox, 2.7, 2.2), 600, 5.0, (1.0, 0.92, 0.8))
        self.marks["title_card"] = {"centre": (ox, 0.0, 0)}
