"""Simulierte HTTP-Antworten für Tests (keine Netzwerkzugriffe, keine Kosten).

Die Testtexte sind eigens formulierte Testdaten im Stil eines Lexikonartikels.
"""
from __future__ import annotations

import json

import httpx

LONG_TEXT = (
    "Die Laufmaschine ist ein einspuriges, von Menschenkraft betriebenes Fahrzeug ohne Pedale. "
    "Karl Drais stellte sie im Jahr 1817 in Mannheim vor. "
    "Bei der ersten bekannten Ausfahrt im Juni 1817 fuhr er von Mannheim in Richtung Schwetzingen. "
    "Der Fahrer sass zwischen zwei hintereinander angeordneten Rädern und stiess sich mit den Füssen vom Boden ab. "
    "Auf ebener Strecke war die Laufmaschine deutlich schneller als ein Fussgänger. "
    "Das Gestell der ersten Modelle bestand überwiegend aus Holz. "
    "Gelenkt wurde über das Vorderrad mit einer einfachen Lenkstange. "
    "Drais erhielt im Jahr 1818 ein badisches Privileg für seine Erfindung. "
    "Die Idee verbreitete sich rasch in andere Länder, etwa nach Frankreich und England. "
    "In England wurden die Geräte unter dem Namen Hobby Horse bekannt. "
    "Manche Städte verboten das Fahren auf Gehwegen, weil es immer wieder zu Zusammenstössen kam. "
    "Die Laufmaschine gilt als wichtiger Vorläufer des heutigen Fahrrads. "
    "Erst Jahrzehnte später kamen Tretkurbeln am Vorderrad hinzu. "
    "Heute erinnern Museen und originalgetreue Nachbauten an die Erfindung aus Mannheim. "
    "Viele Kinder lernen das Gleichgewicht auf Laufrädern, die nach demselben Prinzip funktionieren. "
    "Damit lebt die Grundidee der Laufmaschine bis heute in fast jedem Kinderzimmer weiter."
)

SHORT_TEXT = ("Der Testweiler ist ein sehr kleiner Ort mit einer einzigen Strasse und einem alten Brunnen am Dorfplatz. "
              "Er wurde im Jahr 1850 erstmals in einer Urkunde erwähnt und hat heute nur wenige Einwohner.")


def wiki_transport(articles: dict[str, str], onthisday: list[dict] | None = None, calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        q = dict(request.url.params)
        if "onthisday" in request.url.path:
            return httpx.Response(200, json={"events": onthisday or []})
        if q.get("list") == "search":
            term = q.get("srsearch", "").lower()
            hits = [t for t in articles if any(w in t.lower() for w in term.split())] or list(articles)[:1]
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in hits]}})
        if q.get("prop", "").startswith("extracts"):
            title = q.get("titles", "")
            if title not in articles:
                return httpx.Response(200, json={"query": {"pages": {"-1": {"title": title, "missing": ""}}}})
            return httpx.Response(200, json={"query": {"pages": {"1": {
                "title": title, "extract": articles[title],
                "fullurl": f"https://de.wikipedia.org/wiki/{title.replace(' ', '_')}"}}}})
        return httpx.Response(404, text="unbekannt")
    return httpx.MockTransport(handler)


def json_response(data: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(data).encode(), headers={"content-type": "application/json"})
