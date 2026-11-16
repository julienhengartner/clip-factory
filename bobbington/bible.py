"""BOBBINGTON – official series bible (single source of truth).

Everything that must stay consistent across episodes lives here: brand, palette, town lore, the cast's
appearance (used by the Blender character builder), personalities, voices (used by the TTS layer) and
relationships. Markdown docs in docs/bible/ are generated from this file (python -m bobbington.docs).
"""
from __future__ import annotations

SERIES = {
    "title": "Bobbington",
    "tagline": "A Town Full of Bad Decisions.",
    "language": "en-GB",
    "humour": "Dry British comedy: sarcasm, absurd bureaucracy, eccentric characters, unexpected punchlines.",
    "audience": "International English-speaking comedy audience",
    "platforms": {"primary": "TikTok", "secondary": ["Instagram Reels", "YouTube Shorts"]},
    "episode_rules": [
        "60–75 seconds (never under 60, standard maximum 80)",
        "Every episode: beginning, conflict, escalation, twist, punchline",
        "Cold open: the hook line is spoken within the first 3 seconds",
        "At least two cast members per episode; Winston appears in every episode",
        "End on a button joke, then the series sting",
    ],
}

# --- Visual identity -------------------------------------------------------------------------
# British-inspired palette: burgundy, dark green, cream, warm gold (+ supporting neutrals)
PALETTE = {
    "burgundy": "#7A1F2B",
    "burgundy_dark": "#4E1219",
    "racing_green": "#1F4D3A",
    "green_dark": "#12301F",
    "cream": "#F3E9D2",
    "parchment": "#E6D5B0",
    "gold": "#C9A227",
    "gold_light": "#E4C766",
    "brick": "#9C4A33",
    "stone": "#B9AE9A",
    "slate": "#3F4650",
    "ink": "#1B1B1F",
    "sky_day": "#AFC8D8",
    "sky_dusk": "#E7A869",
}


def rgb(name_or_hex: str) -> tuple[float, float, float]:
    """Palette name or #RRGGBB -> linear-ish 0..1 RGB for Blender (sRGB values; Blender converts)."""
    h = PALETTE.get(name_or_hex, name_or_hex).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


TYPOGRAPHY = {
    "display": "Georgia Bold (fallback: serif bold) – headlines, title cards",
    "subtitles": "Arial Black / Arial Bold – burned-in subtitles, cream text, ink outline",
    "subtitle_colours": {"text": "cream", "highlight": "gold", "outline": "ink"},
}

# --- The town ---------------------------------------------------------------------------------
TOWN = {
    "name": "Bobbington",
    "type": "Former market town in the fictional English county of Muddlesex",
    "motto": "Ex Errore Gloria",   # "Glory out of error"
    "motto_translation": "Glory out of error",
    "founded": 1347,
    "starting_population": 2450,     # fictional simulation value
    "starting_budget_gbp": 1_000_000,  # fictional simulation value
    "history": [
        "1347 – Founded when a cattle drover took a wrong turn and refused to admit it.",
        "1612 – The market charter is granted; the charter is immediately lost, then found in a pie.",
        "1789 – The Town Hall clock is installed facing a wall 'to protect it from the weather'.",
        "1868 – The railway arrives. The station is built 400 yards from the nearest track.",
        "1953 – Bobbington wins 'Most Improved Puddle' at the county fair. It has never been fixed.",
        "Today – Run by Mayor Winston Boggle, who considers every disaster a 'bold new chapter'.",
    ],
    "traditions": [
        {"name": "The Great Puddle Day", "when": "first Saturday of April",
         "what": "Residents gather to admire the historic puddle on Main Street. Nobody is allowed to fix it."},
        {"name": "The Backwards Parade", "when": "August bank holiday",
         "what": "Commemorates the founder's wrong turn. Everyone walks the route in reverse, including the band."},
        {"name": "Mayor's Tea of Apology", "when": "whenever necessary (monthly)",
         "what": "The Mayor serves tea to citizens affected by his latest decision. The tea is also a decision."},
        {"name": "Biscuit Census", "when": "every November",
         "what": "Brenda Biscuit counts the town's biscuits. The figures are disputed every year."},
    ],
    "locations": {
        "town_hall": "Grand Victorian Town Hall in red brick and cream stone; clock faces a wall.",
        "mayors_office": "Wood-panelled office, oversized desk, portrait of Winston painted by Winston.",
        "council_chamber": "Green leather benches, gold-framed motto, a gavel that is slightly too large.",
        "main_street": "Terraced shops with bay windows, bunting, the Historic Puddle.",
        "pub": "The Leaning Pickle – crooked Tudor pub run by Arthur Pickles.",
        "railway_station": "Bobbington Parkway – charming, 400 yards from any track.",
        "market_square": "Cobbles, a stone cross, Thursday market stalls.",
        "town_park": "Victoria Gardens – bandstand, duck pond, a bench nobody may sit on.",
        "police_station": "Blue lamp, one cell, one inspector, many questions.",
        "construction_sites": "Permanent cones; the town's most reliable growth industry.",
        "neighbourhoods": ["Old Town", "Puddle End", "Crumble Heights", "Biscuit Row"],
    },
    "identity": {
        "logo": "assets/brand/logo.svg",
        "coat_of_arms": "assets/brand/coat_of_arms.svg",
        "flag": "assets/brand/flag.svg",
        "heraldry": "Burgundy shield, gold chevron, three cream teacups; crest: a traffic cone; "
                    "supporters: two confused geese; motto scroll 'Ex Errore Gloria'.",
    },
}

# --- Cast -----------------------------------------------------------------------------------
# 'look' is consumed by blender/characters.py – change it here and every episode follows.
# Units: metres (Blender). Colours: palette names or hex.
CAST: dict[str, dict] = {
    "winston": {
        "name": "Mayor Winston Boggle",
        "role": "Mayor of Bobbington",
        "age": 61,
        "bio": ("Third-generation mayor (the first two were also Winston Boggle, which he claims is a coincidence). "
                "Studied 'Leadership and Elocution' by correspondence and still has the certificate framed twice. "
                "Believes that every catastrophe is a historic achievement waiting for a plaque."),
        "personality": ["extremely self-confident", "stubborn", "dramatic", "sarcastic", "frequently incompetent",
                        "convinced every mistake is a historic achievement"],
        "speech": "Grand, pompous British delivery; long pauses for applause that never comes; dry put-downs.",
        "catchphrases": ["Historic.", "Write that down, Margaret.", "This will be remembered. Possibly fondly.",
                         "I have consulted myself, and I agree."],
        "look": {
            "height": 1.62, "build": "round", "head": 0.36, "skin": "#E9B99A", "nose": "bulb",
            "hair": {"style": "bald_ring", "colour": "#D9D4CB"},
            "moustache": {"style": "bushy_handlebar", "colour": "#E4DED3"},
            "eyebrows": {"style": "bushy", "colour": "#E4DED3"},
            "glasses": {"style": "round", "frame": "gold"},
            "outfit": {"jacket": "#7B5532", "jacket_pattern": "tweed", "trousers": "#4A3A2C", "shirt": "cream",
                       "neck": {"type": "bow_tie", "colour": "burgundy"}, "shoes": "#2B1D14",
                       "accessory": "mayoral_chain"},
            "silhouette": "pear-shaped torso, short legs, oversized head, handlebar moustache wider than his face",
        },
        "voice": {"model": "en_GB-northern_english_male-medium", "speaker": None, "length_scale": 1.08,
                  "noise_scale": 0.667, "noise_w": 0.8, "volume": 1.0},
        "relationships": {"margaret": "relies on her completely; refuses to admit it",
                          "reginald": "sees him as a loyal admirer (he is not)",
                          "brenda": "fears her ability to spread news faster than his press office",
                          "arthur": "drinks there 'for official research'",
                          "nigel": "appointed him personally; regrets nothing, understands nothing"},
    },
    "margaret": {
        "name": "Margaret Puddington",
        "role": "Town Clerk",
        "age": 54,
        "bio": ("Has run Bobbington's paperwork for 31 years and its actual government for 30. Owns 14 stamps, "
                "each with a different shade of disapproval. The only person who has read the town charter."),
        "personality": ["strict", "precise", "deadpan", "secretly fond of Winston's chaos", "unflappable"],
        "speech": "Clipped Received Pronunciation; replies in procedural language; devastating one-word answers.",
        "catchphrases": ["Noted.", "That requires a form.", "Form 27B. In triplicate.", "Mayor. No."],
        "look": {
            "height": 1.70, "build": "tall_thin", "head": 0.30, "skin": "#F0CDB4", "nose": "pointed",
            "hair": {"style": "tight_bun", "colour": "#5B4636"},
            "glasses": {"style": "half_moon", "frame": "ink"},
            "eyebrows": {"style": "thin", "colour": "#4A382B"},
            "outfit": {"jacket": "racing_green", "skirt": "#2E2A2A", "shirt": "cream",
                       "neck": {"type": "brooch", "colour": "gold"}, "shoes": "#1B1B1F", "accessory": "clipboard"},
            "silhouette": "tall, narrow, perfectly upright; tight bun; clipboard always at chest height",
        },
        "voice": {"model": "en_GB-cori-medium", "speaker": None, "length_scale": 0.98,
                  "noise_scale": 0.5, "noise_w": 0.6, "volume": 1.0},
        "relationships": {"winston": "manages him like weather", "reginald": "sees through him",
                          "brenda": "the only source she cannot file", "arthur": "mutual respect via silence",
                          "nigel": "fills in his forms for him"},
    },
    "reginald": {
        "name": "Reginald Crumble",
        "role": "Council Leader",
        "age": 47,
        "bio": ("Ambitious Council Leader who has prepared his acceptance speech for Mayor every year since 2009. "
                "Agrees with Winston in public and plots in the stationery cupboard."),
        "personality": ["ambitious", "smarmy", "opportunistic", "cowardly when confronted", "loves a slogan"],
        "speech": "Smooth, oily, over-enunciated; turns every sentence into a campaign slogan.",
        "catchphrases": ["A bold vision, Mayor. Bold.", "Purely in the public interest.", "For the record — I was against it."],
        "look": {
            "height": 1.78, "build": "slim", "head": 0.31, "skin": "#E8BFA0", "nose": "long",
            "hair": {"style": "slick_side_part", "colour": "#2A2420"},
            "eyebrows": {"style": "arched", "colour": "#2A2420"},
            "outfit": {"jacket": "#2F3A4A", "jacket_pattern": "pinstripe", "trousers": "#2F3A4A", "shirt": "#FFFFFF",
                       "neck": {"type": "tie", "colour": "burgundy"}, "shoes": "#111111",
                       "accessory": "rosette"},
            "silhouette": "tall and narrow with a big chin and a too-perfect side parting",
        },
        "voice": {"model": "en_GB-vctk-medium", "speaker": "p226", "length_scale": 1.0,
                  "noise_scale": 0.6, "noise_w": 0.7, "volume": 1.0},
        "relationships": {"winston": "wants his job", "margaret": "afraid of her", "brenda": "uses her to leak",
                          "arthur": "banned from the pub twice", "nigel": "tries to recruit him"},
    },
    "brenda": {
        "name": "Brenda Biscuit",
        "role": "Local gossip",
        "age": 68,
        "bio": ("Self-appointed Head of Information. Knows everything that has happened in Bobbington and several "
                "things that have not. Runs the Biscuit Census and the unofficial town newsletter, 'Crumbs'."),
        "personality": ["nosy", "warm", "dramatic", "fast-talking", "always holding a biscuit tin"],
        "speech": "Breathless, conspiratorial; starts every sentence with 'Well, I heard…'.",
        "catchphrases": ["Well, I heard…", "I'm not one to gossip, but—", "You didn't hear it from me. You heard it from me."],
        "look": {
            "height": 1.55, "build": "round", "head": 0.33, "skin": "#F2C8B0", "nose": "button",
            "hair": {"style": "big_curls", "colour": "#C9C4D9"},
            "eyebrows": {"style": "arched", "colour": "#9A93A8"},
            "outfit": {"jacket": "#C7718A", "jacket_pattern": "floral", "skirt": "#5D4E6B", "shirt": "cream",
                       "neck": {"type": "pearls", "colour": "cream"}, "shoes": "#5D3A2B", "accessory": "biscuit_tin"},
            "silhouette": "small and round with enormous lilac curls and a biscuit tin",
        },
        "voice": {"model": "en_GB-alba-medium", "speaker": None, "length_scale": 0.92,
                  "noise_scale": 0.7, "noise_w": 0.8, "volume": 1.0},
        "relationships": {"winston": "her favourite source of material", "margaret": "her nemesis and best friend",
                          "reginald": "knows his secrets", "arthur": "gossip exchange partner",
                          "nigel": "solves his cases before he does"},
    },
    "arthur": {
        "name": "Arthur Pickles",
        "role": "Landlord of The Leaning Pickle",
        "age": 63,
        "bio": ("Has run The Leaning Pickle for 35 years. Speaks in grunts, sighs and the occasional devastating "
                "sentence. Keeps a dartboard with the Mayor's face on it 'for tradition'."),
        "personality": ["grumpy", "laconic", "secretly kind", "deeply sceptical of the council", "polishes the same glass forever"],
        "speech": "Low, slow, grumbling; very short sentences; longer silences.",
        "catchphrases": ["No.", "We're closed. Emotionally.", "That'll be four pounds and an apology."],
        "look": {
            "height": 1.74, "build": "broad", "head": 0.34, "skin": "#D9A58A", "nose": "bulb",
            "hair": {"style": "flat_cap", "colour": "#6B6B6B"},
            "beard": {"style": "stubble", "colour": "#6B6B6B"},
            "eyebrows": {"style": "heavy", "colour": "#4E4E4E"},
            "outfit": {"jacket": "#3E3A33", "jacket_pattern": "knit_vest", "trousers": "#2E2B26", "shirt": "#D8CDB8",
                       "neck": {"type": "none"}, "shoes": "#2B1D14", "accessory": "tea_towel"},
            "silhouette": "broad barrel chest, flat cap, tea towel over one shoulder",
        },
        "voice": {"model": "en_GB-vctk-medium", "speaker": "p270", "length_scale": 1.15,
                  "noise_scale": 0.6, "noise_w": 0.7, "volume": 1.0},
        "relationships": {"winston": "tolerates him for the bar tab", "margaret": "the only person he fears",
                          "reginald": "banned (twice)", "brenda": "trades gossip for crisps",
                          "nigel": "serves him lemonade 'on duty'"},
    },
    "nigel": {
        "name": "Inspector Nigel Nonsense",
        "role": "Police inspector (the only one)",
        "age": 39,
        "bio": ("Appointed by Winston after winning the 'Best Hat' contest. Has solved zero crimes and arrested "
                "himself once 'to test the system'. Takes notes constantly; none are legible."),
        "personality": ["confused", "earnest", "enthusiastic", "literal-minded", "accidentally right at the worst moment"],
        "speech": "Eager, slightly too loud; misunderstands idioms; repeats the last word others said.",
        "catchphrases": ["Right. Wrong. Right?", "I'm going to need everyone to remain… whatever you're doing.",
                         "Case closed. Which case?"],
        "look": {
            "height": 1.84, "build": "lanky", "head": 0.30, "skin": "#EDC4A6", "nose": "long",
            "hair": {"style": "custodian_helmet", "colour": "#1B2A4A"},
            "moustache": {"style": "pencil", "colour": "#7A5A3A"},
            "eyebrows": {"style": "worried", "colour": "#7A5A3A"},
            "outfit": {"jacket": "#1B2A4A", "jacket_pattern": "uniform", "trousers": "#1B2A4A", "shirt": "#FFFFFF",
                       "neck": {"type": "tie", "colour": "ink"}, "shoes": "#111111", "accessory": "notebook"},
            "silhouette": "very tall and thin, tall custodian helmet, notebook raised",
        },
        "voice": {"model": "en_GB-vctk-medium", "speaker": "p237", "length_scale": 0.95,
                  "noise_scale": 0.7, "noise_w": 0.8, "volume": 1.0},
        "relationships": {"winston": "hero worship", "margaret": "terrified of her forms",
                          "reginald": "thinks he's a suspect in everything (correct)", "brenda": "his best informant",
                          "arthur": "his 'safe house'"},
    },
}

RUNNING_GAGS = [
    "The Town Hall clock faces the wall; characters check the time on it anyway.",
    "Margaret produces the exact form needed for any absurd situation.",
    "Reginald says 'For the record — I was against it' after every disaster, even ones he proposed.",
    "Brenda already knows the news before it is announced.",
    "Nigel arrests the wrong object (a bench, a goose, a puddle).",
    "Arthur's pub chalkboard comments on the episode's disaster.",
    "Winston unveils a commemorative plaque for every mistake.",
]

AUDIO_IDENTITY = {
    "theme": "Pompous brass-band style fanfare in B-flat major, 4 bars, then a deflating trombone 'wah-wah'",
    "sting": "Two-note tuba button + teacup clink at the end of every episode",
    "ambience": {"town_hall": "room tone with ticking clock", "pub": "murmur and glasses", "street": "birds and distant traffic"},
    "music_policy": "Only self-generated music (assets generated by bobbington/sound.py) or licensed tracks with licence file",
}
