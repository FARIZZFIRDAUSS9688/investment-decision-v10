# V10.4 PRIVATE HARDENED — BEGINNER SETUP

Use this version instead of V10.3.

## A. GitHub
1. Create GitHub account if needed.
2. Create repository: investment-decision-v10
3. Visibility: PRIVATE.
4. Upload everything from this ZIP.
5. Never put passwords/API secrets in source files.

## B. Cloudflare basic account
1. Create/sign in to Cloudflare.
2. Create D1 database: investment-v10-db.
3. Open D1 SQL Console.
4. Paste cloudflare/schema.sql and Run.

## C. Create Worker
1. Workers & Pages -> Create Worker.
2. Name: investment-v10.
3. Replace starter code with cloudflare/worker.js.
4. Add D1 binding:
   Variable name: DB
   Database: investment-v10-db
5. Add Secret:
   INGEST_TOKEN = a long random secret.
6. Add plaintext variables:
   LIGHT_REFRESH_MIN_SECONDS = 120
   LUNO_PAIRS = XBTMYR,ETHMYR,XRPMYR,SOLMYR
7. Deploy.

## D. Enable Zero Trust / Cloudflare Access
Cloudflare currently requires Zero Trust onboarding before Worker-level Access can be enabled.
Choose the Free plan. Cloudflare documentation currently says payment details are still requested
during onboarding even on the Free plan, but the Free plan is not charged.

## E. Protect the Worker
1. Workers & Pages -> investment-v10 -> Access.
2. Select: Protect this Worker behind Access.
3. Protect: ALL TRAFFIC.
4. Create an Allow policy for ONLY YOUR identity:
   Action: Allow
   Include: Email
   Value: your exact Cloudflare login email.
5. Do NOT use:
   - Everyone
   - all valid emails
   - a broad email domain
6. Apply Access.
7. Test in a private/incognito browser:
   the Worker URL must show Cloudflare login BEFORE the app.

## F. Create machine service token for GitHub
1. Zero Trust -> Access controls -> Service credentials -> Service Tokens.
2. Create token: v10-github-scanner.
3. Save BOTH values immediately:
   Client ID
   Client Secret
   (the secret is shown only once)
4. In the Access application policy for investment-v10, add a Service Auth policy
   that includes this service token.

## G. Cloudflare Cron
Worker -> Triggers -> Cron Triggers.
Add:
*/5 * * * *

This only refreshes the light/public-data layer.

## H. GitHub repository secrets
GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret.

Create:
API_BASE = full Worker URL
INGEST_TOKEN = same INGEST_TOKEN stored in Cloudflare
CF_ACCESS_CLIENT_ID = service-token Client ID
CF_ACCESS_CLIENT_SECRET = service-token Client Secret

## I. Test GitHub scanner
GitHub -> Actions -> V10 Private Heavy Validation Scanner -> Run workflow.
It should finish green.

## J. Phone
1. Open Worker URL on phone.
2. Cloudflare Access login appears first.
3. Sign in with your allowed Cloudflare identity.
4. Only then should V10.4 load.
5. Install to Home Screen if desired.

## K. Security verification before real financial data
Test these:
1. Incognito browser, signed out -> cannot open app.
2. Wrong/unapproved email -> denied.
3. GitHub Actions run -> green.
4. Browser DevTools/source -> no broker/API secret present.
5. Error screen -> generic message only, no SQL/DB dump.
6. Equity Market Feed remains NOT CONNECTED until a trusted feed is added.

Do NOT add real broker credentials until all six checks pass.
