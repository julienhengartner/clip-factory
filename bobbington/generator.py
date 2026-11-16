"""Episode generator (offline, free).

Builds complete, validated episodes from authored comedy premises + the current simulation state:
story concept, scene list, dialogue, actions (animation instructions), camera instructions, voice
assignment (from the cast bible), sound effects and simulation consequences. Subtitles and timing are
produced later from the real voice recordings (bobbington/timeline.py).

The premises are hand-written comedy material in the house style; the generator handles structure,
staging, continuity (no premise is reused, the simulation picks what fits) and validation.
A language model can later add new premises – the format stays the same.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from bobbington.episode import Episode

# Each premise: beginning / conflict / escalation / twist / punchline in the cast's voices.
PREMISES: list[dict] = [
    {
        "id": "rain", "title": "THE MAYOR BANS RAIN!", "department": "Parks & Traditions",
        "logline": "Winston outlaws rain to save the Backwards Parade – and dries up Bobbington's most beloved puddle.",
        "hook": "From today, rain is no longer permitted in Bobbington.",
        "decree": "Citizens! For centuries rain has ruined our parades. As of this morning, it is banned. Weather, you have been warned.",
        "objection": "Mayor. The rain does not read the council minutes.",
        "comeback": "Then it shall be fined, Margaret. Heavily.",
        "reginald": "Visionary, Mayor. A dry Bobbington is a happy Bobbington. I'll print the leaflets.",
        "form": "Form nineteen C. Notice to the sky. Delivered by pigeon.",
        "gossip": "Well, I heard the clouds have been seen heading to Little Muddle. Traitors.",
        "nigel": "So if it drizzles, do I arrest the drizzle, or the sky?",
        "pub": "No rain means no puddle. No puddle means no Great Puddle Day. No puddle day means no customers.",
        "pub_button": "Well done. You've dried up the only tourist attraction.",
        "chalkboard": "PUDDLE: MISSING.\nREWARD: ONE PINT.",
        "chaos": "Mayor, the Historic Puddle has evaporated. The ducks have filed a complaint.",
        "denial": "Nonsense. The ducks are delighted. They simply express it badly.",
        "twist": "One small detail, Mayor. The puddle is listed. Losing it costs the town fifty thousand pounds.",
        "reaction": "Ah.",
        "punchline": "Citizens! In a historic reversal, I hereby make rain compulsory. On Saturdays. Over the puddle only.",
        "button": "For the record, I was always pro-puddle.",
        "sim_effects": [{"type": "complaint", "department": "Parks & Traditions", "text": "Historic Puddle evaporated"},
                        {"type": "expense", "department": "Parks & Traditions", "amount": 50000,
                         "description": "Heritage penalty: listed puddle lost"}],
    },
    {
        "id": "roundabout", "title": "THE MAYOR BUILDS A ROUNDABOUT", "department": "Public Works",
        "logline": "Winston commissions Bobbington's first roundabout – on a road with no junctions.",
        "hook": "Bobbington will have the finest roundabout in England.",
        "decree": "Citizens! Every great town has a roundabout. Today, Bobbington joins history. On Main Street. Where there is nothing to go round.",
        "objection": "Mayor. A roundabout needs a junction.",
        "comeback": "Then we shall build a junction, Margaret. Around the roundabout.",
        "reginald": "Genius, Mayor. Circular thinking. The public will go round and round.",
        "form": "Form forty-four R. Planning permission for a circle. Approved in circles.",
        "gossip": "Well, I heard Mr Pemberton has been going round it since Tuesday. He can't find the exit.",
        "nigel": "Right. If someone goes round it twice, is that speeding or loitering?",
        "pub": "Deliveries go round twice and come back. I've had the same barrel arrive four times.",
        "pub_button": "Four times. Still no beer.",
        "chalkboard": "THIS WAY ->\n<- NO, THIS WAY",
        "chaos": "Mayor, the bus is stuck on the roundabout. It's been going round for six hours.",
        "denial": "Excellent. The longest bus route in the county.",
        "twist": "One small detail, Mayor. Your own car is on that bus. You lent it to the driver.",
        "reaction": "Hmm.",
        "punchline": "Citizens! To solve the roundabout, I am commissioning a second roundabout. To go round the first one.",
        "button": "For the record, I was against circles in general.",
        "sim_effects": [{"type": "project", "name": "Main Street Roundabout", "department": "Public Works",
                         "budget": 120000, "note": "No junction. Building one around it."},
                        {"type": "complaint", "department": "Public Works", "text": "Bus trapped on roundabout"}],
    },
    {
        "id": "silence", "title": "THE MAYOR BANS COMPLAINING", "department": "Town Clerk's Office",
        "logline": "Swamped by complaints, Winston bans complaining – and receives a complaint about the ban.",
        "hook": "As of noon, complaining in Bobbington is illegal.",
        "decree": "Citizens! The complaints box is full. Therefore complaints are banned. Problem solved. Historic.",
        "objection": "Mayor. Banning complaints is a complaint about complaints.",
        "comeback": "Then I withdraw it, Margaret, and replace it with a decree.",
        "reginald": "Masterful, Mayor. A town with no complaints is a town with no problems. On paper.",
        "form": "Form one. Complaint about the ban on complaints. Seventeen copies received.",
        "gossip": "Well, I heard people are complaining in whispers. Behind the bins.",
        "nigel": "So if somebody sighs loudly, is that a complaint or just weather?",
        "pub": "I'm not complaining. I'm describing my disappointment. In detail.",
        "pub_button": "That'll be four pounds and an apology.",
        "chalkboard": "NO COMPLAINTS.\n(WE'VE TRIED.)",
        "chaos": "Mayor, the complaints box has exploded. Literally. It was very full.",
        "denial": "A celebration of public engagement, Reginald. Confetti.",
        "twist": "One small detail, Mayor. Your request for a pay rise was filed as a complaint.",
        "reaction": "Oh dear.",
        "punchline": "Citizens! Complaining is legal again. Please form an orderly queue. Starting with me.",
        "button": "For the record, I have never complained about anything.",
        "sim_effects": [{"type": "complaint", "department": "Town Clerk's Office", "text": "Complaint about the ban on complaints"},
                        {"type": "expense", "department": "Town Clerk's Office", "amount": 340,
                         "description": "Replacement complaints box (exploded)"}],
    },
]


def build_episode(premise: dict, number: int) -> Episode:
    """Turns a premise into a staged, validated episode (same structure as the pilot)."""
    p = premise
    shots = [
        {"id": "cold_open", "set": "mayors_office", "cast": {"winston": "desk"},
         "camera": {"type": "push_in", "target": "winston", "from": 2.4, "to": 1.6},
         "sfx": [{"name": "clock_tick", "at": 0.0, "volume": 0.35}],
         "lines": [{"speaker": "winston", "text": p["hook"], "action": "slam_desk", "emotion": "proud"}]},
        {"id": "title", "set": "title_card", "cast": {}, "duration": 2.6, "camera": {"type": "static"},
         "music": {"name": "theme", "at": 0.0, "volume": 0.9},
         "on_screen": {"title": "BOBBINGTON", "subtitle": p["title"].title()}},
        {"id": "announcement", "set": "council_chamber",
         "cast": {"winston": "dais", "margaret": "clerk_desk", "reginald": "bench_left"},
         "camera": {"type": "wide", "target": "winston"},
         "sfx": [{"name": "gavel", "at": 0.1, "volume": 0.9}, {"name": "murmur", "at": 0.0, "volume": 0.25, "duration": 4.0}],
         "lines": [{"speaker": "winston", "text": p["decree"], "action": "raise_arms", "emotion": "grand"}]},
        {"id": "objection", "set": "council_chamber", "cast": {"winston": "dais", "margaret": "clerk_desk"},
         "camera": {"type": "two_shot", "targets": ["margaret", "winston"]},
         "lines": [{"speaker": "margaret", "text": p["objection"], "action": "fold_arms", "emotion": "deadpan"},
                   {"speaker": "winston", "text": p["comeback"], "action": "point_self", "emotion": "smug"}]},
        {"id": "reginald", "set": "council_chamber", "cast": {"reginald": "bench_left"},
         "camera": {"type": "close", "target": "reginald"},
         "lines": [{"speaker": "reginald", "text": p["reginald"], "action": "thumbs_up", "emotion": "smarmy"}]},
        {"id": "form", "set": "council_chamber", "cast": {"margaret": "clerk_desk"},
         "camera": {"type": "close", "target": "margaret"},
         "sfx": [{"name": "stamp", "at_line_end": 0, "repeat": 3, "gap": 0.28, "volume": 0.9}],
         "lines": [{"speaker": "margaret", "text": p["form"], "action": "stamp", "emotion": "deadpan"}]},
        {"id": "street", "set": "main_street", "cast": {"brenda": "pavement_left", "nigel": "pavement_right"},
         "camera": {"type": "two_shot", "targets": ["brenda", "nigel"]},
         "sfx": [{"name": "birds", "at": 0.0, "volume": 0.25, "duration": 8.0}],
         "lines": [{"speaker": "brenda", "text": p["gossip"], "action": "gossip_lean", "emotion": "thrilled"},
                   {"speaker": "nigel", "text": p["nigel"], "action": "scratch_head", "emotion": "confused"}]},
        {"id": "pub", "set": "pub", "cast": {"arthur": "behind_bar"},
         "camera": {"type": "push_in", "target": "arthur", "from": 2.6, "to": 1.7},
         "sfx": [{"name": "glass_clink", "at": 0.2, "volume": 0.6}], "on_screen": {"chalkboard": p["chalkboard"]},
         "lines": [{"speaker": "arthur", "text": p["pub"], "action": "polish_glass", "emotion": "grumpy"},
                   {"speaker": "arthur", "text": p["pub_button"], "action": "shake_head", "emotion": "grumpy",
                    "optional": True}]},
        {"id": "chaos", "set": "council_chamber",
         "cast": {"winston": "dais", "reginald": "bench_left", "margaret": "clerk_desk"},
         "camera": {"type": "two_shot", "targets": ["reginald", "winston"]},
         "lines": [{"speaker": "reginald", "text": p["chaos"], "action": "wring_hands", "emotion": "panicked"},
                   {"speaker": "winston", "text": p["denial"], "action": "raise_arms", "emotion": "proud"}]},
        {"id": "twist", "set": "council_chamber", "cast": {"margaret": "clerk_desk", "winston": "dais"},
         "camera": {"type": "close", "target": "margaret"},
         "sfx": [{"name": "record_scratch", "at_line_end": 0, "volume": 0.7}],
         "lines": [{"speaker": "margaret", "text": p["twist"], "action": "lift_clipboard", "emotion": "deadpan"}]},
        {"id": "reaction", "set": "council_chamber", "cast": {"winston": "dais"},
         "camera": {"type": "push_in", "target": "winston", "from": 2.1, "to": 1.6},
         "lines": [{"speaker": "winston", "text": p["reaction"], "action": "freeze", "emotion": "shocked", "pause_before": 0.5}]},
        {"id": "punchline", "set": "mayors_office", "cast": {"winston": "desk"},
         "camera": {"type": "push_in", "target": "winston", "from": 2.3, "to": 1.6},
         "music": {"name": "fanfare_short", "at_line_end": 0, "volume": 0.8},
         "lines": [{"speaker": "winston", "text": p["punchline"], "action": "raise_arms", "emotion": "grand"},
                   {"speaker": "winston", "text": "Historic.", "action": "nod", "emotion": "proud"}]},
        {"id": "button", "set": "council_chamber", "cast": {"reginald": "bench_left", "margaret": "clerk_desk"},
         "camera": {"type": "two_shot", "targets": ["reginald", "margaret"]},
         "music": {"name": "sting", "at_line_end": 1, "volume": 0.9},
         "lines": [{"speaker": "reginald", "text": p["button"], "action": "fold_arms", "emotion": "smug"},
                   {"speaker": "margaret", "text": "Noted.", "action": "stamp", "emotion": "deadpan"}]},
    ]
    data = {
        "id": f"s01e{number:02d}", "title": p["title"], "logline": p["logline"],
        "structure": {"beginning": p["hook"], "conflict": p["objection"], "escalation": p["chaos"],
                      "twist": p["twist"], "punchline": p["punchline"]},
        "running_gags": ["form_27b", "for_the_record", "brenda_knew_first", "nigel_arrests_object", "pub_chalkboard"],
        "sim_effects": p["sim_effects"], "shots": shots,
        "extensions": [{"after_shot": "street", "speaker": "nigel", "text": "Case closed. Which case?",
                        "action": "scratch_head", "emotion": "confused"},
                       {"after_shot": "objection", "speaker": "margaret",
                        "text": "I shall need that in writing. From someone qualified.", "action": "fold_arms",
                        "emotion": "deadpan"}],
    }
    return Episode.model_validate(data)


def choose_premise(used: set[str], sim_report: dict | None = None, seed: str = "") -> dict | None:
    """Prefers premises that match the departments with open complaints; never repeats a premise."""
    candidates = [p for p in PREMISES if p["id"] not in used]
    if not candidates:
        return None
    hot = {c["department"] for c in (sim_report or {}).get("open_complaints", [])}
    rng = random.Random(seed)
    return max(candidates, key=lambda p: (p["department"] in hot, rng.random()))


def generate(out_dir: Path, used: set[str], number: int, sim_report: dict | None = None) -> Path | None:
    premise = choose_premise(used, sim_report, seed=str(number))
    if premise is None:
        return None
    ep = build_episode(premise, number)
    path = Path(out_dir) / f"{ep.id}_{premise['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ep.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path
