# Public-deployment checklist (nothing has been deployed)

Secrets
- [ ] `QLOO_API_KEY` only as a host secret/env var; confirm `/healthz` shows `qloo_key_configured` but never the key.
- [ ] Rotate the key if it was ever pasted anywhere; check `git log -p` and build logs for leaks.
- [ ] `.env*`, `.cache/`, `private/`, `fixtures/`, `results.json`, `RAW_RUN.md` absent from the repo and the image (`.dockerignore` covers the image).

Qloo terms
- [ ] No Qloo response data in the public repo (public reports are scrubbed; originals live in `private/`; tests use synthetic fixtures only).
- [ ] Re-read hackathon rules on caching/attribution; private server-side cache is the documented-allowed pattern (verify again).
- [ ] Daily cap (`VIBESPEC_DAILY_CALL_CAP`) set below the key's real quota; per-IP rate limit active.

Runtime
- [ ] Runs use background jobs + polling (short requests), so host request timeouts do not matter; first visit after Render Free spin-down takes ~1 min (state this in the Devpost testing instructions). See `DEPLOY.md`.
- [ ] Put behind HTTPS; app sets CSP, nosniff, no-referrer, no-store. Add HSTS at the proxy.
- [ ] `VIBESPEC_TRUST_PROXY=1` only behind a trusted proxy; run `python3 tools/leak_scan.py` before every publish.

Licensing
- [ ] UI has no third-party assets, fonts, icons or scripts (system fonts, inline CSS/JS). Re-check if you add any.
- [ ] Repo LICENSE chosen; dependencies: none at runtime (pytest dev-only).
- [ ] Brand names (Aesop, Muji, ...) are user inputs rendered as text only; no logos used.

Honesty copy
- [ ] UI/README state: Qloo = cultural affinity only; no prices, inventory, rights, or revenue claims; budget figures are user assumptions or "indicative".
