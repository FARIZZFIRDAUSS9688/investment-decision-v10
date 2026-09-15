# V10.4B Private No-Card Setup

No Cloudflare Zero Trust required.

Existing D1 and Worker stay as-is.

Update these GitHub files with this package:
- cloudflare/worker.js
- scanner/run.py
- .github/workflows/heavy-scanner.yml

Cloudflare Worker secrets:
- keep INGEST_TOKEN
- add OWNER_PASSWORD = strong password only you know
- add SESSION_SECRET = a DIFFERENT long random secret (64+ characters recommended)

Keep variables:
- LIGHT_REFRESH_MIN_SECONDS = 120
- LUNO_PAIRS = XBTMYR,ETHMYR,XRPMYR,SOLMYR

Deploy updated worker.js. Opening the Worker URL must show a private password login.

GitHub Actions secrets needed later:
- API_BASE
- INGEST_TOKEN

Security:
- password stays in Cloudflare Secret, never source code
- signed session cookie is Secure + HttpOnly + SameSite=Strict
- browser localStorage contains no app password/token
- D1 remains server-side through env.DB
- machine writes require INGEST_TOKEN
- errors remain generic
- no auto-trading endpoint
