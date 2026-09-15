# V10.4 Private Hardened

Single-user private investment decision-support starter.

Security model:
1. Cloudflare Access protects the entire Worker before the Worker runs.
2. Human access is limited to the owner's exact Cloudflare identity/email.
3. GitHub Actions authenticates with a Cloudflare Access Service Token.
4. A separate INGEST_TOKEN is required for write/ingest as defense-in-depth.
5. D1 is only accessed through the Worker binding.
6. Frontend stores no app password/API key in localStorage.
7. User-facing errors are generic; internal error text is not returned.
8. No trade execution endpoint exists.

Important:
- This starter is still fail-closed for equities until a trusted equity feed is connected.
- Demo/unvalidated rows must never be treated as investment advice or a live trading signal.
