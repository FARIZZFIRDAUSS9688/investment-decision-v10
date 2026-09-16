import os, json, math, statistics, datetime, urllib.request, urllib.parse, urllib.error
from pathlib import Path

ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
DATABASE_ID = os.environ["CF_D1_DATABASE_ID"]
API_TOKEN = os.environ["CF_D1_API_TOKEN"]
D1_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query"
UNIVERSE = Path(__file__).with_name("universe.json")
UA = "Mozilla/5.0 V10-Investment-Scanner/1.0"
SOURCE = "YAHOO_PUBLIC_CHART_UNOFFICIAL"

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def ts_iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=35) as r:
        return json.loads(r.read().decode())

def chart(symbol, range_, interval):
    qs = urllib.parse.urlencode({"range":range_,"interval":interval,"includePrePost":"false","events":"div,splits"})
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?" + qs
    data = get_json(url).get("chart", {})
    if data.get("error"): raise RuntimeError(str(data["error"]))
    res = (data.get("result") or [None])[0]
    if not res: raise RuntimeError("no chart result")
    ts = res.get("timestamp") or []
    q = (((res.get("indicators") or {}).get("quote") or [None])[0])
    if not q: raise RuntimeError("no quote data")
    bars=[]
    for i,t in enumerate(ts):
        try:
            o,h,l,c,v = q["open"][i],q["high"][i],q["low"][i],q["close"][i],q["volume"][i]
        except Exception:
            continue
        if None in (o,h,l,c): continue
        bars.append({"ts":int(t),"open":float(o),"high":float(h),"low":float(l),"close":float(c),"volume":float(v or 0)})
    if not bars: raise RuntimeError("no usable bars")
    return bars

def ema(vals,p):
    out=[None]*len(vals)
    if len(vals)<p:return out
    k=2/(p+1); x=sum(vals[:p])/p; out[p-1]=x
    for i in range(p,len(vals)):
        x=vals[i]*k+x*(1-k); out[i]=x
    return out

def rsi(vals,p=14):
    out=[None]*len(vals)
    if len(vals)<=p:return out
    g=l=0.0
    for i in range(1,p+1):
        d=vals[i]-vals[i-1]; g+=max(d,0); l+=max(-d,0)
    g/=p; l/=p
    out[p]=100.0 if l==0 else 100-100/(1+g/l)
    for i in range(p+1,len(vals)):
        d=vals[i]-vals[i-1]; g=(g*(p-1)+max(d,0))/p; l=(l*(p-1)+max(-d,0))/p
        out[i]=100.0 if l==0 else 100-100/(1+g/l)
    return out

def atr(h,l,c,p=14):
    tr=[h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    out=[None]*len(c)
    if len(c)<p:return out
    x=sum(tr[:p])/p; out[p-1]=x
    for i in range(p,len(c)):
        x=(x*(p-1)+tr[i])/p; out[i]=x
    return out

def rollavg(v,p):
    out=[None]*len(v); s=0.0
    for i,x in enumerate(v):
        s+=x
        if i>=p:s-=v[i-p]
        if i>=p-1:out[i]=s/p
    return out

def rollmax(v,p):
    out=[None]*len(v)
    for i in range(p,len(v)):out[i]=max(v[i-p:i])
    return out

def rollmin(v,p):
    out=[None]*len(v)
    for i in range(p,len(v)):out[i]=min(v[i-p:i])
    return out

def indicators(b):
    c=[x["close"] for x in b]; h=[x["high"] for x in b]; l=[x["low"] for x in b]; v=[x["volume"] for x in b]
    e20,e50,e200,e12,e26=ema(c,20),ema(c,50),ema(c,200),ema(c,12),ema(c,26)
    mac=[None]*len(c)
    valid=[]; idx=[]
    for i in range(len(c)):
        if e12[i] is not None and e26[i] is not None:
            mac[i]=e12[i]-e26[i]; valid.append(mac[i]); idx.append(i)
    sigc=ema(valid,9); sig=[None]*len(c)
    for j,x in enumerate(sigc):
        if x is not None:sig[idx[j]]=x
    return {"e20":e20,"e50":e50,"e200":e200,"rsi":rsi(c),"atr":atr(h,l,c),"v20":rollavg(v,20),"res":rollmax(h,20),"sup":rollmin(l,20),"mac":mac,"sig":sig}

def score(b,I,i):
    needed=[I[k][i] for k in ("e20","e50","e200","rsi","atr","v20","mac","sig")]
    if any(x is None for x in needed):return None
    p=b[i]["close"]; s=0
    if p>I["e20"][i]:s+=10
    if I["e20"][i]>I["e50"][i]:s+=10
    if I["e50"][i]>I["e200"][i]:s+=10
    rv=I["rsi"][i]
    if 50<=rv<=70:s+=10
    elif 45<=rv<50 or 70<rv<=75:s+=5
    if I["mac"][i]>I["sig"][i]:s+=10
    if I["mac"][i]>0:s+=5
    vr=b[i]["volume"]/I["v20"][i] if I["v20"][i] else 0
    if vr>=1.2:s+=10
    if vr>=1.5:s+=5
    if I["res"][i] and p>=I["res"][i]*0.995:s+=15
    elif p>=I["e20"][i]:s+=5
    atrp=I["atr"][i]/p*100 if p else 999
    if atrp<=5:s+=5
    if I["sup"][i] and p>I["sup"][i]:s+=5
    if p>I["e50"][i]:s+=5
    return min(100,s)

def rr_ref(b,I,i):
    p=b[i]["close"]; a=I["atr"][i]
    if not a:return 0,0,0
    stop=p-max(1.5*a,p*0.03)
    if I["sup"][i] and I["sup"][i]<p:stop=max(stop,I["sup"][i]*0.995)
    risk=p-stop
    if risk<=0:return 0,stop,0
    target=p+2*risk
    if I["res"][i] and I["res"][i]>p:target=max(target,I["res"][i])
    return (target-p)/risk,stop,target

def backtest(b,I):
    n=len(b); out=[]
    if n<260:return {"trades":0,"win":0,"pf":0,"exp":0,"dd":0}
    for i in range(max(210,int(n*.70)),n-11):
        sc=score(b,I,i)
        if sc is None or sc<75:continue
        p=b[i]["close"]; a=I["atr"][i]
        if not a:continue
        risk=max(1.5*a,p*.03); stop=p-risk; target=p+2*risk; r=None
        for j in range(i+1,min(i+11,n)):
            hs=b[j]["low"]<=stop; ht=b[j]["high"]>=target
            if hs and ht:r=-1;break
            if hs:r=-1;break
            if ht:r=2;break
        if r is None:r=max(-1,min(2,(b[min(i+10,n-1)]["close"]-p)/risk))
        out.append(r)
    if not out:return {"trades":0,"win":0,"pf":0,"exp":0,"dd":0}
    pos=[x for x in out if x>0]; neg=[x for x in out if x<0]
    pf=sum(pos)/abs(sum(neg)) if neg else (99 if pos else 0)
    eq=peak=dd=0
    for x in out:
        eq+=x; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {"trades":len(out),"win":len(pos)/len(out)*100,"pf":pf,"exp":statistics.mean(out),"dd":dd}

def d1(sql,params):
    payload=json.dumps({"sql":sql,"params":params}).encode()
    req=urllib.request.Request(D1_URL,data=payload,headers={"Authorization":f"Bearer {API_TOKEN}","Content-Type":"application/json","Accept":"application/json","User-Agent":UA},method="POST")
    with urllib.request.urlopen(req,timeout=45) as r: body=json.loads(r.read().decode())
    if not body.get("success"):raise RuntimeError("D1 success=false")
    return body

def d1_rows(sql,params=None):
    body=d1(sql,params or [])
    result=body.get("result") or []
    return (result[0].get("results") or []) if result else []

def health(status,note):
    d1("""INSERT INTO health(source,status,updated_at,note) VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,note=excluded.note""",["Equity Signal Scanner",status,now_iso(),note])

def position_health(status,note):
    d1("""INSERT INTO health(source,status,updated_at,note) VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,note=excluded.note""",["Position Manager",status,now_iso(),note])


def upsert(x):
    d1("""INSERT INTO buy_ideas(market,symbol,name,price,action,setup_grade,safety_status,technical_score,validation_status,rr,reason,price_updated_at,signal_updated_at,data_status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(market,symbol) DO UPDATE SET name=excluded.name,price=excluded.price,action=excluded.action,setup_grade=excluded.setup_grade,safety_status=excluded.safety_status,technical_score=excluded.technical_score,validation_status=excluded.validation_status,rr=excluded.rr,reason=excluded.reason,price_updated_at=excluded.price_updated_at,signal_updated_at=excluded.signal_updated_at,data_status=excluded.data_status,updated_at=excluded.updated_at""",[x[k] for k in ("market","symbol","name","price","action","grade","safety","score","validation","rr","reason","price_ts","signal_ts","data_status","updated")])

def analyse(item):
    daily=chart(item["symbol"],"3y","1d")
    if len(daily)<220:raise RuntimeError("insufficient history")
    I=indicators(daily); i=len(daily)-1; sc=score(daily,I,i)
    if sc is None:raise RuntimeError("warmup")
    rr,stop,target=rr_ref(daily,I,i); bt=backtest(daily,I)
    price=daily[-1]["close"]; pts=daily[-1]["ts"]
    try:
        intr=chart(item["symbol"],"1d","5m")
        if intr:price=intr[-1]["close"];pts=intr[-1]["ts"]
    except Exception:pass
    px=daily[-1]["close"]; vavg=I["v20"][i] or 0; vr=daily[-1]["volume"]/vavg if vavg else 0; turnover=px*daily[-1]["volume"]
    prelim=bt["trades"]>=30 and bt["pf"]>=1.2 and bt["exp"]>0
    low=item["market"]=="MY" and px<=1.0
    if low:
        safety="BLOCKED"; validation="NOT VALIDATED"; action="PAPER ONLY - LOW PRICE EXECUTION DATA"
    elif prelim and sc>=80 and rr>=2:
        safety="PASS"; validation="PRELIMINARY OOS PASS"; action="BUY CANDIDATE A" if sc>=90 else "BUY CANDIDATE B"
    elif sc>=75:
        safety="REVIEW"; validation="NEED MORE VALIDATION"; action="PAPER ONLY - NEED VALIDATION"
    else:
        safety="BLOCKED"; validation="NO ACTIONABLE EDGE"; action="WATCH / WAIT"
    grade="A" if sc>=90 else "B" if sc>=80 else "C" if sc>=70 else "D"
    mac=I["mac"][i]
    sig=I["sig"][i]
    res=I["res"][i]
    atr_pct=(I["atr"][i]/px*100) if px else 999

    e20=I["e20"][i]
    e50=I["e50"][i]
    e200=I["e200"][i]
    mac=I["mac"][i]
    sig=I["sig"][i]
    res=I["res"][i]
    atr_pct=(I["atr"][i]/px*100) if px else 999

    def pct_gap(a,b):
        return ((a/b)-1)*100 if b else 0.0

    breakout_pct=(px/res*100) if res else 0.0
    mac_gap=(mac-sig) if mac is not None and sig is not None else None

    tech_checks=[
        (
            "Price > EMA20",
            px>e20,
            "Price > EMA20",
            f"{px:.4f} > {e20:.4f} ({pct_gap(px,e20):+.2f}%)"
        ),
        (
            "EMA20 > EMA50",
            e20>e50,
            "EMA20 > EMA50",
            f"{e20:.4f} > {e50:.4f} ({pct_gap(e20,e50):+.2f}%)"
        ),
        (
            "EMA50 > EMA200",
            e50>e200,
            "EMA50 > EMA200",
            f"{e50:.4f} > {e200:.4f} ({pct_gap(e50,e200):+.2f}%)"
        ),
        (
            "RSI14",
            50<=I["rsi"][i]<=70,
            "50–70",
            f"{I['rsi'][i]:.1f}"
        ),
        (
            "MACD > Signal",
            mac is not None and sig is not None and mac>sig,
            "MACD > Signal",
            f"{mac:.4f} > {sig:.4f} (Δ {mac_gap:+.4f})"
            if mac is not None and sig is not None else "N/A"
        ),
        (
            "MACD > 0",
            mac is not None and mac>0,
            "> 0",
            f"{mac:.4f}" if mac is not None else "N/A"
        ),
        (
            "Volume Ratio",
            vr>=1.20,
            "≥ 1.20x",
            f"{vr:.2f}x"
        ),
        (
            "20D Breakout",
            res is not None and px>=res*0.995,
            "Price ≥ 99.5% of 20D High",
            f"{px:.4f} vs {res:.4f} ({breakout_pct:.2f}% of 20D High)"
            if res else "N/A"
        ),
        (
            "ATR%",
            atr_pct<=5,
            "≤ 5.00%",
            f"{atr_pct:.2f}%"
        ),
        (
            "R:R",
            rr>=2.0,
            "≥ 2.00",
            f"{rr:.2f}"
        )
    ]
    tech_pass=sum(1 for _,ok,_,_ in tech_checks if ok)

    val_checks=[
        ("OOS Sample", bt["trades"]>=30, "≥ 30 trades", f"{bt['trades']} trades"),
        ("Win Rate", bt["win"]>=50, "≥ 50.0%", f"{bt['win']:.1f}%"),
        ("Profit Factor", bt["pf"]>=1.20, "≥ 1.20", f"{bt['pf']:.2f}"),
        ("Expectancy", bt["exp"]>0, "> 0R", f"{bt['exp']:+.2f}R")
    ]
    val_pass=sum(1 for _,ok,_,_ in val_checks if ok)

    lines=[f"SUMMARY|Technical Study||{tech_pass}/10"]
    for label,ok,standard,actual in tech_checks:
        lines.append(
            ("PASS" if ok else "FAIL")
            +f"|{label}|{standard}|{actual}"
        )

    lines.append("SECTION|Validation Study||")
    lines.append(f"SUMMARY|Validation Checks||{val_pass}/4")
    for label,ok,standard,actual in val_checks:
        lines.append(
            ("PASS" if ok else "FAIL")
            +f"|{label}|{standard}|{actual}"
        )

    lines += [
        f"INFO|Max Drawdown|Value|{bt['dd']:.2f}R",
        f"INFO|Turnover|Approx.|~{turnover:.0f}",
        f"INFO|Stop Reference|Reference only|{stop:.4f}",
        f"INFO|Target Reference|Reference only|{target:.4f}",
        f"INFO|Data Source|Source|{SOURCE}",
        "INFO|Reminder|Meaning|Technical score is NOT probability."
    ]
    if low:
        lines.append(
            "WARN|Low-price MY safety|Requirement|"
            "Spread / tick / slippage must be validated; action blocked."
        )

    reason="\n".join(lines)
    return {"market":item["market"],"symbol":item["symbol"],"name":item.get("name",item["symbol"]),"price":str(round(price,6)),"action":action,"grade":grade,"safety":safety,"score":str(int(round(sc))),"validation":validation,"rr":str(round(rr,2)),"reason":reason[:1800],"price_ts":ts_iso(pts),"signal_ts":now_iso(),"data_status":"UNOFFICIAL_BEST_EFFORT","updated":now_iso()}


def normalise_position_symbol(market,symbol):
    m=str(market or "").upper().strip()
    s=str(symbol or "").upper().strip()
    if m=="MY" and not s.endswith(".KL"):
        if s.isdigit(): s=s+".KL"
    elif m=="HK" and not s.endswith(".HK"):
        if s.isdigit(): s=s.zfill(4)+".HK"
    return s

def position_action(avg,current,I,i):
    if avg<=0 or current<=0:
        return "WAIT - DATA","Missing valid price data."

    pnl=(current/avg-1)*100
    e20=I["e20"][i]
    e50=I["e50"][i]
    r=I["rsi"][i]
    a=I["atr"][i]

    if pnl<=-8:
        return "EXIT WATCH - LOSING THESIS",f"P/L {pnl:.2f}% <= -8% risk-review threshold."
    if current<e50 and pnl<0:
        return "REDUCE / RISK REVIEW",f"Price below EMA50 while position is losing ({pnl:.2f}%)."
    if pnl>=15 and current<e20:
        return "EXIT CANDIDATE - PROTECT PROFIT",f"Profit {pnl:.2f}% but price fell below EMA20."
    if pnl>=10:
        trail=max(e20,current-2*a) if a else e20
        return "TRAIL PROFIT / HOLD",f"Profit {pnl:.2f}%. Trail reference ~{trail:.4f}."
    if pnl>=5 and r is not None and r>=70:
        return "TAKE PARTIAL PROFIT REVIEW",f"Profit {pnl:.2f}% with RSI14 {r:.1f}."
    if current>=e20 and e20>=e50:
        return "HOLD - TREND OK",f"Price > EMA20 > EMA50. P/L {pnl:.2f}%."
    return "HOLD / MONITOR",f"P/L {pnl:.2f}%. No major exit trigger."

def update_positions():
    rows=d1_rows("""SELECT platform,market,symbol,quantity,avg_buy FROM positions ORDER BY platform,market,symbol""")
    if not rows:
        position_health("CURRENT","No saved positions.")
        print("Position Manager: no positions")
        return

    ok=0
    failed=[]

    for row in rows:
        platform=row["platform"]; market=row["market"]; stored=row["symbol"]
        try:
            if str(market).upper()=="CRYPTO":
                raise RuntimeError("Crypto position sync comes in next connector phase")

            symbol=normalise_position_symbol(market,stored)
            b=chart(symbol,"1y","1d")
            if len(b)<210: raise RuntimeError("insufficient history")
            I=indicators(b); i=len(b)-1

            current=b[-1]["close"]; pts=b[-1]["ts"]
            try:
                intr=chart(symbol,"1d","5m")
                if intr:
                    current=intr[-1]["close"]; pts=intr[-1]["ts"]
            except Exception:
                pass

            avg=float(row["avg_buy"] or 0)
            pnl=(current/avg-1)*100 if avg>0 else 0
            action,reason=position_action(avg,current,I,i)
            now=now_iso()

            d1("""UPDATE positions SET
                current_price=?,pnl_pct=?,action=?,reason=?,
                price_updated_at=?,signal_updated_at=?,
                data_status='UNOFFICIAL_BEST_EFFORT',updated_at=?
                WHERE platform=? AND market=? AND symbol=?""",
                [str(round(current,6)),str(round(pnl,4)),action,reason,
                 ts_iso(pts),now,now,platform,market,stored])

            ok+=1
            print(f"POSITION {market} {stored}: {action} P/L={pnl:.2f}%")
        except Exception as e:
            failed.append(stored)
            print("POSITION FAILED",stored,type(e).__name__,e)

    status="CURRENT" if ok==len(rows) else "PARTIAL" if ok else "ERROR"
    note=f"{ok}/{len(rows)} positions refreshed."
    if failed: note+=" Failed: "+",".join(failed[:10])
    position_health(status,note)

def main():
    cfg=json.loads(UNIVERSE.read_text()); items=cfg.get("symbols",[]); ok=0; failed=[]
    for item in items:
        try:
            x=analyse(item); upsert(x); ok+=1; print(item["symbol"],x["score"],x["action"])
        except Exception as e:
            failed.append(item.get("symbol","?")); print("FAILED",item.get("symbol"),type(e).__name__,e)
    status="CURRENT" if ok==len(items) else "PARTIAL" if ok else "ERROR"
    health(status,f"{ok}/{len(items)} symbols scanned. Source={SOURCE}; unofficial/best-effort, not guaranteed real-time." + (" Failed: "+",".join(failed) if failed else ""))
    if ok==0:raise RuntimeError("all symbols failed")
    update_positions()
    print(f"Equity scan complete: {ok}/{len(items)}")

if __name__=="__main__":main()
