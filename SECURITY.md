# Security design

Human:
Internet -> Cloudflare Access -> Worker -> D1

Automation:
GitHub Actions -> Cloudflare Access Service Token -> Worker
               -> INGEST_TOKEN -> /api/ingest -> D1

Protections:
- Entire Worker is private behind Access.
- Exact owner identity only.
- Service token for automation.
- Separate write token for defense-in-depth.
- D1 has no browser-side connection string.
- Parameter-bound SQL.
- No app secret in browser localStorage.
- User-facing errors are generic.
- CSP blocks third-party scripts/frames by default.
- No public registration.
- No trade execution endpoint.
