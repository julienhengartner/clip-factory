"""Bobstadt – der Stadtzustand als Teil des Gedächtnisses.

Spielregel (öffentlich in der Instagram-Bio beobachtet, 16.11.2026):
    "Jeder Follower = 1 Einwohner + 1.000 € für Bobstadt. Ihr entscheidet, was gebaut wird."

Daraus folgt:  Einwohner = Follower,  Budget = Follower × 1.000 €,  Kasse = Budget − Ausgaben.
Ausgaben = Summe der gebauten Gebäude + Korrekturwert (zum Abgleich mit den echten Kanalzahlen).

Gebäudepreise im Katalog sind SPIELDESIGN-ANNAHMEN (data/city_catalog.json überschreibt sie).
Der Startbestand stammt aus öffentlich sichtbaren Beitragstexten und ist bis zur Bestätigung als
'unbestätigt' markiert.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from pydantic import BaseModel

from brain.memory import Memory
from config import Settings

EUR_PER_FOLLOWER = 1000
MILESTONE_STEP = 500

# Grammatik: Artikel im Nominativ -> Akkusativ/Dativ
_ACC = {"der": "den", "die": "die", "das": "das"}
_DAT = {"der": "dem", "die": "der", "das": "dem"}


class BuildingType(BaseModel):
    key: str
    name: str
    article: str           # der | die | das
    cost_eur: int
    keywords: list[str]    # Wortstämme für die Erkennung in Kommentaren
    shape: str             # house | tower | park | stadium | hospital | station | generic
    color: tuple[int, int, int]
    wiki: str              # Wikipedia-Artikel für echte Hintergrundfakten
    repeatable: bool = False

    @property
    def nom(self) -> str:
        return f"{self.article} {self.name}"

    @property
    def acc(self) -> str:
        return f"{_ACC[self.article]} {self.name}"

    @property
    def dat(self) -> str:
        return f"{_DAT[self.article]} {self.name}"


DEFAULT_CATALOG: list[BuildingType] = [BuildingType(**b) for b in [
    dict(key="wohnviertel", name="Wohnviertel", article="das", cost_eur=500_000, keywords=["wohnviertel", "wohnungen", "häuser", "haeuser", "siedlung"], shape="house", color=(214, 140, 90), wiki="Wohngebiet", repeatable=True),
    dict(key="wohnturm", name="Wohnturm", article="der", cost_eur=1_400_000, keywords=["wohnturm", "wohntürme", "hochhaus", "hochhäuser", "wolkenkratzer"], shape="tower", color=(120, 150, 200), wiki="Hochhaus", repeatable=True),
    dict(key="baeckerei", name="Bäckerei", article="die", cost_eur=150_000, keywords=["bäckerei", "baeckerei", "bäcker", "brötchen"], shape="generic", color=(222, 184, 120), wiki="Bäckerei"),
    dict(key="doener", name="Dönerladen", article="der", cost_eur=120_000, keywords=["döner", "doener", "dönerladen", "kebab"], shape="generic", color=(200, 90, 60), wiki="Döner Kebab"),
    dict(key="supermarkt", name="Supermarkt", article="der", cost_eur=400_000, keywords=["supermarkt", "einkaufen", "laden"], shape="generic", color=(90, 170, 120), wiki="Supermarkt"),
    dict(key="spielplatz", name="Spielplatz", article="der", cost_eur=100_000, keywords=["spielplatz", "rutsche", "schaukel"], shape="park", color=(110, 190, 90), wiki="Spielplatz"),
    dict(key="park", name="Stadtpark", article="der", cost_eur=300_000, keywords=["park", "stadtpark", "grünfläche", "bäume"], shape="park", color=(80, 170, 80), wiki="Stadtpark"),
    dict(key="skatepark", name="Skatepark", article="der", cost_eur=250_000, keywords=["skatepark", "skaten", "skateboard"], shape="park", color=(150, 150, 160), wiki="Skatepark"),
    dict(key="kita", name="Kita", article="die", cost_eur=600_000, keywords=["kita", "kindergarten", "kindertagesstätte"], shape="generic", color=(240, 200, 80), wiki="Kindertagesstätte"),
    dict(key="schule", name="Schule", article="die", cost_eur=1_200_000, keywords=["schule", "grundschule", "gymnasium"], shape="generic", color=(230, 160, 70), wiki="Schule"),
    dict(key="bibliothek", name="Bibliothek", article="die", cost_eur=700_000, keywords=["bibliothek", "bücherei", "buecherei"], shape="generic", color=(160, 110, 80), wiki="Bibliothek"),
    dict(key="feuerwache", name="Feuerwache", article="die", cost_eur=900_000, keywords=["feuerwehr", "feuerwache"], shape="generic", color=(210, 50, 50), wiki="Feuerwehr"),
    dict(key="polizei", name="Polizeiwache", article="die", cost_eur=800_000, keywords=["polizei", "polizeiwache", "wache"], shape="generic", color=(60, 90, 170), wiki="Polizei"),
    dict(key="krankenhaus", name="Krankenhaus", article="das", cost_eur=2_500_000, keywords=["krankenhaus", "klinik", "spital", "hospital"], shape="hospital", color=(235, 235, 240), wiki="Krankenhaus"),
    dict(key="bahnhof", name="Bahnhof", article="der", cost_eur=2_000_000, keywords=["bahnhof", "zug", "bahn", "gleis"], shape="station", color=(170, 120, 90), wiki="Bahnhof"),
    dict(key="stadion", name="Stadion", article="das", cost_eur=3_000_000, keywords=["stadion", "fußball", "fussball", "fc bobstadt"], shape="stadium", color=(200, 200, 210), wiki="Fußballstadion"),
    dict(key="freibad", name="Freibad", article="das", cost_eur=1_500_000, keywords=["freibad", "schwimmbad", "pool", "baden"], shape="park", color=(70, 170, 230), wiki="Freibad"),
    dict(key="kino", name="Kino", article="das", cost_eur=1_000_000, keywords=["kino", "film"], shape="generic", color=(120, 60, 140), wiki="Kino"),
    dict(key="museum", name="Museum", article="das", cost_eur=900_000, keywords=["museum", "ausstellung"], shape="generic", color=(200, 190, 170), wiki="Museum"),
    dict(key="rathaus", name="Rathaus", article="das", cost_eur=1_800_000, keywords=["rathaus"], shape="generic", color=(190, 150, 110), wiki="Rathaus"),
    dict(key="zoo", name="Zoo", article="der", cost_eur=2_200_000, keywords=["zoo", "tierpark", "tiere"], shape="park", color=(140, 180, 70), wiki="Zoo"),
    dict(key="windpark", name="Windpark", article="der", cost_eur=1_600_000, keywords=["windpark", "windrad", "windräder", "windkraft"], shape="tower", color=(235, 235, 235), wiki="Windpark"),
    dict(key="universitaet", name="Universität", article="die", cost_eur=5_000_000, keywords=["universität", "uni", "hochschule"], shape="generic", color=(150, 60, 60), wiki="Universität"),
    dict(key="flughafen", name="Flughafen", article="der", cost_eur=8_000_000, keywords=["flughafen", "flugplatz", "flugzeug"], shape="station", color=(180, 180, 190), wiki="Flughafen"),
]]

# Öffentlich sichtbare Beitragstexte (Abruf 16.11.2026) – UNBESTÄTIGT, bis der Nutzer bestätigt
SEED_RESIDENTS = 13_400            # "13.4K" Follower, gerundet
SEED_BUILDINGS = [
    ("stadion", "Stadion des 1. FC Bobstadt", "Beitrag: '1. FC Bobstadt ist gegründet'"),
    ("doener", "Döner am Stadion", "Beitrag: Döner am Stadion eröffnet"),
    ("krankenhaus", "Krankenhaus mit Rettungshubschrauber", "Beitrag: '12.500!' – Krankenhaus angekündigt"),
    ("bahnhof", "Bahnhof", "Beitrag erwähnt einen Bahnhof"),
    ("wohnturm", "Wohntürme", "Beitrag erwähnt Wohntürme"),
]


def fmt_int(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def fmt_eur(n: int) -> str:
    """Gut sprechbare Beträge: 1,5 Millionen Euro / 150.000 Euro."""
    n = int(n)
    if abs(n) >= 1_000_000:
        v = n / 1_000_000
        s = f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{s} Millionen Euro" if s != "1" else "1 Million Euro"
    return f"{fmt_int(n)} Euro"


class CityState(BaseModel):
    residents: int | None
    residents_source: str
    budget_eur: int
    spent_eur: int
    available_eur: int
    buildings: list[dict]
    confirmed: bool
    next_milestone: int | None

    def built_kinds(self) -> set[str]:
        return {b["kind"] for b in self.buildings if b["status"] == "built"}


class City:
    def __init__(self, settings: Settings, memory: Memory):
        self.s, self.memory = settings, memory
        self.catalog = self._load_catalog()

    # --- Katalog --------------------------------------------------------------------
    def _load_catalog(self) -> dict[str, BuildingType]:
        cat = {b.key: b for b in DEFAULT_CATALOG}
        f = self.s.data_dir / "city_catalog.json"
        if f.is_file():
            for entry in json.loads(f.read_text(encoding="utf-8")):
                base = cat.get(entry.get("key"), None)
                cat[entry["key"]] = BuildingType(**{**(base.model_dump() if base else {}), **entry})
        return cat

    def match_building(self, text: str) -> BuildingType | None:
        low = text.lower()
        hits = [(len(k), b) for b in self.catalog.values() for k in b.keywords
                if re.search(rf"(?<![a-zäöüß]){re.escape(k)}", low)]
        return max(hits, key=lambda h: h[0])[1] if hits else None

    # --- Startbestand ---------------------------------------------------------------
    def ensure_seed(self) -> None:
        if self.memory.get_setting("city.seeded"):
            return
        for kind, name, note in SEED_BUILDINGS:
            b = self.catalog[kind]
            self.memory.add_building(kind, name, b.cost_eur, "built", "seed", confirmed=False, note=note)
        self.memory.set_setting("city.residents_manual", {"value": SEED_RESIDENTS, "source": "öffentliches Profil "
                                "(13.4K, gerundet, 16.11.2026)", "confirmed": False})
        self.memory.set_setting("city.last_milestone", (SEED_RESIDENTS // MILESTONE_STEP) * MILESTONE_STEP)
        self.memory.set_setting("city.seeded", True)
        self.memory.log("info", "city", "Bobstadt-Startbestand aus öffentlichen Beiträgen angelegt (unbestätigt)")

    # --- Zustand --------------------------------------------------------------------
    def residents(self) -> tuple[int | None, str, bool]:
        hist = self.memory.follower_history("instagram", limit=1)
        if hist and hist[-1]["followers"] is not None:
            return int(hist[-1]["followers"]), f"Instagram-API ({hist[-1]['collected_at'][:10]})", True
        manual = self.memory.get_setting("city.residents_manual")
        if manual:
            return int(manual["value"]), manual["source"], bool(manual.get("confirmed"))
        return None, "unbekannt", False

    def state(self) -> CityState:
        self.ensure_seed()
        residents, source, res_ok = self.residents()
        buildings = self.memory.buildings()
        spent = sum(b["cost_eur"] for b in buildings if b["status"] == "built") + \
            int(self.memory.get_setting("city.spent_adjust_eur", 0))
        budget = (residents or 0) * EUR_PER_FOLLOWER
        confirmed = res_ok and all(b["confirmed"] for b in buildings) and \
            bool(self.memory.get_setting("city.ledger_confirmed", False))
        nxt = None
        if residents is not None:
            nxt = (residents // MILESTONE_STEP + 1) * MILESTONE_STEP
        return CityState(residents=residents, residents_source=source, budget_eur=budget, spent_eur=spent,
                         available_eur=budget - spent, buildings=buildings, confirmed=confirmed, next_milestone=nxt)

    def affordable(self, state: CityState) -> list[BuildingType]:
        built = state.built_kinds()
        return sorted([b for b in self.catalog.values() if b.cost_eur <= state.available_eur
                       and (b.repeatable or b.key not in built)], key=lambda b: b.cost_eur)

    def unbuilt(self, state: CityState) -> list[BuildingType]:
        built = state.built_kinds()
        return [b for b in self.catalog.values() if b.repeatable or b.key not in built]

    # --- Pflege durch den Nutzer -----------------------------------------------------
    def set_residents(self, value: int, source: str = "manuell eingegeben") -> None:
        self.memory.set_setting("city.residents_manual", {"value": int(value), "source": source, "confirmed": True})

    def set_spent_adjust(self, eur: int) -> None:
        self.memory.set_setting("city.spent_adjust_eur", int(eur))

    def confirm(self) -> None:
        for b in self.memory.buildings():
            if not b["confirmed"]:
                self.memory.db.execute("UPDATE city_buildings SET confirmed=1 WHERE id=?", (b["id"],))
        manual = self.memory.get_setting("city.residents_manual")
        if manual:
            self.memory.set_setting("city.residents_manual", {**manual, "confirmed": True})
        self.memory.set_setting("city.ledger_confirmed", True)

    # --- Community-Stimmen aus Kommentaren ------------------------------------------
    NAME_PATTERNS = [re.compile(p, re.I) for p in (
        r"(?:name|nennt?\s+(?:es|ihn|das viertel)|heißen|heissen|taufen)\s*[:\-]?\s*[\"„“']?([A-ZÄÖÜ][\wäöüß\-]{2,24}(?:\s[A-ZÄÖÜ][\wäöüß\-]{2,24})?)",
        r"[\"„“]([A-ZÄÖÜ][\wäöüß\-]{2,24}(?:\s[A-ZÄÖÜ][\wäöüß\-]{2,24})?)[\"“”]")]

    def collect_votes(self) -> dict[str, int]:
        """Zählt Gebäudewünsche und Namensvorschläge aus analysierten Kommentaren (Spam ausgeschlossen)."""
        counted = {"building": 0, "name": 0}
        done = set(self.memory.get_setting("city.counted_comments", []))
        new_done = []
        for c in self.memory.comments(limit=2000):
            if c["id"] in done or c["category"] in (None, "spam"):
                continue
            b = self.match_building(c["text"])
            if b:
                self.memory.vote("building", b.key, c["author_hash"])
                counted["building"] += 1
            for pat in self.NAME_PATTERNS:
                m = pat.search(c["text"])
                if m:
                    self.memory.vote("name", m.group(1).strip(), c["author_hash"])
                    counted["name"] += 1
                    break
            new_done.append(c["id"])
        self.memory.set_setting("city.counted_comments", sorted(done | set(new_done)))
        return counted

    def top_building_wish(self, state: CityState, min_votes: int = 2) -> tuple[BuildingType, int] | None:
        built = state.built_kinds()
        for p in self.memory.proposals("building"):
            b = self.catalog.get(p["value"])
            if b and p["votes"] >= min_votes and (b.repeatable or b.key not in built):
                return b, p["votes"]
        return None

    def followers_needed(self, gap_eur: int) -> int:
        return math.ceil(max(0, gap_eur) / EUR_PER_FOLLOWER)

    def snapshot_path(self) -> Path:
        return self.s.data_dir / "bobstadt.json"
