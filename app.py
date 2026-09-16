"""
Public site + TikTok OAuth callback for the "Data Science, End to End" content project.

Runs as a single Render Web Service. It serves the pages TikTok requires for app review
(a real landing page, Terms of Service, Privacy Policy) AND the OAuth redirect target, all
on Render's own HTTPS domain — no Vercel, no custom domain needed:

    https://<your-service>.onrender.com/            landing
    https://<your-service>.onrender.com/terms       Terms of Service
    https://<your-service>.onrender.com/privacy     Privacy Policy
    https://<your-service>.onrender.com/tiktok/callback   <- register THIS as the Redirect URI

The callback finishes the OAuth automatically when TIKTOK_CLIENT_KEY/SECRET are set: it
exchanges the ?code= for a refresh token and writes it to TIKTOK_STATE_DIR (the mounted disk),
so the poster picks it up with no copy-paste. If the secrets are not set, it just shows the
code so you can paste it into the CLI `--authorize` flow.

Env:
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET   (from developers.tiktok.com)
  TIKTOK_REDIRECT_URI                        this exact callback URL
  TIKTOK_STATE_DIR                           where to persist the token (Render disk, e.g. /data)
  TIKTOK_VERIFY_META                         optional: TikTok domain-verification meta content
"""
from __future__ import annotations
import os
import json
import time
import datetime as _dt
from pathlib import Path

import requests
from flask import Flask, render_template, request, send_from_directory, abort, jsonify

app = Flask(__name__)

BRAND = "Data Science, End to End"
AUTHOR = "Archit Sharma"
CONTACT = "archits1996@gmail.com"
BOOK_URL = "https://architsh.vercel.app/book"
YT = "https://www.youtube.com/@intuitionfirstds"
UPDATED = "September 16, 2026"

TT_API = "https://open.tiktokapis.com"
CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "")
STATE_DIR = Path(os.getenv("TIKTOK_STATE_DIR", "/tmp/tiktok-state"))  # /data when a disk is mounted
VERIFY_META = os.getenv("TIKTOK_VERIFY_META", "")  # TikTok domain-verification <meta> content
WELL_KNOWN = Path(__file__).resolve().parent / "well_known"


def ctx(**kw):
    base = dict(brand=BRAND, author=AUTHOR, contact=CONTACT, book_url=BOOK_URL,
                youtube=YT, updated=UPDATED, verify_meta=VERIFY_META,
                year=_dt.date.today().year)
    base.update(kw)
    return base


@app.route("/")
def index():
    return render_template("index.html", **ctx())


@app.route("/terms")
def terms():
    return render_template("terms.html", **ctx())


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", **ctx())


@app.route("/healthz")
def healthz():
    return {"ok": True}, 200


@app.route("/tiktok/callback")
def tiktok_callback():
    """OAuth redirect target. Auto-exchanges the code when app secrets are present."""
    err = request.args.get("error")
    if err:
        return render_template("callback.html", **ctx(
            status="error", detail=request.args.get("error_description", err)))

    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code:
        return render_template("callback.html", **ctx(
            status="error", detail="No authorization code was returned."))

    # If we can, finish the exchange server-side and persist the token — no copy-paste needed.
    if CLIENT_KEY and CLIENT_SECRET and REDIRECT_URI:
        # Send the code EXACTLY as received (Flask has already URL-decoded it once). TikTok v2 codes
        # legitimately contain '*' and end in a region tag like '.e1' — do NOT truncate. As a safety
        # net, if the full code is rejected we retry with the pre-'*' portion; a wrong variant does not
        # consume a valid single-use code, so trying both on one code is safe.
        variants = [code] + ([code.split("*")[0]] if "*" in code else [])
        detail = "No response from TikTok's token endpoint."
        for cand in variants:
            try:
                tok = requests.post(f"{TT_API}/v2/oauth/token/", data={
                    "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
                    "grant_type": "authorization_code", "code": cand,
                    "redirect_uri": REDIRECT_URI}, timeout=30).json()
            except Exception as e:  # noqa: BLE001
                detail = f"Token exchange request failed: {e}"
                continue
            if "refresh_token" in tok:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                (STATE_DIR / "tiktok_token.json").write_text(json.dumps(tok, indent=2))
                return render_template("callback.html", **ctx(status="stored", state=state))
            detail = f"TikTok rejected the code: {tok.get('error_description', tok.get('error', tok))}"
        return render_template("callback.html", **ctx(status="error", detail=detail, code=code, state=state))

    # No secrets on this instance — show the code for the CLI paste flow.
    return render_template("callback.html", **ctx(status="code", code=code, state=state))


# --------------------------------------------------------------------------- #
# TEMPORARY test-post endpoint — proves the TikTok pipeline end-to-end from the
# US Render box (where the token lives). Key-gated (X-Test-Key == client secret).
# Remove after testing. Posts a bundled 1080x1920 clip; SELF_ONLY (private) via
# Direct Post, falling back to an inbox draft if the sandbox app can't Direct Post.
# --------------------------------------------------------------------------- #
TEST_VIDEO = Path(__file__).resolve().parent / "test_clip.mp4"


def _tt_access_token() -> str:
    saved = json.loads((STATE_DIR / "tiktok_token.json").read_text())
    r = requests.post(f"{TT_API}/v2/oauth/token/", data={
        "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": saved["refresh_token"]}, timeout=30).json()
    if "access_token" not in r:
        raise RuntimeError(f"token refresh failed: {r}")
    if r.get("refresh_token"):
        saved.update(r)
        (STATE_DIR / "tiktok_token.json").write_text(json.dumps(saved, indent=2))
    return r["access_token"]


def _tt_upload(hdr: dict, init_url: str, payload: dict) -> dict:
    size = TEST_VIDEO.stat().st_size
    init = requests.post(init_url, headers=hdr, json=payload, timeout=60).json()
    data = init.get("data") or {}
    upload_url, publish_id = data.get("upload_url"), data.get("publish_id")
    if not upload_url:
        return {"ok": False, "init": init}
    put = requests.put(upload_url, data=TEST_VIDEO.read_bytes(), timeout=300, headers={
        "Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if put.status_code not in (200, 201, 206):
        return {"ok": False, "init": init, "upload_http": put.status_code, "upload_text": put.text[:200]}
    final = None
    for _ in range(20):
        final = requests.post(f"{TT_API}/v2/post/publish/status/fetch/", headers=hdr,
                              json={"publish_id": publish_id}, timeout=30).json().get("data", {})
        if final.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED", "DROPPED"):
            break
        time.sleep(3)
    ok = bool(final) and final.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX")
    return {"ok": ok, "publish_id": publish_id, "final": final, "init": init}


@app.route("/tiktok/test-post", methods=["POST"])
def tiktok_test_post():
    if not CLIENT_SECRET or request.headers.get("X-Test-Key") != CLIENT_SECRET:
        abort(403)
    if not (STATE_DIR / "tiktok_token.json").exists():
        return jsonify(ok=False, error="No stored token — re-authorize first."), 400
    if not TEST_VIDEO.exists():
        return jsonify(ok=False, error="test_clip.mp4 not deployed"), 500
    try:
        at = _tt_access_token()
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, step="token", error=str(e)), 500
    hdr = {"Authorization": f"Bearer {at}", "Content-Type": "application/json; charset=UTF-8"}
    ci = requests.post(f"{TT_API}/v2/post/publish/creator_info/query/", headers=hdr, timeout=30).json()
    allowed = (ci.get("data") or {}).get("privacy_level_options") or []
    privacy = "SELF_ONLY" if "SELF_ONLY" in allowed else (allowed[0] if allowed else "SELF_ONLY")
    size = TEST_VIDEO.stat().st_size
    title = "Test: k-means clustering · Data Science, End to End #datascience #machinelearning"
    src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}

    direct = _tt_upload(hdr, f"{TT_API}/v2/post/publish/video/init/", {
        "post_info": {"title": title, "privacy_level": privacy,
                      "disable_comment": False, "disable_duet": False, "disable_stitch": False},
        "source_info": src})
    if direct.get("ok"):
        return jsonify(ok=True, path="direct_post_private", privacy=privacy, creator_info=ci, result=direct)

    inbox = _tt_upload(hdr, f"{TT_API}/v2/post/publish/inbox/video/init/", {"source_info": src})
    return jsonify(ok=bool(inbox.get("ok")), path="inbox_draft", creator_info=ci,
                   direct_post_attempt=direct, result=inbox), (200 if inbox.get("ok") else 502)


@app.route("/<path:fname>")
def wellknown(fname):
    """Serve domain-verification files (e.g. tiktokXXXX.txt) dropped into web/well_known/."""
    if "/" in fname or fname.startswith("."):
        abort(404)
    if (WELL_KNOWN / fname).is_file():
        return send_from_directory(WELL_KNOWN, fname)
    abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
