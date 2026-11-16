"""Stilprofil von Bürgermeister Bob – getrennt nach gesicherten Beobachtungen und Annahmen.

Grundlage: EINMALIGER Abruf der öffentlichen Instagram-Profilseite ohne Anmeldung am 16.11.2026
(kein automatisiertes Scraping). Sichtbar waren nur Profilname, Bio, gerundete Followerzahl,
Ausschnitte von Beitragstexten und Hashtags – KEINE Videoinhalte (Bild, Ton, Schnitt).
Alles, was nicht sichtbar war, steht unter "nicht_feststellbar" bzw. "annahmen".
"""

STYLE_PROFILE = {
    "version": 1,
    "erstellt": "2026-11-16",
    "quelle": "https://www.instagram.com/buergermeisterbob/ – öffentliche Profilseite, einmaliger Abruf ohne Anmeldung",
    "bestaetigt": False,
    "gesichert": {
        "profilname": "Bürgermeister Bob",
        "handle": "buergermeisterbob",
        "bio": "Jeder Follower = 1 Einwohner + 1.000 € für Bobstadt 🏡 Ihr entscheidet, was gebaut wird.",
        "follower": "13.4K (gerundet, Stand 16.11.2026)",
        "folgt": 0,
        "konzept": "Community-Aufbausimulation: Follower werden Einwohner der fiktiven Stadt Bobstadt, jeder bringt "
                   "1.000 € ins Stadtbudget, die Community entscheidet, was gebaut wird.",
        "beitragsart": "Clips (als 'Clip' gekennzeichnete Videos)",
        "hashtags": ["#citybuilder", "#isometric", "#animation", "#bobstadt", "#bürgermeisterbob", "stadtbau", "gaming"],
        "wiederkehrende_formate": [
            "Meilensteine der Einwohnerzahl ('10.000 Einwohner!', 'Ihr habt es geschafft: 12.500!')",
            "Neue Gebäude und Einrichtungen (1. FC Bobstadt, Krankenhaus mit Rettungshubschrauber, Bahnhof, Wohntürme)",
            "Finanzierungslücken als Spannungsbogen ('Fürs Krankenhaus fehlen 1,3 Mio. €' – schaffen wir das?)",
            "Mitbestimmung: Namensvorschläge für ein neues Viertel, Entscheidung was als Nächstes gebaut wird",
            "Kommentar-Wettbewerbe (bester Kommentar gewinnt, z. B. einen Döner am Stadion)",
            "Anerkennung einzelner Community-Mitglieder (Ehrenpräsidentschaft)",
        ],
        "ansprache": "direkte Ansprache der Community im Plural ('Ihr habt es geschafft', 'Ihr entscheidet')",
        "zahlen": "konkrete Zahlen zu Einwohnern und Euro-Beträgen stehen im Mittelpunkt",
    },
    "nicht_feststellbar": [
        "Sprecher/Stimme und ob es überhaupt ein Voice-over gibt",
        "Schnittstil, Tempo, Länge der Clips",
        "Musik und Soundeffekte",
        "genaues Aussehen der isometrischen Animation (nur Hashtags sichtbar)",
        "Humor im gesprochenen Wort",
        "Alter, Region und Zusammensetzung der Zielgruppe",
        "Anzahl der Beiträge, Reichweite und Engagement-Werte",
    ],
    "annahmen": {
        "persona": "Bürgermeister Bob spricht als Stadtoberhaupt in der Ich-Form, nahbar und stolz auf 'seine' Einwohner",
        "tone": "begeistert, gemeinschaftlich, leicht augenzwinkernd; feiert Erfolge, macht Spannung bei Geldlücken",
        "humor": "Situationskomik rund um Stadtleben und Bauprojekte; kein Spott über Personen",
        "language": "Hochdeutsch, kurze Sätze, Ihr/Du-Ansprache, gut sprechbar",
        "narrative": "Hook mit Zahl/Ereignis -> Stand der Stadt -> Entscheidung/Bau/Lücke -> Wissen -> Aufruf zum Kommentieren",
        "topics": ["Bauprojekte", "Meilensteine", "Stadtkasse", "Abstimmungen", "Viertel und Namen", "Community"],
        "audience": "Follower, die Aufbauspiele und Mitbestimmung mögen (Annahme aus #citybuilder/#gaming)",
        "visual_style": "isometrische Stadtansicht, kräftige Farben, Zahlen gross im Bild",
        "editing_style": "Bildwechsel alle 3–5 Sekunden, Wort-für-Wort-Untertitel, keine Pausen",
        "recurring_elements": ["Einwohnerzahl und Stadtkasse im Bild", "Abschlussfrage an die Community",
                               "'Ihr entscheidet'-Mechanik"],
    },
    "hinweis": "Bitte prüfen und ergänzen. Mit \"bestaetigt\": true werden die Annahmen als bestätigt behandelt.",
}
