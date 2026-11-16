import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from core.errors import ExternalApiError, NotConfiguredError, PaidApiNotAllowedError
from integrations.elevenlabs_api import ElevenLabsTTS, words_from_alignment
from integrations.http import make_client, request
from integrations.instagram import InstagramGraph
from integrations.openai_api import OpenAIService
from integrations.rss import parse_feed
from integrations.tiktok import TikTokClient, chunk_plan
from integrations.token_store import TokenStore
from integrations.wikipedia import WikipediaClient
from brain.budget import BudgetGuard
from tests.conftest import IS_WINDOWS, make_settings
from tests.fakes import LONG_TEXT, json_response, wiki_transport


# --- HTTP ------------------------------------------------------------------------------
def test_request_retries_then_succeeds(settings):
    seen = []

    def handler(req):
        seen.append(1)
        return httpx.Response(503) if len(seen) < 3 else httpx.Response(200, text="ok")
    client = make_client(settings, httpx.MockTransport(handler))
    resp = request(client, "GET", "https://example.org/x?access_token=geheim", retries=2, sleep=lambda s: None)
    assert resp.status_code == 200 and len(seen) == 3


def test_request_gives_up_after_limit(settings):
    client = make_client(settings, httpx.MockTransport(lambda r: httpx.Response(500)))
    assert request(client, "GET", "https://example.org", retries=1, sleep=lambda s: None).status_code == 500


# --- Wikipedia / RSS ---------------------------------------------------------------------
def test_wikipedia_article_and_search(settings):
    client = make_client(settings, wiki_transport({"Laufmaschine": LONG_TEXT}))
    wiki = WikipediaClient(settings, client)
    assert wiki.search("Laufmaschine") == ["Laufmaschine"]
    art = wiki.article("Laufmaschine")
    assert art["url"].startswith("https://de.wikipedia.org/") and "Karl Drais" in art["extract"]
    assert wiki.article("Gibtsnicht") is None


def test_wikipedia_onthisday_parsing(settings):
    events = [{"year": 1969, "text": "Testereignis (mit Klammer) passiert.", "pages": [
        {"titles": {"normalized": "Testseite"}, "content_urls": {"desktop": {"page": "https://de.wikipedia.org/wiki/Testseite"}},
         "extract": "Ein Auszug."}]}]
    from datetime import date
    wiki = WikipediaClient(settings, make_client(settings, wiki_transport({}, events)))
    ev = wiki.on_this_day(date(2026, 7, 20))
    assert ev[0]["text"] == "Testereignis passiert." and ev[0]["pages"][0]["title"] == "Testseite"


def test_rss_and_atom_parsing():
    rss = """<rss><channel><item><title>Neu</title><link>https://www.tagesschau.de/a</link>
             <description>&lt;p&gt;Text&lt;/p&gt;</description><pubDate>Mon</pubDate></item></channel></rss>"""
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title><link href="https://srf.ch/x"/>
              <summary>S</summary><updated>2026</updated></entry></feed>"""
    assert parse_feed(rss)[0] == {"title": "Neu", "url": "https://www.tagesschau.de/a", "summary": "Text", "published_at": "Mon"}
    assert parse_feed(atom)[0]["url"] == "https://srf.ch/x"


# --- Token-Speicher ---------------------------------------------------------------------
def test_token_store_roundtrip_is_not_plaintext(tmp_path):
    store = TokenStore(tmp_path)
    store.save("tiktok", {"access_token": "act.SUPERGEHEIM", "expires_at": 1})
    raw = (tmp_path / "tiktok.token").read_bytes()
    if IS_WINDOWS:
        assert b"SUPERGEHEIM" not in raw and raw.startswith(b"DPAPI1")
    assert store.load("tiktok")["access_token"] == "act.SUPERGEHEIM"
    assert store.delete("tiktok") and store.load("tiktok") is None


# --- Kostenpflichtige Dienste: blockiert ohne Freigabe ------------------------------------------
class FakeOpenAI:
    def __init__(self):
        self.calls = 0
        png = base64.b64encode(b"\x89PNG fake").decode()
        self.images = SimpleNamespace(generate=self._gen)
        self._png = png

    def _gen(self, **kw):
        self.calls += 1
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self._png)])


def test_openai_requires_key_and_permission(tmp_path, memory):
    s = make_settings(tmp_path)
    with pytest.raises(NotConfiguredError):
        OpenAIService(s, BudgetGuard(s, memory))
    svc = OpenAIService(s, BudgetGuard(s, memory), client=FakeOpenAI())
    with pytest.raises(PaidApiNotAllowedError):
        svc.generate_image("Prompt", tmp_path / "x.png")


def test_openai_image_cache_avoids_double_cost(tmp_path, memory):
    s = make_settings(tmp_path, allow_paid_apis=True)
    fake = FakeOpenAI()
    svc = OpenAIService(s, BudgetGuard(s, memory), client=fake)
    svc.generate_image("Gleicher Prompt", tmp_path / "a.png")
    svc.generate_image("Gleicher Prompt", tmp_path / "b.png")
    assert fake.calls == 1 and memory.paid_calls_today() == 1
    assert (tmp_path / "b.png").read_bytes().startswith(b"\x89PNG")


def test_elevenlabs_blocked_without_permission(tmp_path, memory):
    s = make_settings(tmp_path)
    with pytest.raises(NotConfiguredError):
        ElevenLabsTTS(s, BudgetGuard(s, memory))
    tts = ElevenLabsTTS(s, BudgetGuard(s, memory), client=object())
    with pytest.raises(PaidApiNotAllowedError):
        tts.synthesize_batch([("Hallo Welt", tmp_path / "a.wav")])


def test_elevenlabs_alignment_to_words():
    chars = list("Hallo, Welt!")
    starts = [i * 0.1 for i in range(len(chars))]
    ends = [s + 0.1 for s in starts]
    ws = words_from_alignment(chars, starts, ends)
    assert [w.word for w in ws] == ["Hallo", "Welt"]
    assert ws[0].start == 0.0 and ws[1].start == pytest.approx(0.7)


# --- Instagram -----------------------------------------------------------------------------
def test_instagram_not_configured(settings):
    g = InstagramGraph(settings, make_client(settings))
    assert "META_ACCESS_TOKEN" in g.missing_requirements()
    with pytest.raises(NotConfiguredError):
        g.account()


def test_instagram_graph_calls_and_tolerant_insights(tmp_path):
    s = make_settings(tmp_path, meta_access_token="EAAG-test", instagram_user_id="17841")

    def handler(req: httpx.Request):
        assert req.url.params.get("access_token") == "EAAG-test"
        p = req.url.path
        if p.endswith("/17841"):
            return json_response({"username": "bob", "followers_count": 1200, "media_count": 40})
        if p.endswith("/17841/media"):
            return json_response({"data": [{"id": "m1", "like_count": 50, "comments_count": 2}]})
        if p.endswith("/m1/comments"):
            return json_response({"data": [{"id": "c1", "text": "Super!", "username": "anna"}]})
        if p.endswith("/m1/insights"):
            metric = req.url.params["metric"]
            if metric == "views":
                return json_response({"error": {"message": "unsupported metric", "code": 100}}, 400)
            return json_response({"data": [{"name": metric, "values": [{"value": 7}]}]})
        return json_response({"error": {"message": "nope"}}, 404)
    g = InstagramGraph(s, make_client(s, httpx.MockTransport(handler)))
    assert g.account()["followers_count"] == 1200
    assert g.comments("m1")[0]["text"] == "Super!"
    assert g.media_insights("m1") == {"reach": 7, "saved": 7, "shares": 7}


# --- TikTok --------------------------------------------------------------------------------
def tiktok_settings(tmp_path, **kw):
    return make_settings(tmp_path, tiktok_client_key="ck", tiktok_client_secret="cs",
                         tiktok_redirect_uri="https://example.org/cb", **kw)


def test_chunk_plan():
    assert chunk_plan(1000) == (1000, 1)
    size = 150 * 1024 * 1024
    chunk, count = chunk_plan(size)
    assert chunk == 10 * 1024 * 1024 and count == 15
    with pytest.raises(ValueError):
        chunk_plan(0)


def test_tiktok_oauth_and_refresh(tmp_path):
    s = tiktok_settings(tmp_path)
    store = TokenStore(tmp_path / "sec")
    now = [1000.0]
    bodies = []

    def handler(req):
        body = dict(httpx.QueryParams(req.content.decode()))
        bodies.append(body)
        return json_response({"access_token": f"act-{len(bodies)}", "refresh_token": "rft", "expires_in": 86400,
                              "refresh_expires_in": 31536000, "open_id": "o1", "scope": "video.upload"})
    c = TikTokClient(s, store, make_client(s, httpx.MockTransport(handler)), clock=lambda: now[0])
    url, state = c.authorize_url()
    assert "client_key=ck" in url and f"state={state}" in url and "video.upload" in url
    assert not c.connected
    c.exchange_code("CODE")
    assert c.connected and bodies[0]["grant_type"] == "authorization_code"
    assert c.access_token() == "act-1"
    now[0] += 86400  # abgelaufen -> Refresh
    assert c.access_token() == "act-2" and bodies[1]["grant_type"] == "refresh_token"


def test_tiktok_inbox_upload_and_status(tmp_path):
    s = tiktok_settings(tmp_path)
    store = TokenStore(tmp_path / "sec")
    store.save("tiktok", {"access_token": "act", "refresh_token": "r", "expires_at": 9e12, "refresh_expires_at": 9e12})
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1234)
    seen = {}

    def handler(req):
        if req.url.path == "/v2/post/publish/inbox/video/init/":
            seen["init"] = json.loads(req.content)
            assert req.headers["authorization"] == "Bearer act"
            return json_response({"data": {"publish_id": "p1", "upload_url": "https://upload.example/u"},
                                  "error": {"code": "ok"}})
        if req.url.host == "upload.example":
            seen["range"] = req.headers["content-range"]
            return httpx.Response(201)
        if req.url.path == "/v2/post/publish/status/fetch/":
            return json_response({"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})
        return json_response({"error": {"code": "not_found"}}, 404)
    c = TikTokClient(s, store, make_client(s, httpx.MockTransport(handler)))
    init = c.init_upload(video, "inbox")
    assert seen["init"]["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1234, "chunk_size": 1234,
                                           "total_chunk_count": 1}
    c.upload_file(init["upload_url"], video)
    assert seen["range"] == "bytes 0-1233/1234"
    assert c.fetch_status("p1")["status"] == "SEND_TO_USER_INBOX"


def test_tiktok_api_error_is_raised(tmp_path):
    s = tiktok_settings(tmp_path)
    store = TokenStore(tmp_path / "sec")
    store.save("tiktok", {"access_token": "act", "expires_at": 9e12, "refresh_expires_at": 9e12})
    c = TikTokClient(s, store, make_client(s, httpx.MockTransport(lambda r: json_response(
        {"error": {"code": "spam_risk_too_many_posts", "message": "Zu viele Beiträge"}}, 403))))
    with pytest.raises(ExternalApiError) as exc:
        c.creator_info()
    assert exc.value.code == "spam_risk_too_many_posts"


def test_tiktok_not_configured(settings):
    c = TikTokClient(settings, TokenStore(settings.secrets_dir), make_client(settings))
    assert "TIKTOK_CLIENT_KEY" in c.missing_requirements()
    with pytest.raises(NotConfiguredError):
        c.authorize_url()
