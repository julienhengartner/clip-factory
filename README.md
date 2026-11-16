# Bobbington – AI Video Factory

**Bobbington – *A Town Full of Bad Decisions.*** Eine animierte 3D-Comedy-Serie in britischem Englisch über
Mayor Winston Boggle und seine Stadt. Die Fabrik schreibt bzw. generiert Folgen, vertont jede Figur mit eigener
Stimme, animiert die Figuren in Blender, mischt Ton und Untertitel, prüft die Qualität (60–75 s, 9:16,
1080×1920, H.264/AAC) und veröffentlicht nach Freigabe auf TikTok. Darunter läuft eine fiktive Stadtsimulation.

Codebasis: <https://github.com/julienhengartner/clip-factory>. Läuft nativ unter Windows (ohne WSL und ohne
Docker), mit SQLite als Gedächtnis. Alle verwendeten Werkzeuge sind kostenlos.

> **Grundsatz:** Ohne ausdrückliche Freigabe ist alles kostenlos und lokal. Es entstehen keine API-Kosten,
> es wird nichts veröffentlicht und es werden keine Ergebnisse erfunden.

## Bobbington (aktuelle Richtung)

| Bereich | Stand |
|---|---|
| Serien-Bibel (`docs/bible/README.md`, Quelle `bobbington/bible.py`) | ✅ Marke, Palette, Stadtgeschichte, Traditionen, 6 Figuren mit Biografie, Aussehen, Stimme, Beziehungen |
| Stadtidentität `assets/brand/` | ✅ Logo, Wappen („Ex Errore Gloria“), Flagge als SVG |
| 3D-Figuren (Blender 4.5 LTS, prozedural, mit Armature-Rig) | ✅ alle 6 Figuren, Referenzbild `docs/bible/cast_lineup.jpg` |
| Sets | ✅ Büro des Bürgermeisters, Ratssaal, Main Street, Pub „The Leaning Pickle“, Titelkarte |
| Figurenanimation | ✅ Lippensynchronität aus der Stimme, Blinzeln, Atmen, Blickwechsel, 16 Gesten, Mimik je Emotion |
| Kamera | ✅ Totale, Zwei-Personen-Einstellung, Nahaufnahme, Push-in, Schärfentiefe |
| Stimmen (Piper, offline) | ✅ britische Stimmen, je Figur unterschiedlich (Lizenzen siehe unten) |
| Ton | ✅ Titelfanfare, Sting, 8 Soundeffekte – selbst erzeugt, lizenzfrei |
| Pilot „THE MAYOR BANS MONDAYS!“ | ✅ Drehbuch, ca. 74 s; Render siehe „Produktion“ |
| Episodengenerator | ✅ 3 weitere Prämissen; wählt passend zur Simulation, keine Wiederholung |
| Stadtsimulation | ✅ 2.450 Einwohner, £1.000.000 (fiktiv), Abteilungen, Hauptbuch mit Prüfung, Projekte, Betriebe, Beschwerden, Abstimmungen |

**Produktion einer Folge:**

```powershell
python -m bobbington.production episodes\pilot_mayor_bans_mondays.json --quality draft   # ~25 min, 540x960 hochskaliert
python -m bobbington.production episodes\pilot_mayor_bans_mondays.json --quality final   # ~1–1,5 h, 1080x1920
python -m bobbington.docs                     # Bibel und Markendateien neu erzeugen
blender -b --factory-startup -P blender\reference_sheet.py -- docs\bible\cast_lineup.png   # Besetzungsbild
```

Das fertige Video erscheint in der Videobibliothek (`python -m app.main serve`). „Neues Video“ erzeugt im
Bobbington-Modus die nächste Folge, zuerst den Piloten. Erst die **Freigabe** schreibt die Folgen einer Episode
(Kosten, Beschwerden, Projekte) ins Hauptbuch der Stadt.

**Einmalige Einrichtung (kostenlos):**
- Blender 4.5 LTS portabel nach `C:\Tools\blender-4.5.16-windows-x64\` (Pfad: `BBOB_BLENDER_BIN`)
- `pip install piper-tts==1.3.0` (in der venv; GPL-3.0, wird nur als eigenständiges Programm aufgerufen)
- Piper-Stimmen nach `C:\Tools\piper-voices\` (Pfad: `BBOB_PIPER_VOICES_DIR`) aus
  <https://huggingface.co/rhasspy/piper-voices>: `en_GB-northern_english_male-medium`, `en_GB-vctk-medium`,
  `en_GB-alba-medium`, `en_GB-cori-medium` (jeweils `.onnx` + `.onnx.json`)

**Stimmlizenzen** (werden in `credits.txt` und in der TikTok-Beschreibung genannt): northern_english_male –
OpenSLR 83, CC BY-SA 4.0 · vctk – University of Edinburgh, CC BY 4.0 · alba – University of Edinburgh, CC BY 4.0 ·
cori – LibriVox, Public Domain. Nicht verwendet: `semaine` (nur nicht kommerziell), `alan` und `jenny_dioco`
(Lizenz unklar).

**Ehrliche Einordnung der Qualität:** Die Figuren sind schlichte, aus Grundformen aufgebaute 3D-Cartoonfiguren
mit Rig, und die Animation ist echte Rig-Animation (keine Kamerafahrt über Standbilder). Das ist eine
funktionierende Produktionspipeline, aber noch nicht das Niveau detailliert modellierter Studio-Figuren mit
Gesichts-Rigs. Die Bewegungen sind keyframe-basiert und eher steif, und die Piper-Stimmen klingen synthetisch.
Der nächste Qualitätssprung wären handmodellierte Figuren in Blender (gleiche Rig-Namen, dann funktioniert die
Animation weiter) und bessere Stimmen, was kostenpflichtig wäre und nur nach Freigabe in Frage kommt.

Die früheren Modi **Bobstadt** (`BBOB_CONTENT_MODE=bobstadt`) und **Wissen** (`wissen`) bleiben verfügbar und
sind unten beschrieben.

---

## Inhalt
1. [Stand](#stand)
2. [Schnellstart unter Windows](#schnellstart-unter-windows)
3. [Bedienung](#bedienung)
4. [Bobstadt-Modus](#bobstadt-modus)
5. [So entsteht ein Video](#so-entsteht-ein-video)
6. [Videolänge (60–75 s)](#videolänge-6075-s)
7. [Sicherheit & Kosten](#sicherheit--kosten)
8. [Integrationen einrichten](#integrationen-einrichten)
9. [Tägliche Automatisierung](#tägliche-automatisierung)
10. [Gedächtnis & Lernen](#gedächtnis--lernen)
11. [Architektur](#architektur)
12. [Tests](#tests)
13. [Migration auf Ubuntu](#migration-auf-ubuntu)
14. [Bekannte Grenzen](#bekannte-grenzen)
15. [GitHub](#github)

---

## Stand

| Bereich | Status |
|---|---|
| Gedächtnis (SQLite, 16 Tabellen, Migrationen, Backups) | ✅ fertig, getestet |
| **Bobstadt:** Stadtzustand, Kommentar-Stimmen, Episodenplanung | ✅ live getestet (Startbestand **unbestätigt**) |
| **Isometrische Stadtgrafik** mit Bau-Animation (kostenlos) | ✅ live getestet |
| Stilprofil `data/style_profile.json` (Beobachtung vs. Annahme) | ✅ angelegt, **bitte prüfen** |
| Geplante Veröffentlichungszeit | ✅ getestet (Veröffentlichung selbst erst nach TikTok-Einrichtung) |
| Brain Agent + 14 Agenten | ✅ fertig, getestet |
| Recherche (Wikipedia-API, RSS) inkl. Quellenprüfung | ✅ live getestet (kostenlos) |
| Skript mit Längen-Regelkreis auf Basis echter Sprechdauer | ✅ live getestet |
| Deutsche Stimme lokal (Windows „Hedda“), wortgenaue Zeitstempel | ✅ live getestet (kostenlos) |
| Visuals (Motion-Graphics, Kamerafahrten, Wechsel ≤ 4,5 s) | ✅ live getestet |
| Karaoke-Untertitel (Wort für Wort), SRT-Export | ✅ live getestet |
| Qualitätskontrolle (17 Prüfungen) | ✅ live getestet |
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

python -m pytest                    # 115 Tests, ca. 80 Sekunden
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
python -m app.main city                                # Bobstadt-Stand anzeigen
python -m app.main city --einwohner 13512 --bestaetigen   # Stand pflegen/bestätigen
python -m app.main publish-due                         # geplante, fällige Videos veröffentlichen
python -m app.main tiktok-auth                         # TikTok-Konto verbinden
```

Alle Ergebnisse liegen in `data\videos\<id>\`: `video.mp4`, `thumbnail.jpg`, `subtitles.srt/.ass`,
`script.json`, `qc.json` und `sources.txt`.

## Bobstadt-Modus

Standard ist `BBOB_CONTENT_MODE=bobstadt`. Mit `wissen` erzeugt die Fabrik stattdessen Wissensvideos aus recherchierten Themen.

**Spielregel** (öffentlich in der Bio beobachtet): Einwohner = Follower, Budget = Follower × 1.000 €,
Kasse = Budget − Ausgaben. Die Einwohnerzahl kommt aus der Instagram-API, sobald diese eingerichtet ist;
bis dahin aus deiner Eingabe (`city --einwohner`).

**Episoden**, aus den öffentlich sichtbaren Beitragstexten abgeleitet:

| Folge | Wann | Wirkung nach Freigabe |
|---|---|---|
| Meilenstein | neue 500er-Marke erreicht | Meilenstein gilt als gefeiert |
| Bau | Wunsch mit ≥ 2 Stimmen und bezahlbar, oder ein Gebäude per Thema im Eingabefeld | Gebäude wird gebaut, Kasse sinkt |
| Finanzierungslücke | Wunsch ist zu teuer | rechnet vor, wie viele neue Einwohner fehlen |
| Abstimmung | keine klaren Wünsche | Community wählt aus drei bezahlbaren Optionen |
| Namenswahl | Namensvorschläge mit ≥ 3 Stimmen | Viertel bekommt den Namen |

**Stimmen** kommen aus Kommentaren: eine Stimme pro Person (Autor nur als Hash), Spam ausgeschlossen.
Gebäudewünsche werden über Schlüsselwörter aus dem Katalog erkannt, Namen über Muster wie `Name: „Sonnenhang“`.

**Wichtig:** Der Startbestand (13.400 Einwohner; Stadion, Döner, Krankenhaus, Bahnhof, Wohntürme) stammt aus
öffentlich sichtbaren Beitragstexten. Die **Gebäudepreise sind Spieldesign-Annahmen**. Bis du den Stand
bestätigst, warnt die Qualitätskontrolle bei jedem Video: „Zahlen vor Freigabe prüfen“.

```powershell
python -m app.main city --einwohner 13512             # echte Followerzahl
python -m app.main city --ausgaben-korrektur 250000    # Kasse an echte Kanalzahlen angleichen
python -m app.main city --bestaetigen                  # Startbestand bestätigen
```

Preise und Gebäude lassen sich in `data\city_catalog.json` überschreiben, z. B.
`[{"key": "freibad", "cost_eur": 1800000}]`.

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

**Stilprofil** (`data\style_profile.json`): Es wurde aus einem **einmaligen Abruf der öffentlichen
Profilseite ohne Anmeldung** angelegt; ein Scraping von Videos oder Followern findet nicht statt. Die Datei trennt:
- `gesichert`: Bio, Followerzahl (gerundet), Hashtags, wiederkehrende Formate aus Beitragstexten;
- `nicht_feststellbar`: Stimme, Schnitt, Musik, Videolänge, Zielgruppe (ohne Videozugriff nicht sichtbar);
- `annahmen`: Tonfall, Humor und Bildstil. Daraus leitet die Fabrik die Vorgaben ab.

Bitte die Annahmen prüfen und anpassen, dann `"bestaetigt": true` setzen. Die Datei wird nie überschrieben.

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
python -m pytest            # 115 Tests
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

- **Bobstadt-Zahlen:** Startbestand und Gebäudepreise sind unbestätigt bzw. angenommen (siehe oben).
- **Grafik:** Die isometrische Stadt ist eine schlichte, kostenlose Eigenproduktion und keine Kopie der Kanal-Animation,
  deren genaues Aussehen ohne Videozugriff nicht bekannt ist.
- **Planen:** Die TikTok-API bietet keine eigene Terminplanung. Die Fabrik veröffentlicht zum geplanten Zeitpunkt
  selbst, solange die Oberfläche läuft (Prüfung alle 5 Minuten), oder per `python -m app.main publish-due`.

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

## GitHub

- Repository: <https://github.com/julienhengartner/clip-factory> (**öffentlich**)
- Commits laufen unter der GitHub-Noreply-Adresse (`git config user.email` nur für dieses Repository),
  damit keine private E-Mail-Adresse öffentlich wird.
- Nie im Repository: `.env`, `data\` (Gedächtnis, Videos, Logs, Backups, Tokens), `*.token`,
  `.claude/settings.local.json`, Musikdateien.
- Erster Push bzw. Anmeldung: `git push -u origin main`. Git Credential Manager öffnet dabei die GitHub-Anmeldung im Browser.
