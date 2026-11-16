"""Generates the design bible (Markdown) and the brand assets (SVG) from bobbington/bible.py.

    python -m bobbington.docs
"""
from __future__ import annotations

from pathlib import Path

from bobbington.bible import AUDIO_IDENTITY, CAST, PALETTE, RUNNING_GAGS, SERIES, TOWN, TYPOGRAPHY

ROOT = Path(__file__).resolve().parent.parent
P = PALETTE


# --- brand assets ---------------------------------------------------------------------------------
def coat_of_arms_svg() -> str:
    cups = "".join(f'<g transform="translate({x},{y})"><path d="M-22,-12 h44 v14 a22,18 0 0 1 -44,0 z" fill="{P["cream"]}"/>'
                   f'<path d="M22,-8 a10,10 0 0 1 0,16" fill="none" stroke="{P["cream"]}" stroke-width="5"/></g>'
                   for x, y in ((150, 165), (250, 165), (200, 300)))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 480" width="400" height="480">
  <title>Coat of arms of Bobbington</title>
  <!-- crest: a traffic cone -->
  <path d="M200,18 L228,92 H172 Z" fill="#E8742C" stroke="{P["ink"]}" stroke-width="3"/>
  <rect x="180" y="46" width="40" height="10" fill="{P["cream"]}"/><rect x="164" y="90" width="72" height="10" fill="{P["ink"]}"/>
  <!-- supporters: two confused geese -->
  <g fill="{P["cream"]}" stroke="{P["ink"]}" stroke-width="3">
    <ellipse cx="55" cy="300" rx="38" ry="55"/><path d="M55,250 q-5,-60 30,-70 q12,4 4,14 q-20,4 -18,56 z"/>
    <ellipse cx="345" cy="300" rx="38" ry="55"/><path d="M345,250 q5,-60 -30,-70 q-12,4 -4,14 q20,4 18,56 z"/>
  </g>
  <text x="80" y="176" font-family="Georgia" font-size="22" fill="{P["ink"]}">?</text>
  <text x="308" y="176" font-family="Georgia" font-size="22" fill="{P["ink"]}">?</text>
  <!-- shield: burgundy field, gold chevron, three cream teacups -->
  <path d="M100,110 H300 V270 Q300,370 200,410 Q100,370 100,270 Z" fill="{P["burgundy"]}" stroke="{P["gold"]}" stroke-width="10"/>
  <path d="M110,280 L200,200 L290,280 L290,315 L200,235 L110,315 Z" fill="{P["gold"]}"/>
  {cups}
  <!-- motto scroll -->
  <path d="M60,420 H340 L325,445 L340,470 H60 L75,445 Z" fill="{P["cream"]}" stroke="{P["gold"]}" stroke-width="4"/>
  <text x="200" y="453" text-anchor="middle" font-family="Georgia" font-weight="bold" font-size="22" fill="{P["burgundy_dark"]}">{TOWN["motto"].upper()}</text>
</svg>
'''


def logo_svg() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 260" width="900" height="260">
  <title>Bobbington logo</title>
  <rect width="900" height="260" rx="28" fill="{P["burgundy"]}"/>
  <rect x="12" y="12" width="876" height="236" rx="20" fill="none" stroke="{P["gold"]}" stroke-width="4"/>
  <g transform="translate(70,40)">
    <path d="M0,10 H120 V100 Q120,160 60,180 Q0,160 0,100 Z" fill="{P["racing_green"]}" stroke="{P["gold"]}" stroke-width="6"/>
    <path d="M10,110 L60,65 L110,110 L110,128 L60,85 L10,128 Z" fill="{P["gold"]}"/>
    <path d="M42,30 h36 v10 a18,14 0 0 1 -36,0 z" fill="{P["cream"]}"/>
  </g>
  <text x="235" y="140" font-family="Georgia" font-weight="bold" font-size="96" fill="{P["gold"]}" letter-spacing="4">BOBBINGTON</text>
  <text x="240" y="195" font-family="Georgia" font-style="italic" font-size="34" fill="{P["cream"]}">{SERIES["tagline"]}</text>
</svg>
'''


def flag_svg() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 360" width="600" height="360">
  <title>Flag of Bobbington</title>
  <rect width="600" height="360" fill="{P["burgundy"]}"/>
  <rect y="140" width="600" height="80" fill="{P["racing_green"]}"/>
  <rect y="132" width="600" height="8" fill="{P["gold"]}"/><rect y="220" width="600" height="8" fill="{P["gold"]}"/>
  <circle cx="300" cy="180" r="72" fill="{P["cream"]}" stroke="{P["gold"]}" stroke-width="8"/>
  <path d="M262,160 h76 v20 a38,30 0 0 1 -76,0 z" fill="{P["burgundy"]}"/>
  <path d="M338,166 a14,14 0 0 1 0,24" fill="none" stroke="{P["burgundy"]}" stroke-width="7"/>
</svg>
'''


# --- design bible -------------------------------------------------------------------------------
def bible_markdown() -> str:
    out = [f"# {SERIES['title']} – Series Bible", "", f"> *{SERIES['tagline']}*", "",
           "Generated from `bobbington/bible.py` (single source of truth). Do not edit by hand – run "
           "`python -m bobbington.docs`.", "", "## Series", "",
           f"- **Language:** {SERIES['language']}", f"- **Humour:** {SERIES['humour']}",
           f"- **Audience:** {SERIES['audience']}",
           f"- **Platforms:** {SERIES['platforms']['primary']} (primary), {', '.join(SERIES['platforms']['secondary'])}",
           "", "### Episode rules", ""] + [f"- {r}" for r in SERIES["episode_rules"]]
    out += ["", "## Visual identity", "", "![Logo](../../assets/brand/logo.svg)", "", "| Colour | Hex |", "|---|---|"]
    out += [f"| {k} | `{v}` |" for k, v in PALETTE.items()]
    out += ["", f"- Display type: {TYPOGRAPHY['display']}", f"- Subtitles: {TYPOGRAPHY['subtitles']}", "",
            "| Coat of arms | Flag |", "|---|---|",
            "| ![Coat of arms](../../assets/brand/coat_of_arms.svg) | ![Flag](../../assets/brand/flag.svg) |", "",
            f"**Heraldry:** {TOWN['identity']['heraldry']}", "",
            "Rendering: stylised 3D in Blender (EEVEE), rigged characters built from the specs below, "
            "24 fps, 9:16. Every shot contains character animation (rig) – camera moves alone are never used "
            "as 'animation'.", "", "## The town", "",
            f"**{TOWN['name']}** – {TOWN['type']}. Motto: *{TOWN['motto']}* ({TOWN['motto_translation']}). "
            f"Founded {TOWN['founded']}. Simulation start: {TOWN['starting_population']:,} residents, "
            f"£{TOWN['starting_budget_gbp']:,} (fictional values).", "", "### History", ""]
    out += [f"- {h}" for h in TOWN["history"]] + ["", "### Traditions", ""]
    out += [f"- **{t['name']}** ({t['when']}): {t['what']}" for t in TOWN["traditions"]] + ["", "### Locations", ""]
    out += [f"- **{k.replace('_', ' ').title()}:** {v if isinstance(v, str) else ', '.join(v)}"
            for k, v in TOWN["locations"].items()]
    out += ["", "## Cast", "", "![Cast line-up](cast_lineup.jpg)", ""]
    for cid, c in CAST.items():
        look = c["look"]
        v = c["voice"]
        out += [f"### {c['name']} – {c['role']}", "", c["bio"], "",
                f"- **Age:** {c['age']}", f"- **Personality:** {', '.join(c['personality'])}",
                f"- **Speech:** {c['speech']}", f"- **Catchphrases:** " + " · ".join(f"“{x}”" for x in c["catchphrases"]),
                f"- **Silhouette:** {look['silhouette']}",
                f"- **Proportions:** height {look['height']} m, head {look['head']}, build `{look['build']}`",
                f"- **Voice:** Piper `{v['model']}`" + (f" speaker `{v['speaker']}`" if v["speaker"] else "") +
                f", length scale {v['length_scale']}", "- **Relationships:**"]
        out += [f"  - {CAST[k]['name']}: {rel}" for k, rel in c["relationships"].items()]
        out += [""]
    out += ["## Running gags", ""] + [f"- {g}" for g in RUNNING_GAGS]
    out += ["", "## Audio identity", ""] + [f"- **{k}:** {v}" for k, v in AUDIO_IDENTITY.items() if isinstance(v, str)]
    out += [f"- **ambience:** " + "; ".join(f"{k}: {v}" for k, v in AUDIO_IDENTITY["ambience"].items()), ""]
    return "\n".join(out)


def generate(root: Path = ROOT) -> list[Path]:
    brand = root / "assets" / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    files = []
    for name, content in (("logo.svg", logo_svg()), ("coat_of_arms.svg", coat_of_arms_svg()), ("flag.svg", flag_svg())):
        (brand / name).write_text(content, encoding="utf-8")
        files.append(brand / name)
    doc = root / "docs" / "bible" / "README.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(bible_markdown(), encoding="utf-8")
    files.append(doc)
    return files


if __name__ == "__main__":
    for f in generate():
        print(f)
