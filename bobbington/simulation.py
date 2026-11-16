"""Bobbington city simulation – a fictional town with a council, departments, budget, projects, businesses,
events, complaints and votes.

Rules:
- Starting values are FICTIONAL: 2,450 residents, £1,000,000 opening balance.
- Simulated citizens are completely separate from real social-media followers (no link anywhere).
- Money is stored in pence (integers – no rounding errors). The ledger is append-only and every entry
  stores the balance after posting, so every pound can be traced back to a description and a reference.
- Randomness is seeded (sim_seed), so a run is reproducible.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass

from storage.database import Database, utcnow

START_POPULATION = 2450
START_BALANCE_PENCE = 1_000_000 * 100
COUNCIL_TAX_PENCE_PER_RESIDENT_DAY = 115          # £1.15 per resident per day
CITIZEN_NAMES = ["Mrs Higgins", "Mr Pemberton", "Dorothy Wainwright", "Colin Fairweather", "Edna Pottage",
                 "Barry Thistlewood", "Agnes Crumpet", "Derek Noggin", "Pauline Tuppence", "Keith Marmalade"]

DEPARTMENTS = [  # name, head, annual budget (£)
    ("Mayor's Office", "winston", 60_000), ("Town Clerk's Office", "margaret", 45_000),
    ("Council", "reginald", 30_000), ("Public Works", None, 180_000), ("Waste & Recycling", None, 95_000),
    ("Police", "nigel", 85_000), ("Licensing", None, 12_000), ("Parks & Traditions", None, 40_000),
    ("Treasury", None, 0),
]
BUSINESSES = [  # name, owner, kind, weekly business rates (£)
    ("The Leaning Pickle", "arthur", "pub", 240), ("Crumbs (newsletter)", "brenda", "media", 15),
    ("Bobbington Bakery", None, "bakery", 120), ("Puddle End Post Office", None, "post office", 90),
    ("Biscuit Row Teas", None, "tea room", 80), ("Crumble & Sons Ironmonger", None, "hardware", 95),
]


class InsufficientFundsError(ValueError):
    pass


@dataclass
class Entry:
    id: int
    sim_day: int
    department: str
    kind: str
    amount_pence: int
    balance_after_pence: int
    description: str
    reference: str | None


def gbp(pence: int) -> str:
    sign = "-" if pence < 0 else ""
    pence = abs(pence)
    return f"{sign}£{pence // 100:,}.{pence % 100:02d}"


class CitySimulation:
    def __init__(self, db: Database, seed: int = 1347):
        self.db = db
        if self.get("initialised") is None:
            self._initialise(seed)
        self.rng = random.Random(f"{self.get('seed')}-{self.day}")

    # --- state ------------------------------------------------------------------------------
    def get(self, key: str, default=None):
        row = self.db.query_one("SELECT value_json FROM sim_state WHERE key=?", (key,))
        return json.loads(row["value_json"]) if row else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT INTO sim_state (key, value_json) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET "
                        "value_json=excluded.value_json", (key, json.dumps(value)))

    @property
    def day(self) -> int:
        return int(self.get("day", 0))

    @property
    def population(self) -> int:
        return int(self.get("population", START_POPULATION))

    def _initialise(self, seed: int) -> None:
        self.set("seed", seed)
        self.set("day", 0)
        self.set("population", START_POPULATION)
        for name, head, budget in DEPARTMENTS:
            self.db.execute("INSERT INTO sim_departments (name, head, annual_budget_pence) VALUES (?,?,?)",
                            (name, head, budget * 100))
        for name, owner, kind, rates in BUSINESSES:
            self.db.execute("INSERT INTO sim_businesses (name, owner, kind, weekly_rates_pence, status) VALUES (?,?,?,?,?)",
                            (name, owner, kind, rates * 100, "open"))
        self.db.execute("INSERT INTO sim_ledger (sim_day, department, kind, amount_pence, balance_after_pence, description,"
                        " reference, created_at) VALUES (0,'Treasury','opening',?,?,?,?,?)",
                        (START_BALANCE_PENCE, START_BALANCE_PENCE, "Opening balance (fictional starting budget)",
                         "init", utcnow()))
        self.set("initialised", True)

    # --- ledger -----------------------------------------------------------------------------
    @property
    def balance_pence(self) -> int:
        row = self.db.query_one("SELECT balance_after_pence FROM sim_ledger ORDER BY id DESC LIMIT 1")
        return int(row["balance_after_pence"]) if row else 0

    def post(self, department: str, kind: str, amount_pence: int, description: str, reference: str | None = None,
             allow_deficit: bool = False) -> Entry:
        if kind not in ("revenue", "expense"):
            raise ValueError("kind must be 'revenue' or 'expense'")
        if amount_pence <= 0:
            raise ValueError("amount must be positive")
        if not self.db.query_one("SELECT 1 FROM sim_departments WHERE name=?", (department,)):
            raise ValueError(f"unknown department '{department}'")
        new_balance = self.balance_pence + (amount_pence if kind == "revenue" else -amount_pence)
        if new_balance < 0 and not allow_deficit:
            raise InsufficientFundsError(f"{description}: would overdraw the town ({gbp(new_balance)})")
        eid = self.db.execute("INSERT INTO sim_ledger (sim_day, department, kind, amount_pence, balance_after_pence,"
                              " description, reference, created_at) VALUES (?,?,?,?,?,?,?,?)",
                              (self.day, department, kind, amount_pence, new_balance, description, reference, utcnow()))
        return Entry(eid, self.day, department, kind, amount_pence, new_balance, description, reference)

    def ledger(self, reference: str | None = None, limit: int = 1000) -> list[dict]:
        if reference:
            return self.db.query("SELECT * FROM sim_ledger WHERE reference=? ORDER BY id", (reference,))
        return self.db.query("SELECT * FROM sim_ledger ORDER BY id DESC LIMIT ?", (limit,))

    def audit(self) -> bool:
        """Recomputes every running balance from the entries – proves the books are consistent."""
        bal = 0
        for e in self.db.query("SELECT * FROM sim_ledger ORDER BY id"):
            bal += e["amount_pence"] if e["kind"] in ("opening", "revenue") else -e["amount_pence"]
            if bal != e["balance_after_pence"]:
                return False
        return True

    def department_totals(self) -> dict[str, dict[str, int]]:
        rows = self.db.query("SELECT department, kind, SUM(amount_pence) AS total FROM sim_ledger GROUP BY department, kind")
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r["department"], {})[r["kind"]] = int(r["total"])
        return out

    # --- time ---------------------------------------------------------------------------------
    def advance(self, days: int = 1) -> dict:
        summary = {"revenue": 0, "expenses": 0, "population_change": 0}
        for _ in range(days):
            day = self.day + 1
            self.set("day", day)
            tax = self.population * COUNCIL_TAX_PENCE_PER_RESIDENT_DAY
            self.post("Treasury", "revenue", tax, f"Council tax, day {day} ({self.population:,} residents)", f"day:{day}")
            summary["revenue"] += tax
            if day % 7 == 0:
                for b in self.db.query("SELECT * FROM sim_businesses WHERE status='open'"):
                    self.post("Treasury", "revenue", b["weekly_rates_pence"], f"Business rates – {b['name']}", f"day:{day}")
                    summary["revenue"] += b["weekly_rates_pence"]
            for d in self.db.query("SELECT * FROM sim_departments WHERE annual_budget_pence > 0"):
                cost = d["annual_budget_pence"] // 365
                self.post(d["name"], "expense", cost, f"Running costs, day {day}", f"day:{day}", allow_deficit=True)
                summary["expenses"] += cost
            rng = random.Random(f"{self.get('seed')}-{day}")
            mood = int(self.get("mood", 0))
            change = rng.randint(-2, 3) + (1 if mood > 0 else -1 if mood < 0 else 0)
            self.set("population", max(0, self.population + change))
            summary["population_change"] += change
        return summary

    # --- civic life ----------------------------------------------------------------------------
    def start_project(self, name: str, department: str, budget_pence: int, note: str = "",
                      episode_id: str | None = None) -> int:
        return self.db.execute("INSERT INTO sim_projects (name, department, budget_pence, status, note, started_day,"
                               " episode_id) VALUES (?,?,?,?,?,?,?)",
                               (name, department, budget_pence, "in_progress", note, self.day, episode_id))

    def spend_on_project(self, project_id: int, amount_pence: int, description: str) -> Entry:
        p = self.db.query_one("SELECT * FROM sim_projects WHERE id=?", (project_id,))
        if not p:
            raise ValueError("unknown project")
        entry = self.post(p["department"], "expense", amount_pence, f"{p['name']}: {description}", f"project:{project_id}")
        self.db.execute("UPDATE sim_projects SET spent_pence = spent_pence + ? WHERE id=?", (amount_pence, project_id))
        return entry

    def complete_project(self, project_id: int, status: str = "completed") -> None:
        self.db.execute("UPDATE sim_projects SET status=?, completed_day=? WHERE id=?", (status, self.day, project_id))

    def complain(self, department: str, text: str, citizen: str | None = None, episode_id: str | None = None) -> int:
        citizen = citizen or random.Random(f"{text}{self.day}").choice(CITIZEN_NAMES)
        self.set("mood", int(self.get("mood", 0)) - 1)
        return self.db.execute("INSERT INTO sim_complaints (sim_day, department, citizen, text, episode_id)"
                               " VALUES (?,?,?,?,?)", (self.day, department, citizen, text, episode_id))

    def resolve_complaint(self, complaint_id: int, status: str = "resolved") -> None:
        self.db.execute("UPDATE sim_complaints SET status=? WHERE id=?", (status, complaint_id))
        if status == "resolved":
            self.set("mood", int(self.get("mood", 0)) + 1)

    def event(self, name: str, kind: str, description: str, episode_id: str | None = None) -> int:
        return self.db.execute("INSERT INTO sim_events (sim_day, name, kind, description, episode_id) VALUES (?,?,?,?,?)",
                               (self.day, name, kind, description, episode_id))

    def open_vote(self, question: str, options: list[str], method: str = "council") -> int:
        return self.db.execute("INSERT INTO sim_votes (sim_day, question, method, options_json) VALUES (?,?,?,?)",
                               (self.day, question, method, json.dumps(options)))

    def close_vote(self, vote_id: int, bias: dict[str, float] | None = None) -> dict[str, int]:
        """Simulated citizens vote (seeded). `bias` lets a storyline tip the scales – still reproducible."""
        v = self.db.query_one("SELECT * FROM sim_votes WHERE id=?", (vote_id,))
        options = json.loads(v["options_json"])
        rng = random.Random(f"{self.get('seed')}-vote-{vote_id}")
        voters = 9 if v["method"] == "council" else int(self.population * rng.uniform(0.25, 0.45))
        weights = [1.0 + (bias or {}).get(o, 0.0) for o in options]
        results = {o: 0 for o in options}
        for _ in range(voters):
            results[rng.choices(options, weights=weights)[0]] += 1
        self.db.execute("UPDATE sim_votes SET results_json=?, status='closed' WHERE id=?", (json.dumps(results), vote_id))
        return results

    # --- episodes ------------------------------------------------------------------------------
    def apply_episode(self, episode_id: str, effects: list[dict]) -> dict:
        """Applies an episode's story consequences exactly once (idempotent via the ledger reference)."""
        ref = f"episode:{episode_id}"
        if self.get(f"applied:{episode_id}"):
            return {"status": "already_applied"}
        applied = []
        for fx in effects:
            if fx["type"] == "expense":
                self.post(fx["department"], "expense", int(round(fx["amount"] * 100)), fx["description"], ref,
                          allow_deficit=True)
            elif fx["type"] == "revenue":
                self.post(fx["department"], "revenue", int(round(fx["amount"] * 100)), fx["description"], ref)
            elif fx["type"] == "complaint":
                self.complain(fx["department"], fx["text"], episode_id=episode_id)
            elif fx["type"] == "event":
                self.event(fx["name"], fx.get("kind", "story"), fx.get("description", ""), episode_id)
            elif fx["type"] == "project":
                self.start_project(fx["name"], fx["department"], int(fx["budget"] * 100), fx.get("note", ""), episode_id)
            applied.append(fx["type"])
        self.set(f"applied:{episode_id}", True)
        return {"status": "applied", "effects": applied}

    def report(self) -> dict:
        return {
            "day": self.day, "population": self.population, "balance": gbp(self.balance_pence),
            "balance_pence": self.balance_pence, "mood": int(self.get("mood", 0)),
            "open_complaints": self.db.query("SELECT * FROM sim_complaints WHERE status='open' ORDER BY id DESC LIMIT 10"),
            "projects": self.db.query("SELECT * FROM sim_projects ORDER BY id DESC LIMIT 10"),
            "businesses": self.db.query("SELECT name, owner, kind, status FROM sim_businesses"),
            "books_consistent": self.audit(),
        }
