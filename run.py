import os, json, datetime, urllib.request

API_BASE=os.environ["API_BASE"].rstrip("/")
INGEST_TOKEN=os.environ["INGEST_TOKEN"]

def post(payload):
    data=json.dumps(payload).encode()
    req=urllib.request.Request(
        API_BASE+"/api/ingest",
        data=data,
        headers={
            "content-type":"application/json",
            "authorization":"Bearer "+INGEST_TOKEN
        },
        method="POST"
    )
    with urllib.request.urlopen(req,timeout=45) as r:
        print(r.read().decode())

now=datetime.datetime.now(datetime.timezone.utc).isoformat()

post({
  "health":[{
    "source":"Heavy Validation Scanner",
    "status":"CURRENT",
    "updated_at":now,
    "note":"Private scheduled heavy job ran. Real equity/backtest engine not connected yet."
  }],
  "buy_ideas":[{
    "market":"DEMO","symbol":"SAMPLE","name":"Demo only","price":1.0,
    "action":"PAPER ONLY - NEED DATA","setup_grade":"U","safety_status":"BLOCKED",
    "technical_score":0,"validation_status":"NOT VALIDATED","rr":0,
    "reason":"Placeholder only. Never use as an investment signal.",
    "price_updated_at":now,"signal_updated_at":now,"data_status":"DEMO","updated_at":now
  }]
})
