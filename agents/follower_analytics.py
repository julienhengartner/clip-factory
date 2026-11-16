"""Follower Analytics Agent: dokumentiert verfügbare Follower- und Engagement-Kennzahlen (nur aggregiert,
keine personenbezogenen Follower-Daten)."""
from __future__ import annotations

from agents.base import Agent


class FollowerAnalyticsAgent(Agent):
    name = "follower_analytics"

    def record(self, platform: str, account: dict) -> None:
        self.memory.add_follower_stats(platform, account.get("followers_count"), account.get("follows_count"),
                                       account.get("media_count"))

    def report(self, platform: str = "instagram") -> dict:
        hist = self.memory.follower_history(platform)
        result: dict = {"platform": platform, "snapshots": len(hist)}
        if hist:
            latest = hist[-1]
            result["followers"] = latest["followers"]
            week = hist[-8] if len(hist) >= 8 else hist[0]
            if latest["followers"] is not None and week["followers"] is not None:
                result["growth"] = latest["followers"] - week["followers"]
        perf = self.memory.latest_performance(platform)
        followers = result.get("followers") or 0
        if perf and followers:
            rates = [((p["likes"] or 0) + (p["comments"] or 0)) / followers for p in perf]
            result["avg_engagement_rate"] = round(sum(rates) / len(rates), 5)
            best = max(perf, key=lambda p: (p["likes"] or 0) + 3 * (p["comments"] or 0))
            result["best_post"] = best["external_id"]
        self.memory.set_insight("audience", f"followers_{platform}", result)
        return result
