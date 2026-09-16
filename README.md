# Public site + TikTok OAuth callback (Render)

One small Flask service that gives the TikTok app everything it needs — a real **landing page**,
**Terms of Service**, **Privacy Policy**, and the **OAuth redirect** — all on Render's own HTTPS
domain. No Vercel, no custom domain.

```
/            landing
/terms       Terms of Service   (give this URL to TikTok)
/privacy     Privacy Policy     (give this URL to TikTok)
/tiktok/callback   OAuth redirect target (register this as the Redirect URI)
/healthz     health check
```

## Deploy in ~5 minutes

1. **Make this folder its own git repo** (keeps the public site separate from the book source):
   ```bash
   cd marketing/social/web
   git init && git add . && git commit -m "Data Science End to End — site + TikTok callback"
   # push to a new GitHub repo, e.g. gh repo create dsee-social --public --source=. --push
   ```

2. **Create the service on Render** → New → **Blueprint**, pick this repo. It reads `render.yaml`
   (Python web service, US-East `virginia` region, Starter plan, a 1 GB disk at `/data`).
   You get a URL like `https://dsee-social.onrender.com` (rename the service if that name is taken).

3. **Set env vars** in Render → your service → *Environment*:
   - `TIKTOK_REDIRECT_URI` = `https://<your-service>.onrender.com/tiktok/callback`
   - `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` (from developers.tiktok.com)
   - `TIKTOK_STATE_DIR` = `/data` (already set by the blueprint)

4. **In the TikTok developer app**, set:
   - Redirect URI → `https://<your-service>.onrender.com/tiktok/callback`
   - Terms of Service URL → `https://<your-service>.onrender.com/terms`
   - Privacy Policy URL → `https://<your-service>.onrender.com/privacy`
   - Scopes → `user.info.basic`, `video.publish`, `video.upload`

5. **Domain verification** (if TikTok asks): drop the `tiktokXXXX.txt` file it gives you into
   `well_known/` and redeploy, **or** set `TIKTOK_VERIFY_META` to the meta value it gives you.

## Authorize (one click)

Because the service has the client key/secret + the disk, the callback finishes OAuth itself:
open the consent URL, approve, and the token is written to `/data/tiktok_token.json` — no copy-paste.
(Headless fallback still works: `python -m marketing.social.crosspost_tiktok --authorize`.)

## Notes

- **Starter plan ($7/mo)** is used because the persistent disk needs it; the disk is what keeps
  TikTok's *rotating* refresh token across deploys. A free static site can't do that.
- The poster (`crosspost_tiktok.py`) reads the same `/data` token. Run it daily as a Render **Cron
  Job** in the `virginia` region once the app is audited (unaudited apps are SELF_ONLY only). Sync
  the video files to the disk, or host them and switch to TikTok `PULL_FROM_URL`.
- This service intentionally does **not** import the book/pipeline code — it only needs Flask +
  requests, so the public repo stays tiny.
