"""Learning Agent: wertet echte Performance-Daten aus und passt die Strategie an.

Bewertung je Video (relativ zum Kanal-Median, damit Kanalwachstum die Werte nicht verzerrt):
  Engagement = (Likes + 5·Kommentare + 8·Shares + 4·Saves) / Views
  Score      = 0,5·(Engagement / Median) + 0,5·sqrt(Views / Median-Views)
Aggregiert nach Themenkategorie, Hook-Muster und Längenbereich; geglättet mit einem Prior von 1,0
(Gewicht 2), damit einzelne Ausreisser die Strategie nicht kippen. Ohne Performance-Daten wird nichts
"gelernt" – es werden keine Werte erfunden.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from statistics import median

from brain.memory import Memory

PRIOR, PRIOR_WEIGHT = 1.0, 2.0


def length_bucket(seconds: float | None) -> str:
    if not seconds:
        return "unbekannt"
    lo = int(seconds // 5 * 5)
    return f"{lo}-{lo + 5}s"


class LearningAgent:
    name = "learning"

    def __init__(self, memory: Memory):
        self.memory = memory

    def video_scores(self) -> dict[str, dict]:
        rows = [r for r in self.memory.latest_performance() if r["video_id"] and (r["views"] or r["reach"])]
        if not rows:
            return {}
        def base(r): return float(r["views"] or r["reach"] or 0)
        eng = {r["video_id"]: ((r["likes"] or 0) + 5 * (r["comments"] or 0) + 8 * (r["shares"] or 0)
                               + 4 * (r["saves"] or 0)) / base(r) for r in rows}
        med_eng = median(eng.values()) or 1e-9
        med_views = median(base(r) for r in rows) or 1.0
        return {r["video_id"]: {"score": round(0.5 * eng[r["video_id"]] / med_eng + 0.5 * math.sqrt(base(r) / med_views), 4),
                                "views": base(r), "engagement": round(eng[r["video_id"]], 5)} for r in rows}

    def update(self) -> dict:
        scores = self.video_scores()
        groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for vid, sc in scores.items():
            v = self.memory.get_video(vid)
            if not v:
                continue
            groups["topic_category"][v["category"]].append(sc["score"])
            if v.get("hook_pattern"):
                groups["hook_pattern"][v["hook_pattern"]].append(sc["score"])
            groups["length_bucket"][length_bucket(v.get("duration_s"))].append(sc["score"])
        for kind, by_key in groups.items():
            for key, vals in by_key.items():
                mean = (sum(vals) + PRIOR * PRIOR_WEIGHT) / (len(vals) + PRIOR_WEIGHT)
                self.memory.set_insight(kind, key, {"mean": round(mean, 4), "n": len(vals),
                                                    "raw_mean": round(sum(vals) / len(vals), 4)},
                                        confidence=round(len(vals) / (len(vals) + PRIOR_WEIGHT), 3))

        cats = self.memory.insights("topic_category")
        hooks = self.memory.insights("hook_pattern")
        recommendations = {
            "repeat_categories": sorted([k for k, v in cats.items() if v["mean"] > 1.15 and v["n"] >= 2],
                                        key=lambda k: -cats[k]["mean"]),
            "avoid_categories": sorted(k for k, v in cats.items() if v["mean"] < 0.8 and v["n"] >= 3),
            "best_hook_patterns": sorted(hooks, key=lambda k: -hooks[k]["mean"])[:3],
            "based_on_videos": len(scores),
        }
        self.memory.set_insight("strategy", "recommendations", recommendations,
                                confidence=min(1.0, len(scores) / 20))

        issues: Counter = Counter()
        for v in self.memory.list_videos(status="qc_failed", limit=200):
            for c in (v.get("qc") or {}).get("checks", []):
                if not c["passed"] and c["severity"] == "error":
                    issues[c["name"]] += 1
        failures = Counter(e["source"] for e in self.memory.events(level="error", limit=500))
        self.memory.set_insight("quality", "frequent_issues", {"qc": dict(issues), "errors_by_source": dict(failures)})
        return {"videos_with_data": len(scores), "recommendations": recommendations, "qc_issues": dict(issues)}

    def report(self) -> str:
        rec = self.memory.get_insight("strategy", "recommendations") or {}
        return json.dumps(rec, ensure_ascii=False)
