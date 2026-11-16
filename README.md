# BürgermeisterBob AI Video Factory

Eine selbstlernende Videofabrik für deutsche TikTok-Videos (9:16, 1080×1920, H.264/AAC, **60–75 s**).
Sie recherchiert Themen, schreibt Skripte, vertont sie und erzeugt Visuals und Untertitel. Danach schneidet
sie das Video, prüft die Qualität, archiviert es und veröffentlicht es nach menschlicher Freigabe auf TikTok.
Sie läuft nativ unter Windows, ohne WSL und ohne Docker; als Datenbank dient SQLite.

> **Grundsatz:** Ohne ausdrückliche Freigabe ist alles kostenlos und lokal. Es entstehen keine API-Kosten,
> es wird nichts veröffentlicht und es werden keine Ergebnisse erfunden.

---

## Inhalt
1. [Stand](#stand)
2. [Schnellstart unter Windows](#schnellstart-unter-windows)
3. [Bedienung](#bedienung)
4. [So entsteht ein Video](#so-entsteht-ein-video)
5. [Videolänge (60–75 s)](#videolänge-6075-s)
6. [Sicherheit & Kosten](#sicherheit--kosten)
7. [Integrationen einrichten](#integrationen-einrichten)
8. [Tägliche Automatisierung](#tägliche-automatisierung)
9. [Gedächtnis & Lernen](#gedächtnis--lernen)
10. [Architektur](#architektur)
11. [Tests](#tests)
12. [Migration auf Ubuntu](#migration-auf-ubuntu)
13. [Bekannte Grenzen](#bekannte-grenzen)

---

## Stand

| Bereich | Status |
|---|---|
| Gedächtnis (SQLite, 14 Tabellen, Migrationen, Backups) | ✅ fertig, getestet |
| Brain Agent + 14 Agenten | ✅ fertig, getestet |
| Recherche (Wikipedia-API, RSS) inkl. Quellenprüfung | ✅ live getestet (kostenlos) |
| Skript mit Längen-Regelkreis auf Basis echter Sprechdauer | ✅ live getestet |
| Deutsche Stimme lokal (Windows „Hedda“), wortgenaue Zeitstempel | ✅ live getestet (kostenlos) |
| Visuals (Motion-Graphics, Kamerafahrten, Wechsel ≤ 4,5 s) | ✅ live getestet |
| Karaoke-Untertitel (Wort für Wort), SRT-Export | ✅ live getestet |
| Qualitätskontrolle (16 Prüfungen) | ✅ live getestet |
| Videobibliothek (Web-Oberfläche) | ✅ API live getestet, Darstellung noch nicht im Browser gesichtet |
| Tagesablauf mit Sperre, Kontingent, Wiederholungen | ✅ live getestet |
| ElevenLabs, OpenAI (Bilder/Text) | ⚙️ implementiert, mit simulierten Antworten getestet; **live erst nach Kostenfreigabe** |
| TikTok Content Posting API + OAuth | ⚙️ implementiert, mit simulierten Antworten getestet; **live erst mit App-Zugang** |
| Instagram Graph API | ⚙️ implementiert, mit simulierten Antworten getestet; **live erst mit Kontozugriff** |
| Higgsfield | ⏸️ bewusst nicht integriert (erst bei Bedarf und nach Kostenfreigabe) |

---

## Schnellstart unter Windows

Voraussetzungen (bereits vorhanden): Python 3.12, FFmpeg im PATH, die deutsche Windows-Stimme
„Microsoft Hedda“ (Windows-Einstellungen → Zeit und Sprache → Sprache → Deutsch → Sprachausgabe).

```powershell
cd C:\buergermeisterbob-ai-video-factory
.\.venv\Scripts\Activate.ps1
# Falls Skripte blockiert sind (einmalig):  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

pip install -r requirements.txt     # alles ist bereits installiert – prüft nur
copy .env.example .env              # optional; ohne .env läuft alles kostenlos

python -m pytest                    # 99 Tests, ca. 50 Sekunden
python -m app.main status           # Systemstatus
python -m app.main serve            # Oberfläche: http://127.0.0.1:8000
```

## Bedienung

**Oberfläche** (`python -m app.main serve` → <http://127.0.0.1:8000>):

- **Neues Video:** mit eigenem Thema, oder ohne Thema, dann wählt Bob selbst eines.
- **Automatische Produktion:** an/aus (steuert den täglichen Lauf).
- **Bibliothek:** ansehen, herunterladen, freigeben, ablehnen, auf TikTok veröffentlichen und den Status sehen.
- Im Ansehen-Fenster stehen Skript, Quellen und alle Prüfergebnisse.

**Kommandozeile:**

```powershell
python -m app.main produce "Erfindung des Telefons"   # Video zu einem Thema
python -m app.main produce                             # Bob wählt selbst
python -m app.main daily --force                       # Tagesablauf jetzt einmal ausführen
python -m app.main backup                              # Gedächtnis sichern
python -m app.main tiktok-auth                         # TikTok-Konto verbinden
```

Alle Ergebnisse liegen in `data\videos\<id>\`: `video.mp4`, `thumbnail.jpg`, `subtitles.srt/.ass`,
`script.json`, `qc.json` und `sources.txt`.

## So entsteht ein Video

| # | Schritt | Agent |
|---|---|---|
| 1 | Thema wählen (Neuheit, gelernte Leistung, Community-Wünsche, Sensibilitätsfilter) | Brain / Strategie |
| 2–3 | Recherche und Quellenprüfung (vertraute Domain, abrufbar, genug Text) | Research |
| 4 | Videoidee und Blickwinkel | Strategie |
| 5 | Mehrere Hooks erzeugen, den besten wählen (≤ 3 s Sprechzeit) | Hook |
| 6–7 | Skript schreiben, Länge planen | Script Writer |
| 8 | Szenenplan und Bildstil je Inhalt (Jahreszahl, Frage, Wendepunkt …) | Video Director |
| 10 | Voice-over je Szene, echte Dauer messen; bei Abweichung zurück zu 6 | Voice |
| 11 | In Shots ≤ 4,5 s mit wechselnder Kamerabewegung teilen | Video Editing |
| 9 | Bilder je Shot erzeugen | Image Generation |
| 13 | Wortgenaue Untertitel | Subtitles |
| 14 | Musik nur mit Lizenzdatei, sonst keine | Video Editing |
| 15 | 9:16-Render, Lautheit auf −14 LUFS normalisiert | Video Editing |
| 16–19 | Länge (ffprobe), Ton, Untertitel und Gesamtprüfung | Quality Control |
| 20 | Archivieren, Zwischendateien löschen | Brain |

Danach entscheidet ein Mensch: **Freigeben** oder **Ablehnen**. Nur freigegebene Videos können veröffentlicht werden.

## Videolänge (60–75 s)

- **Planung:** Zielwörter = 67,5 s × *gemessene* Wörter pro Minute. Die Rate wird aus jeder echten
  Aufnahme gelernt, getrennt pro Stimme und Geschwindigkeit (Hedda bei Rate 2: ca. 134 wpm im ganzen Skript).
- **Messung:** Die tatsächliche Audiodauer entscheidet. Ist das Video unter 60 s, wird das Skript mit weiterem
  verifiziertem Material erweitert; über 80 s wird es gekürzt. Danach folgt eine neue Vertonung (höchstens 3 Überarbeitungen).
- **Kein Strecken:** Reicht das Material nicht, wird das Thema verworfen. Die Qualitätskontrolle lehnt zudem
  Pausen über 1,5 s und Standbilder über 2,5 s ab.
- **Kontrolle:** Die Länge des fertigen Videos wird per ffprobe geprüft. Unter 60 s ist es nicht freigebbar, und
  vor jedem Upload wird die Länge erneut gemessen.
- Ergebnis live: Ein Testvideo war zunächst 83,7 s lang, wurde automatisch gekürzt und kam auf 74,2 s. Das nächste
  traf mit gelernter Rate direkt 70,4 s.

## Sicherheit & Kosten

| Schutz | Umsetzung |
|---|---|
| Keine Kosten ohne Freigabe | `BBOB_ALLOW_PAID_APIS=false`; jeder bezahlte Aufruf läuft über `BudgetGuard` mit Tageslimit und Protokoll |
| Keine Veröffentlichung ohne Freigabe | Status *approved* (Mensch) **und** `BBOB_ALLOW_PUBLISHING=true` **und** TikTok verbunden **und** Länge ≥ 60 s |
| Standardmäßig nur Entwurf | `BBOB_TIKTOK_PUBLISH_MODE=inbox`: Das Video landet als Entwurf in der TikTok-App |
| „Veröffentlicht“ nur mit Beleg | Status wird nur gesetzt, wenn die TikTok-API `PUBLISH_COMPLETE` meldet |
| Zugangsdaten | nur in `.env` (git-ignoriert); in der App als `SecretStr`; in Logs automatisch geschwärzt |
| OAuth-Tokens | mit Windows DPAPI verschlüsselt (`data\secrets\`), an das Benutzerkonto gebunden |
| Oberfläche | bindet nur an 127.0.0.1; andere Adressen nur mit `BBOB_APP_TOKEN`; CSRF-Schutz per Header |
| Datenschutz | Kommentar-Autoren nur als Hash; keine Follower-Einzeldaten; kein Scraping |
| Endlosschleifen | Tageskontingent (Standard 1 Video), max. 3 Skript-Revisionen, 2 Render-Versuche, 1 Netz-Wiederholung |
| Backup | täglich `data\backups\brain-*.db` (SQLite-Backup-API, die letzten 14 bleiben erhalten) |

## Integrationen einrichten

Alle Einträge kommen in `.env` (Vorlage: `.env.example`).

### ElevenLabs (Stimme, kostenpflichtig)
1. `ELEVENLABS_API_KEY` und `ELEVENLABS_VOICE_ID` (eine deutschsprachige Stimme) eintragen.
2. `BBOB_VOICE_PROVIDER=elevenlabs` und `BBOB_ALLOW_PAID_APIS=true` setzen.
   Pro Video entstehen etwa 10–15 Aufrufe, plus Revisionen.

### OpenAI (Bilder/Text, kostenpflichtig)
- Bilder: `OPENAI_API_KEY`, `BBOB_IMAGE_PROVIDER=openai` (ein Bild je Szene, ca. 10–12 pro Video, mit Cache).
- Skripte per Sprachmodell: `BBOB_LLM_PROVIDER=openai`. Das Modell bekommt nur verifizierte Fakten und
  die Anweisung, nichts zu erfinden.
- Modellnamen über `BBOB_OPENAI_IMAGE_MODEL` / `BBOB_OPENAI_TEXT_MODEL`.

### Claude
Claude Code dient zur Entwicklung. Eine Laufzeitanbindung an die Anthropic-API ist **nicht** eingebaut, weil
sie eine eigene Abrechnung erfordert. Der Script Writer ist austauschbar: Eine Anthropic-Anbindung lässt sich
nach Freigabe analog zu `integrations/openai_api.py` ergänzen.

### TikTok (Content Posting API)
1. Auf <https://developers.tiktok.com> eine App anlegen und die Produkte **Login Kit** und **Content Posting API** hinzufügen.
2. Scopes: `user.info.basic`, `video.upload` (Entwurfsmodus) bzw. `video.publish` (Direktmodus), `video.list` (Statistiken).
3. Eine Redirect-URI registrieren. Die Anforderungen an die URI (z. B. HTTPS) im Developer-Portal prüfen.
4. `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI` eintragen.
5. Das Konto verbinden: `python -m app.main tiktok-auth`. Die angezeigte Adresse öffnen und die Weiterleitungsadresse
   einfügen; alternativ <http://127.0.0.1:8000/oauth/tiktok/start>, falls die Redirect-URI auf die lokale App zeigt.
6. `BBOB_ALLOW_PUBLISHING=true` erst setzen, wenn alles getestet ist.
   **Öffentliche** Direktveröffentlichung ist erst nach dem Audit der App durch TikTok möglich, vorher nur `SELF_ONLY`.

### Instagram (Graph API, nur lesend)
Benötigt werden:
- ein **Professional-Konto** (Business/Creator), verknüpft mit einer Facebook-Seite;
- eine Meta-App mit den Berechtigungen `instagram_basic`, `instagram_manage_comments`,
  `instagram_manage_insights`, `pages_show_list` und `pages_read_engagement` (für den Produktivbetrieb mit App-Review);
- ein langlebiges Zugriffstoken `META_ACCESS_TOKEN` und die Konto-ID `INSTAGRAM_USER_ID`.

Ohne diese Angaben überspringt der Tagesablauf Instagram und nennt die fehlenden Punkte.

## Tägliche Automatisierung

```powershell
.\scripts\register_daily_task.ps1            # täglich 08:00 (holt nach, wenn der PC aus war)
.\scripts\unregister_daily_task.ps1          # wieder entfernen
```

Der Lauf tut nur etwas, wenn in der Oberfläche **Automatische Produktion** aktiviert ist. Er umfasst:
Instagram-Daten, Kommentaranalyse, Follower-Bericht, TikTok-Status und -Statistiken, Lernen,
Themenrecherche (inkl. Wünschen aus Kommentaren), Produktion bis zum Tageskontingent, Veröffentlichung
freigegebener Videos (nur wenn erlaubt) und Backup. Fehler eines Schritts stoppen die anderen nicht;
alles wird in `data\logs\factory.log` und in der Datenbank protokolliert.

## Gedächtnis & Lernen

`data\brain.db` speichert Recherche und Quellen, Ideen, Videos samt Skript, Szenen und QC-Bericht,
Hook-Kandidaten, Veröffentlichungen, Performance-Verläufe, Kommentare (kategorisiert), Follower-Zahlen,
Erkenntnisse, Ereignis- und Fehlerprotokoll, Läufe, Einstellungen und API-Nutzung.

**Gelernt wird**, sobald echte Performance-Daten vorliegen. Ohne Daten werden keine Werte erfunden.
- **Sprechrate** je Stimme: schon heute, aus jeder Aufnahme.
- **Leistung je Themenkategorie, Hook-Muster und Längenbereich:** relativ zum Kanal-Median, geglättet.
  Das steuert Themenwahl und Hook-Auswahl, mit einem Anteil Exploration für Neues.
- **Empfehlungen:** welche Kategorien wiederholt und welche gemieden werden sollen.
- **Häufige QC-Fehler:** werden als Erkenntnis gespeichert.

**Stilprofil:** Das Profil ist derzeit eine **Annahme** (`source: default_assumption`), weil der Instagram-Kanal
ohne autorisierten Zugriff nicht ausgewertet wird. Eigene Vorgaben kommen in `data\style_profile.json`, z. B.:

```json
{ "tone": "trocken, schlagfertig", "humor": "Lokalpolitik-Satire ohne Spott über Personen",
  "topics": ["Gemeindeleben", "kuriose Geschichte"], "audience": "25–45, Schweiz" }
```

## Architektur

```
config.py                  Einstellungen (.env, BBOB_*)
core/                      Logging mit Schwärzung, deutsche Textwerkzeuge, Fehlerklassen
storage/database.py        SQLite-Schema, Migrationen, Backup      storage/models.py  Datenmodelle
brain/orchestrator.py      Brain Agent – Pipeline, Freigabe, Veröffentlichung, Status
brain/memory.py            Gedächtnis-API      brain/strategy.py  Stil, Themenwahl, Neuheit, Sensibilität
brain/learning.py          Learning Agent      brain/budget.py    Kostenbremse
agents/                    research, instagram_monitor, comment_analysis, follower_analytics, hook,
                           script_writer, video_director, voice, image_generation, video_editing,
                           subtitles, quality_control, tiktok_publisher
video_engine/              ffmpeg, duration (Längenrichtlinie), visuals, scenes (Kamerafahrten),
                           audio, subtitles (ASS/SRT), renderer, quality_check (Analyse)
integrations/              http, wikipedia, rss, windows_tts (+ scripts/sapi_tts.ps1),
                           elevenlabs_api, openai_api, instagram, tiktok, token_store (DPAPI)
workflows/daily_workflow.py   Tagesablauf
app/main.py, app/api.py, app/static/index.html   Oberfläche und CLI
scripts/                   Windows-Aufgabenplanung
```

## Tests

```powershell
python -m pytest            # 99 Tests
```

- **Echte** Tests ohne Kosten: Windows-Stimme, FFmpeg-Rendering und -Analyse, kompletter Ablauf von der
  Recherche bis zur (simulierten) TikTok-Bestätigung, Datenbank, Backup und DPAPI.
- **Simuliert** (keine Netzwerkzugriffe): Wikipedia, TikTok, Instagram, OpenAI, ElevenLabs.
- Tests nutzen temporäre Verzeichnisse und berühren `data\` nicht.

## Migration auf Ubuntu

- Python-Code, SQLite und FFmpeg sind plattformunabhängig.
- **Stimme:** Die Windows-Stimme fällt weg, also `BBOB_VOICE_PROVIDER=elevenlabs` setzen (oder einen lokalen
  TTS-Anbieter ergänzen).
- **Schriften:** `BBOB_FONTS_DIR=/usr/share/fonts/truetype/...` und passende Schriftdateien
  (`BBOB_DISPLAY_FONT`, `BBOB_BOLD_FONT`).
- **Tokens:** werden unter Linux mit Dateirechten 0600 statt DPAPI gespeichert. Für den Server einen
  Secret-Manager vorsehen.
- **Zeitplan:** cron oder ein systemd-Timer mit `python -m workflows.daily_workflow`.
- **Datenbank:** das SQL ist bewusst einfach gehalten, ein späterer Umzug auf PostgreSQL ist direkt möglich.

## Bekannte Grenzen

- **Skriptqualität offline:** Der kostenlose Autor setzt verifizierte Lexikonsätze plus Bobs Moderation zusammen.
  Das ist faktentreu, aber sprachlich hölzern und nicht witzig. Für wirklich unterhaltsame Skripte braucht es ein
  Sprachmodell (OpenAI hier eingebaut, Anthropic nach Freigabe).
- **Windows-Stimme:** verständlich, aber hörbar synthetisch. Für eine professionelle Stimme ElevenLabs verwenden.
- **Visuals offline:** Typo-/Motion-Graphics-Karten, keine echten Bildmotive. Für Bilder OpenAI aktivieren.
- **Wikipedia-Texte** stehen unter CC BY-SA. Die Quellen werden in der Beschreibung genannt; für eigenständige
  Formulierungen ein Sprachmodell nutzen.
- **TikTok/Instagram** sind noch nicht live getestet (fehlende Zugänge).
- **Absturz während einer Produktion:** Beim nächsten Start werden hängende Produktionen (älter als 1 h) als
  fehlgeschlagen markiert.
