"""Instagram Monitor Agent: liest autorisierte Instagram-Daten (Konto, Beiträge, Kommentare, Insights)
über die offizielle Graph API und legt sie im Gedächtnis ab."""
from __future__ import annotations

from agents.base import Agent, AgentContext
from agents.follower_analytics import FollowerAnalyticsAgent
from core.errors import ExternalApiError
from integrations.instagram import REQUIRED_PERMISSIONS, InstagramGraph


class InstagramMonitorAgent(Agent):
    name = "instagram_monitor"

    def __init__(self, ctx: AgentContext, graph: InstagramGraph | None = None,
                 followers: FollowerAnalyticsAgent | None = None):
        super().__init__(ctx)
        self.graph = graph or InstagramGraph(ctx.settings, ctx.http)
        self.followers = followers or FollowerAnalyticsAgent(ctx)

    def run(self, max_media: int = 10) -> dict:
        missing = self.graph.missing_requirements()
        if missing:
            self.event("info", "Instagram nicht eingerichtet – übersprungen. Fehlt: " + ", ".join(missing))
            return {"status": "not_configured", "missing": missing, "required_permissions": REQUIRED_PERMISSIONS}
        account = self.graph.account()
        self.followers.record("instagram", account)
        new_comments, media_count = 0, 0
        for m in self.graph.media(limit=max_media):
            media_count += 1
            try:
                insights = self.graph.media_insights(m["id"])
            except ExternalApiError as exc:
                insights = {}
                self.event("warning", f"Insights für {m['id']} nicht verfügbar: {exc}")
            self.memory.add_performance("instagram", m["id"], views=insights.get("views"), likes=m.get("like_count"),
                                        comments=m.get("comments_count"), shares=insights.get("shares"),
                                        saves=insights.get("saved"), reach=insights.get("reach"))
            for c in self.graph.comments(m["id"]):
                if self.memory.upsert_comment("instagram", c["id"], c.get("text", ""), m["id"], c.get("username"),
                                              c.get("like_count"), c.get("timestamp")):
                    new_comments += 1
        result = {"status": "ok", "followers": account.get("followers_count"), "media": media_count,
                  "new_comments": new_comments}
        self.event("info", f"Instagram: {media_count} Beiträge, {new_comments} neue Kommentare")
        return result
