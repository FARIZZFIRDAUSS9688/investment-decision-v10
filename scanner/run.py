import os
import json
import datetime
import urllib.request
import urllib.error

ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
API_TOKEN = os.environ["CF_D1_API_TOKEN"]

URL = (
    f"https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
)

def d1_query(sql, params):
    payload = json.dumps({
        "sql": sql,
        "params": params
    }).encode("utf-8")

    request = urllib.request.Request(
        URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Cloudflare D1 HTTP {e.code}: {body[:500]}"
        )

    if not result.get("success"):
        raise RuntimeError(
            "Cloudflare D1 API returned success=false"
        )

    for item in result.get("result", []):
        if item.get("success") is False:
            raise RuntimeError(
                "A D1 query failed"
            )

    return result


now = datetime.datetime.now(
    datetime.timezone.utc
).isoformat()

# 1. Update scanner health
d1_query(
    """
    INSERT INTO health(source,status,updated_at,note)
    VALUES(?,?,?,?)
    ON CONFLICT(source) DO UPDATE SET
        status=excluded.status,
        updated_at=excluded.updated_at,
        note=excluded.note
    """,
    [
        "Heavy Validation Scanner",
        "CURRENT",
        now,
        "GitHub scanner connected directly to Cloudflare D1."
    ]
)

# 2. Insert a safe DEMO row only
d1_query(
    """
    INSERT INTO buy_ideas(
        market,
        symbol,
        name,
        price,
        action,
        setup_grade,
        safety_status,
        technical_score,
        validation_status,
        rr,
        reason,
        price_updated_at,
        signal_updated_at,
        data_status,
        updated_at
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(market,symbol) DO UPDATE SET
        name=excluded.name,
        price=excluded.price,
        action=excluded.action,
        setup_grade=excluded.setup_grade,
        safety_status=excluded.safety_status,
        technical_score=excluded.technical_score,
        validation_status=excluded.validation_status,
        rr=excluded.rr,
        reason=excluded.reason,
        price_updated_at=excluded.price_updated_at,
        signal_updated_at=excluded.signal_updated_at,
        data_status=excluded.data_status,
        updated_at=excluded.updated_at
    """,
    [
        "DEMO",
        "SAMPLE",
        "Demo only",
        "1.0",
        "PAPER ONLY - NEED DATA",
        "U",
        "BLOCKED",
        "0",
        "NOT VALIDATED",
        "0",
        "Placeholder only. Never use as an investment signal.",
        now,
        now,
        "DEMO",
        now
    ]
)

print("D1 update successful")
