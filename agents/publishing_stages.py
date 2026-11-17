"""The five publishing stages – each one only counts when it is actually proven.

1 generated          a rendered video file exists
2 validated          all technical, visual and continuity checks passed
3 approved           the user personally approved the video
4 uploaded           TikTok CONFIRMED the upload (status fetch: SEND_TO_USER_INBOX or PUBLISH_COMPLETE)
5 published          TikTok confirmed PUBLISH_COMPLETE for a post whose visibility is PUBLIC_TO_EVERYONE

Our own HTTP upload request succeeding is NOT stage 4 – only TikTok's status report is.
"""
from __future__ import annotations

from pathlib import Path

UPLOAD_CONFIRMED = {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}
PUBLIC = "PUBLIC_TO_EVERYONE"

LABELS = {
    "generated": "Video erzeugt",
    "validated": "Technisch geprüft",
    "approved": "Von dir freigegeben",
    "uploaded": "Bei TikTok hochgeladen (bestätigt)",
    "published": "Öffentlich veröffentlicht (bestätigt)",
}


def stages(video: dict, publications: list[dict]) -> list[dict]:
    qc = video.get("qc") or {}
    has_file = bool(video.get("video_path")) and Path(video["video_path"]).is_file()
    validated = has_file and qc.get("passed") is True and video["status"] not in ("qc_failed", "failed")
    approved = validated and bool(video.get("approved_at")) and video["status"] not in ("rejected",)
    confirmed = [p for p in publications if p.get("platform_status") in UPLOAD_CONFIRMED and p.get("confirmed_at")]
    public = [p for p in confirmed if p.get("public_confirmed_at")]
    out = [
        {"key": "generated", "done": has_file, "at": video.get("created_at") if has_file else None},
        {"key": "validated", "done": validated,
         "detail": None if validated else ("Prüfung nicht bestanden" if qc.get("passed") is False else "noch nicht geprüft")},
        {"key": "approved", "done": approved, "at": video.get("approved_at")},
        {"key": "uploaded", "done": bool(confirmed), "at": confirmed[-1]["confirmed_at"] if confirmed else None,
         "detail": (confirmed[-1]["platform_status"] if confirmed else
                    ("Upload gesendet – TikTok-Bestätigung ausstehend" if publications else None))},
        {"key": "published", "done": bool(public), "at": public[-1]["public_confirmed_at"] if public else None,
         "detail": None if public else ("hochgeladen, aber nicht öffentlich" if confirmed else None)},
    ]
    for s in out:
        s["label"] = LABELS[s["key"]]
    return out


def current_stage(video: dict, publications: list[dict]) -> str:
    done = [s["key"] for s in stages(video, publications) if s["done"]]
    return done[-1] if done else "none"
