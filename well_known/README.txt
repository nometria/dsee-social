Drop TikTok's domain-verification file here.

When TikTok asks you to "verify URL prefix / domain ownership", it gives you either:
  (a) a file to host, e.g.  tiktokXXXXXXXX.txt  containing a single verification line, or
  (b) a <meta> tag value.

For (a): place that .txt file in THIS folder and redeploy. It will be served at the site root,
         e.g.  https://<your-service>.onrender.com/tiktokXXXXXXXX.txt
For (b): set the TIKTOK_VERIFY_META environment variable to the meta content value instead
         (no redeploy of files needed).

This README is ignored by the verifier.
