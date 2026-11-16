"""Script Writer Agent: schreibt vollständige Skripte anhand der tatsächlichen Sprechgeschwindigkeit.

Längenplanung: Zielwörter = Zieldauer × gemessene Wörter pro Minute (gelernt aus echten Audiodateien;
Startwert 150 wpm). Zu kurz -> erweitern mit weiterem VERIFIZIERTEM Material, zu lang -> kürzen.
Reicht das Material nicht, wird das Thema verworfen – es wird NIE mit Füllsätzen oder Pausen gestreckt.

Anbieter:
- offline (Standard): baut das Skript aus verifizierten Recherche-Sätzen und Bobs Moderation.
  Kostenlos, faktentreu, aber sprachlich weniger kreativ als ein Sprachmodell.
- openai: Sprachmodell formuliert das Skript ausschliesslich aus den gelieferten Fakten (kostenpflichtig).
"""
from __future__ import annotations

import random

from agents.base import Agent, AgentContext
from core.errors import ExternalApiError, InsufficientMaterialError
from core.text import normalize_space, word_count
from storage.models import HookCandidate, Idea, Script, ScriptSegment, StyleProfile

DEFAULT_WPM = 150.0
MAX_SENTENCE_WORDS = 28

# ohne Artikel vor {title}, damit jede Titelform grammatisch passt
INTROS = ["Ich bin Bürgermeister Bob, und unser Thema heute lautet: {title}.",
          "Bürgermeister Bob hier. Heute auf meinem Schreibtisch: {title}.",
          "Hier ist Bob, euer Bürgermeister. Heute: {title}."]
EPISODE_INTROS = ["Hier ist Bob, euer Bürgermeister – und es gibt Neuigkeiten aus Bobstadt.",
                  "Bürgermeister Bob hier, mit frischen Nachrichten aus dem Rathaus von Bobstadt.",
                  "Willkommen zurück in Bobstadt, hier spricht euer Bürgermeister Bob."]
TURNS = ["Und jetzt wird es spannend.", "Aber das ist noch nicht alles.",
         "Jetzt kommt der Teil, den kaum jemand kennt.", "Und genau hier wird es interessant."]
TAKEAWAYS = ["Was lernen wir daraus? Grosse Veränderungen beginnen oft mit einer einzigen Idee.",
             "Für mich als Bürgermeister zeigt das: Geschichte passiert nicht irgendwo, sondern mitten unter uns.",
             "Mein Fazit als Bürgermeister: Hinter jeder Schlagzeile stecken Menschen mit Mut und Ideen.",
             "Und die Moral von der Geschichte? Neugier lohnt sich – immer."]
CTAS = ["Hättest du das gewusst? Schreib es in die Kommentare und folge Bob für mehr Geschichten.",
        "Welche Geschichte soll ich als Nächstes erzählen? Schreib es mir in die Kommentare!",
        "Was meinst du dazu? Ab in die Kommentare damit – und folge Bob für mehr."]


INTERESTING = ("erste", "ersten", "erfand", "erfunden", "erfindung", "entdeck", "rekord", "ungewöhnlich",
               "überrasch", "berühmt", "grösste", "größte", "einzige", "weltweit", "kurios", "erstmals", "legendär",
               "sensation", "geschwindigkeit", "kilometer", "stunde", "verbot", "spott", "patent", "durchbruch")
TRIVIA = ("mutter", "vater", "sohn", "tochter", "geboren", "heiratete", "taufe", "pate", "patenschaft", "schule",
          "schulisch", "gymnasium", "studierte", "beigesetzt", "ehe", "bruder", "schwester", "familie")


def rank_sentences(sentences: list[str], topic: str) -> list[str]:
    """Wählt relevante, interessante Sätze zuerst – Ausgabe in Originalreihenfolge (Chronologie bleibt)."""
    from core.text import keyword_set
    topic_kw = keyword_set(topic)
    scored = []
    for i, s in enumerate(sentences):
        low, kw = s.lower(), keyword_set(s)
        score = 3.0 * len(kw & topic_kw) + sum(1.5 for m in INTERESTING if m in low) \
            - sum(1.5 for t in TRIVIA if t in low)
        n = word_count(s)
        score += 1.0 if 8 <= n <= 24 else 0.0
        score += 0.5 if any(ch.isdigit() for ch in s) else 0.0
        score -= i * 0.05  # frühe (einleitende) Sätze leicht bevorzugen
        scored.append((score, i, s))
    return [s for _, _, s in sorted(scored, key=lambda x: (-x[0], x[1]))]


def usable_sentences(material: list[str]) -> list[str]:
    out = []
    for s in material:
        s = normalize_space(s)
        if not s or s.endswith(":"):
            continue
        parts = [p.strip() for p in s.split(";")] if word_count(s) > MAX_SENTENCE_WORDS else [s]
        for p in parts:
            n = word_count(p)
            if 4 <= n <= MAX_SENTENCE_WORDS:
                out.append(p if p[-1] in ".!?" else p + ".")
    return out


class ScriptWriterAgent(Agent):
    name = "script_writer"

    def __init__(self, ctx: AgentContext, llm=None):
        super().__init__(ctx)
        self.llm = llm  # OpenAIService oder None

    @property
    def provider(self) -> str:
        return "openai" if self.llm is not None else "offline"

    def speech_rate(self, voice_provider: str) -> float:
        stats = self.memory.get_insight("speech_rate", voice_provider) or {}
        return float(stats.get("wpm", DEFAULT_WPM))

    def target_words(self, voice_provider: str, seconds: float | None = None) -> int:
        seconds = seconds or self.s.target_duration_s
        return int(round(seconds * self.speech_rate(voice_provider) / 60.0))

    # --- Schreiben ------------------------------------------------------------------
    def write(self, idea: Idea, material: list[str], hook: HookCandidate, target_words: int,
              style: StyleProfile, seed: str | None = None) -> Script:
        sentences = usable_sentences(material)
        if not sentences:
            raise InsufficientMaterialError(f"Keine verwertbaren, verifizierten Sätze zu '{idea.title}'")
        if self.llm is not None:
            try:
                return self._write_llm(idea, sentences, hook, target_words, style)
            except ExternalApiError as exc:
                self.event("warning", f"Sprachmodell fehlgeschlagen, verwende Offline-Autor: {exc}")
        return self._write_offline(idea, sentences, hook, target_words, seed or idea.title)

    def _frame(self, idea: Idea, hook: HookCandidate, rng: random.Random) -> dict[str, str]:
        return {"hook": hook.text, "intro": rng.choice(INTROS).format(title=idea.title),
                "turn": rng.choice(TURNS), "takeaway": rng.choice(TAKEAWAYS), "cta": rng.choice(CTAS)}

    def _assemble(self, idea: Idea, frame: dict[str, str], story: list[str], hook_pattern: str, revision: int) -> Script:
        split = max(1, round(len(story) * 0.45))
        segs = [ScriptSegment(role="hook", text=frame["hook"]), ScriptSegment(role="intro", text=frame["intro"])]
        segs += [ScriptSegment(role="story", text=s) for s in story[:split]]
        if len(story) > split:
            segs.append(ScriptSegment(role="turn", text=frame["turn"]))
            segs += [ScriptSegment(role="story", text=s) for s in story[split:]]
        segs += [ScriptSegment(role="takeaway", text=frame["takeaway"]), ScriptSegment(role="cta", text=frame["cta"])]
        return Script(title=idea.title, segments=segs, provider="offline", hook_pattern=hook_pattern, revision=revision)

    def _write_offline(self, idea: Idea, sentences: list[str], hook: HookCandidate, target_words: int, seed: str) -> Script:
        frame = self._frame(idea, hook, random.Random(seed))
        fixed = sum(word_count(v) for v in frame.values())
        chosen, words = set(), fixed
        for s in rank_sentences(sentences, f"{idea.title} {idea.angle}"):
            if words >= target_words:
                break
            chosen.add(s)
            words += word_count(s)
        story = [s for s in sentences if s in chosen]  # Originalreihenfolge
        return self._assemble(idea, frame, story, hook.pattern, 0)

    def _story(self, script: Script) -> list[str]:
        return [s.text for s in script.segments if s.role == "story"]

    def _replace_story(self, script: Script, story: list[str]) -> Script:
        """Ersetzt nur die austauschbaren Faktensätze (role=story); Handlung, Hook und Abschluss bleiben.
        Liegt ein Wendepunkt (turn) zwischen Faktensätzen, wird er wieder nach ca. 45 % eingefügt."""
        segs = script.segments
        idx = [i for i, s in enumerate(segs) if s.role == "story"]
        turn_i = next((i for i, s in enumerate(segs) if s.role == "turn"), None)
        if not idx:
            anchor = next((i for i, s in enumerate(segs) if s.role in ("takeaway", "cta")), len(segs))
            pre, post, mid_turn = segs[:anchor], segs[anchor:], None
        else:
            mid_turn = segs[turn_i] if turn_i is not None and idx[0] < turn_i < idx[-1] else None
            pre = [s for i, s in enumerate(segs[:idx[0]])]
            post = [s for s in segs[idx[-1] + 1:]]
        facts = [ScriptSegment(role="story", text=t) for t in story]
        if not facts and pre and pre[-1].role == "turn":
            pre = pre[:-1]  # keine Überleitung ohne folgendes Wissen
        if mid_turn is not None and len(facts) > 1:
            split = max(1, round(len(facts) * 0.45))
            facts = facts[:split] + [mid_turn] + facts[split:]
        elif not idx and facts and not any(s.role == "turn" for s in pre):
            facts = [ScriptSegment(role="turn", text=TURNS[0])] + facts
        return script.model_copy(update={"segments": pre + facts + post, "revision": script.revision + 1})

    def expand(self, script: Script, idea: Idea, material: list[str], extra_words: int) -> Script:
        """Ergänzt weitere verifizierte Sätze; wirft InsufficientMaterialError, wenn nichts mehr da ist."""
        story = self._story(script)
        all_sentences = usable_sentences(material)
        unused = [s for s in rank_sentences(all_sentences, f"{idea.title} {idea.angle}") if s not in story]
        added, n = set(), 0
        for s in unused:
            if n >= extra_words:
                break
            added.add(s)
            n += word_count(s)
        if not added:
            raise InsufficientMaterialError(f"Kein weiteres verifiziertes Material für '{idea.title}' – Thema reicht "
                                            f"nicht für {self.s.min_duration_s:.0f} Sekunden")
        ordered = [s for s in all_sentences if s in added or s in story] + [s for s in story if s not in all_sentences]
        return self._replace_story(script, ordered)

    def shorten(self, script: Script, idea: Idea, excess_words: int) -> Script:
        story = self._story(script)
        removed = 0
        keep_min = 2 if not any(s.role == "plot" for s in script.segments) else 0
        for s in reversed(rank_sentences(story, f"{idea.title} {idea.angle}")):
            if len(story) <= keep_min or removed >= excess_words:
                break
            story.remove(s)
            removed += word_count(s)
        return self._replace_story(script, story)

    # --- Bobstadt-Episoden ---------------------------------------------------------
    def write_episode(self, episode, material: list[str], hook: HookCandidate, target_words: int,
                      seed: str | None = None) -> Script:
        """Handlung mit echten Zahlen aus dem Stadtzustand + verifizierte Fakten als Wissensteil."""
        rng = random.Random(seed or episode.title)
        intro = rng.choice(EPISODE_INTROS)
        segs = [ScriptSegment(role="hook", text=hook.text), ScriptSegment(role="intro", text=intro)]
        segs += [ScriptSegment(role="plot", text=pl.text, visual=pl.visual, data=pl.data) for pl in episode.plot]
        fixed = sum(word_count(s.text) for s in segs) + word_count(episode.takeaway) + word_count(episode.cta)
        sentences = usable_sentences(material)
        story, words = [], fixed + word_count(episode.fact_intro)
        chosen = set()
        for s in rank_sentences(sentences, " ".join(episode.fact_topics) + " " + (episode.building_name or "")):
            if words >= target_words:
                break
            chosen.add(s)
            words += word_count(s)
        story = [s for s in sentences if s in chosen]
        if story:
            segs.append(ScriptSegment(role="turn", text=episode.fact_intro))
            segs += [ScriptSegment(role="story", text=s) for s in story]
        segs += [ScriptSegment(role="takeaway", text=episode.takeaway), ScriptSegment(role="cta", text=episode.cta)]
        return Script(title=episode.title, segments=segs, provider="offline-episode", hook_pattern=hook.pattern)

    # --- Sprachmodell (optional, kostenpflichtig) --------------------------------
    def _write_llm(self, idea: Idea, sentences: list[str], hook: HookCandidate, target_words: int,
                   style: StyleProfile) -> Script:
        system = ("Du schreibst gesprochene deutsche TikTok-Skripte für die Figur Bürgermeister Bob. "
                  f"Stil: {style.tone}. Humor: {style.humor}. Sprache: {style.language}. Aufbau: {style.narrative}. "
                  "Verwende AUSSCHLIESSLICH Fakten aus der Faktenliste. Erfinde nichts. Keine Regieanweisungen, "
                  "keine Emojis, keine Hashtags. Antworte als JSON.")
        facts = "\n".join(f"- {s}" for s in sentences[:40])
        user = (f"Thema: {idea.title}\nBlickwinkel: {idea.angle}\nHook (wörtlich als erster Satz): {hook.text}\n"
                f"Gesamtlänge: {target_words} Wörter (±5 %).\nFakten:\n{facts}\n\n"
                'Format: {"segments": [{"role": "hook|intro|story|turn|takeaway|cta", "text": "..."}]} '
                "Reihenfolge: hook, intro, mehrere story, turn, story, takeaway, cta.")
        data = self.llm.complete_json(system, user)
        segs = [ScriptSegment(role=s["role"], text=normalize_space(s["text"])) for s in data.get("segments", [])
                if s.get("role") in {"hook", "intro", "story", "turn", "takeaway", "cta"} and s.get("text")]
        if not segs or segs[0].role != "hook" or not any(s.role == "story" for s in segs):
            raise ExternalApiError("openai", "Skript-Antwort unvollständig")
        if word_count(segs[0].text) > 12:
            segs[0] = ScriptSegment(role="hook", text=hook.text)
        return Script(title=idea.title, segments=segs, provider="openai", hook_pattern=hook.pattern)
