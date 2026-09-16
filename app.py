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
import datetime as _dt
from pathlib import Path

import requests
from flask import Flask, render_template, request, send_from_directory, abort

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
        clean = code.split("*")[0]
        try:
            tok = requests.post(f"{TT_API}/v2/oauth/token/", data={
                "client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code", "code": clean,
                "redirect_uri": REDIRECT_URI}, timeout=30).json()
        except Exception as e:  # noqa: BLE001
            return render_template("callback.html", **ctx(
                status="error", detail=f"Token exchange request failed: {e}", code=code, state=state))
        if "refresh_token" in tok:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / "tiktok_token.json").write_text(json.dumps(tok, indent=2))
            return render_template("callback.html", **ctx(status="stored", state=state))
        return render_template("callback.html", **ctx(
            status="error", detail=f"TikTok rejected the code: {tok.get('error_description', tok)}",
            code=code, state=state))

    # No secrets on this instance — show the code for the CLI paste flow.
    return render_template("callback.html", **ctx(status="code", code=code, state=state))


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
