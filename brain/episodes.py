"""Episodenplanung für Bobstadt – welche Folge ist als Nächstes dran?

Formate (abgeleitet aus den öffentlich sichtbaren Beiträgen):
  meilenstein     Einwohner-Schwelle erreicht ("10.000 Einwohner!")
  bau             Gebäude wird gebaut (Community-Wunsch oder Bobs Wahl)
  finanzierung    Wunsch zu teuer – es fehlt Geld ("Fürs Krankenhaus fehlen 1,3 Mio. €")
  abstimmung      Community soll entscheiden, was gebaut wird
  namenswahl      Ein Name fürs neue Viertel wird gesucht bzw. verkündet

Jede Folge enthält feste Handlungssätze (mit echten Zahlen aus dem Stadtzustand) und ein Thema für
echte, verifizierte Hintergrundfakten (Wikipedia), die den Wissensteil liefern.
Die Wirkung (z. B. Bau) wird erst bei der FREIGABE des Videos in den Stadtzustand übernommen.
"""
from __future__ import annotations

import random

from pydantic import BaseModel, Field

from brain.city import City, CityState, fmt_eur, fmt_int
from brain.memory import Memory

def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


EPISODE_TYPES = ("meilenstein", "bau", "finanzierung", "abstimmung", "namenswahl")


class PlotLine(BaseModel):
    text: str
    visual: str = "city"       # city | build | cost | funding | vote | milestone | keyword
    data: dict = Field(default_factory=dict)


class Episode(BaseModel):
    type: str
    title: str
    hook_vars: dict = Field(default_factory=dict)
    plot: list[PlotLine]
    takeaway: str
    cta: str
    fact_topics: list[str] = Field(default_factory=list)   # Wikipedia-Artikel für den Wissensteil
    fact_intro: str = "Und jetzt noch ein bisschen Wissen für echte Bürgermeister."
    building: str | None = None         # Katalogschlüssel
    building_name: str | None = None
    options: list[str] = Field(default_factory=list)
    effects: dict = Field(default_factory=dict)
    city: dict = Field(default_factory=dict)   # Zustand zum Produktionszeitpunkt (für Grafik und Nachvollziehbarkeit)
    confirmed_state: bool = False


class EpisodePlanner:
    def __init__(self, city: City, memory: Memory, rng: random.Random | None = None):
        self.city, self.memory = city, memory
        self.rng = rng or random.Random()

    def _snapshot(self, st: CityState, highlight: str | None = None) -> dict:
        return {"residents": st.residents, "budget_eur": st.budget_eur, "available_eur": st.available_eur,
                "buildings": [{"kind": b["kind"], "name": b["name"], "status": b["status"]} for b in st.buildings],
                "highlight": highlight}

    def recent_types(self, n: int = 3) -> list[str]:
        out = []
        for v in self.memory.list_videos(limit=20):
            if v.get("episode") and v["status"] not in ("failed", "rejected"):
                out.append(v["episode"]["type"])
        return out[:n]

    # --- Auswahl ----------------------------------------------------------------------
    def plan(self, wish: str | None = None) -> Episode | None:
        st = self.city.state()
        if st.residents is None:
            return None
        if wish:
            b = self.city.match_building(wish)
            if b is None:
                return None
            return self.bau(st, b, votes=0) if b.cost_eur <= st.available_eur else self.finanzierung(st, b)
        recent = self.recent_types()
        last_ms = int(self.memory.get_setting("city.last_milestone", 0))
        reached = (st.residents // 500) * 500
        if reached > last_ms and "meilenstein" not in recent[:1]:
            return self.meilenstein(st, reached, last_ms)
        names = [p for p in self.memory.proposals("name") if p["votes"] >= 3]
        if names and "namenswahl" not in recent:
            return self.namenswahl(st, names[:3])
        wish_hit = self.city.top_building_wish(st)
        if wish_hit:
            b, votes = wish_hit
            if b.cost_eur <= st.available_eur:
                return self.bau(st, b, votes)
            if "finanzierung" not in recent[:1]:
                return self.finanzierung(st, b, votes)
        affordable = self.city.affordable(st)
        if "abstimmung" not in recent[:1] and len(affordable) >= 3:
            return self.abstimmung(st, affordable)
        if affordable:
            return self.bau(st, self.rng.choice(affordable[-5:]), votes=0)
        unbuilt = sorted(self.city.unbuilt(st), key=lambda b: b.cost_eur)
        return self.finanzierung(st, unbuilt[0]) if unbuilt else None

    # --- Formate ----------------------------------------------------------------------
    def bau(self, st: CityState, b, votes: int) -> Episode:
        remaining = st.available_eur - b.cost_eur
        built = [x for x in st.buildings if x["status"] == "built"]
        decided = (f"Ihr habt abgestimmt, und das Ergebnis ist eindeutig: {fmt_int(votes)} von euch wollen {b.acc}."
                   if votes else f"Heute entscheide ich als Bürgermeister selbst: Wir bauen {b.acc}!")
        plot = [
            PlotLine(text=decided, visual="vote_result" if votes else "keyword", data={"keyword": b.name}),
            PlotLine(text=f"Bobstadt hat inzwischen {fmt_int(st.residents)} Einwohner, und in der Stadtkasse liegen "
                          f"{fmt_eur(st.available_eur)}.", visual="city"),
            PlotLine(text=f"{cap(b.nom)} kostet {fmt_eur(b.cost_eur)}. Das können wir uns leisten!",
                     visual="cost", data={"name": b.name, "cost": b.cost_eur}),
            PlotLine(text="Also: Bagger an, Kräne hoch – die Baustelle ist eröffnet.", visual="build"),
            PlotLine(text=(f"{cap(b.nom)} bekommt einen Platz mitten in Bobstadt – mit Blick auf "
                           f"{len(built)} Gebäude, die ihr schon gebaut habt." if built else
                           f"{cap(b.nom)} bekommt einen Platz mitten in der Stadt."), visual="city"),
            PlotLine(text=f"Nach dem Bau bleiben noch {fmt_eur(remaining)} in der Kasse.", visual="funding",
                     data={"have": max(0, remaining), "need": st.available_eur, "label": "Kasse nach dem Bau"}),
        ]
        return Episode(type="bau", title=f"Bobstadt baut: {b.name}", hook_vars={"nom": b.nom, "acc": b.acc, "name": b.name},
                       plot=plot, building=b.key, building_name=b.name, fact_topics=[b.wiki],
                       takeaway="Jeder neue Follower bringt einen Einwohner und tausend Euro – so wächst Bobstadt weiter.",
                       cta="Was soll als Nächstes gebaut werden? Schreib es in die Kommentare!",
                       effects={"build": b.key, "name": b.name, "cost": b.cost_eur, "votes": votes},
                       city=self._snapshot(st, b.key), confirmed_state=st.confirmed)

    def finanzierung(self, st: CityState, b, votes: int = 0) -> Episode:
        gap = b.cost_eur - st.available_eur
        needed = self.city.followers_needed(gap)
        plot = [
            PlotLine(text=(f"{fmt_int(votes)} von euch wünschen sich {b.acc}." if votes else
                           f"Viele träumen von {b.dat}."), visual="keyword", data={"keyword": b.name}),
            PlotLine(text=f"Das Problem: {cap(b.nom)} kostet {fmt_eur(b.cost_eur)}.", visual="cost",
                     data={"name": b.name, "cost": b.cost_eur}),
            PlotLine(text=f"In der Stadtkasse liegen aber nur {fmt_eur(max(0, st.available_eur))}.", visual="funding",
                     data={"have": max(0, st.available_eur), "need": b.cost_eur, "label": b.name}),
            PlotLine(text=f"Es fehlen also noch {fmt_eur(gap)}. Das sind genau {fmt_int(needed)} neue Einwohner.",
                     visual="funding", data={"have": max(0, st.available_eur), "need": b.cost_eur, "label": b.name}),
            PlotLine(text=f"Bobstadt hat gerade {fmt_int(st.residents)} Einwohner. Mit "
                          f"{fmt_int(st.residents + needed)} können die Bagger anrollen.", visual="city"),
        ]
        return Episode(type="finanzierung", title=f"Fürs {b.name} fehlt Geld" if b.article == "das" else
                       f"Für {b.acc} fehlt Geld", hook_vars={"nom": b.nom, "acc": b.acc, "name": b.name,
                                                               "gap": fmt_eur(gap)},
                       plot=plot, building=b.key, building_name=b.name, fact_topics=[b.wiki],
                       takeaway="Jeder neue Follower ist ein neuer Einwohner und tausend Euro für die Stadtkasse.",
                       cta=f"Schaffen wir die {fmt_int(needed)}? Schreib in die Kommentare, wen du nach Bobstadt holst!",
                       effects={}, city=self._snapshot(st, None), confirmed_state=st.confirmed)

    def abstimmung(self, st: CityState, affordable: list) -> Episode:
        options = self.rng.sample(affordable, 3)
        plot = [PlotLine(text=f"Die Stadtkasse ist voll: {fmt_eur(st.available_eur)} warten darauf, verbaut zu werden.",
                         visual="city"),
                PlotLine(text="Ich habe drei Vorschläge – und ihr entscheidet.", visual="vote",
                         data={"options": [{"name": o.name, "cost": o.cost_eur} for o in options]})]
        for label, o in zip("ABC", options):
            plot.append(PlotLine(text=f"Option {label}: {o.nom}, für {fmt_eur(o.cost_eur)}.", visual="cost",
                                 data={"name": o.name, "cost": o.cost_eur, "label": label}))
        names = ", ".join(o.name for o in options[:2]) + f" oder {options[2].name}"
        return Episode(type="abstimmung", title="Ihr entscheidet: Was baut Bobstadt?", hook_vars={},
                       plot=plot, options=[o.key for o in options], fact_topics=[o.wiki for o in options],
                       fact_intro="Damit ihr gut entscheiden könnt, hier ein paar echte Fakten.",
                       takeaway="Die meisten Stimmen gewinnen – und Bob baut, sobald das Ergebnis feststeht.",
                       cta=f"{names}? Schreib deinen Favoriten in die Kommentare!",
                       city=self._snapshot(st, None), confirmed_state=st.confirmed)

    def meilenstein(self, st: CityState, reached: int, last: int) -> Episode:
        top = self.city.affordable(st)[-2:]
        plot = [PlotLine(text=f"Bobstadt hat die Marke von {fmt_int(reached)} Einwohnern geknackt!", visual="milestone",
                         data={"number": fmt_int(reached)}),
                PlotLine(text=f"Seit dem letzten Meilenstein sind {fmt_int(st.residents - last)} Menschen zu uns gezogen.",
                         visual="city"),
                PlotLine(text=f"Jeder davon bringt tausend Euro mit – die Stadtkasse hat jetzt {fmt_eur(st.available_eur)}.",
                         visual="funding", data={"have": max(0, st.available_eur), "need": max(1, st.budget_eur),
                                                 "label": "Stadtkasse"})]
        if top:
            plot.append(PlotLine(text="Damit wären jetzt sogar Projekte wie " +
                                      " oder ".join(b.nom for b in top) + " drin.", visual="city"))
        return Episode(type="meilenstein", title=f"{fmt_int(reached)} Einwohner!", hook_vars={"n": fmt_int(reached)},
                       plot=plot, fact_topics=["Kleinstadt"],
                       takeaway="Danke an alle Einwohner – ohne euch gäbe es Bobstadt nicht.",
                       cta="Was bauen wir mit dem neuen Geld? Schreib es in die Kommentare!",
                       effects={"milestone": reached}, city=self._snapshot(st, None), confirmed_state=st.confirmed)

    def namenswahl(self, st: CityState, names: list[dict]) -> Episode:
        winner = names[0]
        plot = [PlotLine(text="Ihr erinnert euch: Das neue Viertel von Bobstadt brauchte einen Namen.", visual="city"),
                PlotLine(text="Die meistgenannten Vorschläge: " + ", ".join(n["value"] for n in names) + ".",
                         visual="vote", data={"options": [{"name": n["value"], "cost": None} for n in names]}),
                PlotLine(text=f"Und gewonnen hat: {winner['value']} – mit {fmt_int(winner['votes'])} Stimmen!",
                         visual="keyword", data={"keyword": winner["value"]})]
        return Episode(type="namenswahl", title=f"Das neue Viertel heißt {winner['value']}",
                       hook_vars={"name": winner["value"]}, plot=plot, fact_topics=["Stadtteil"],
                       takeaway="Ab heute steht der Name auf jedem Ortsschild im Viertel.",
                       cta="Welches Gebäude soll als Erstes ins neue Viertel? Ab in die Kommentare!",
                       effects={"name": winner["value"]}, city=self._snapshot(st, None), confirmed_state=st.confirmed)
