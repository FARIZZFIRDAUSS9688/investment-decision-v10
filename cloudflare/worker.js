const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer"
};
const json = (data, status=200) =>
  new Response(JSON.stringify(data), {status, headers: JSON_HEADERS});
const nowIso = () => new Date().toISOString();

const HTML_HEADERS = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
  "content-security-policy": "default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
};
function parseCookies(req){
  const raw=req.headers.get("cookie")||"", out={};
  for(const part of raw.split(";")){const i=part.indexOf("="); if(i>0) out[part.slice(0,i).trim()]=part.slice(i+1).trim();}
  return out;
}
function b64urlBytes(bytes){let x="";for(const b of new Uint8Array(bytes))x+=String.fromCharCode(b);return btoa(x).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"");}
function b64urlText(text){return b64urlBytes(new TextEncoder().encode(text));}
function fromB64url(s){s=s.replace(/-/g,"+").replace(/_/g,"/");while(s.length%4)s+="=";return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function hmac(secret,message){const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);return new Uint8Array(await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(message)));}
async function safeEqualText(a,b){const da=new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(a)));const db=new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(b)));let d=0;for(let i=0;i<da.length;i++)d|=da[i]^db[i];return d===0;}
async function makeSession(env){const payload=b64urlText(JSON.stringify({v:1,exp:Date.now()+2592000000}));const sig=b64urlBytes(await hmac(env.SESSION_SECRET,payload));return payload+"."+sig;}
async function validSession(req,env){const t=parseCookies(req).v10_session;if(!t||!env.SESSION_SECRET)return false;const a=t.split(".");if(a.length!==2)return false;try{const exp=await hmac(env.SESSION_SECRET,a[0]),got=fromB64url(a[1]);if(exp.length!==got.length)return false;let d=0;for(let i=0;i<exp.length;i++)d|=exp[i]^got[i];if(d)return false;const body=JSON.parse(new TextDecoder().decode(fromB64url(a[0])));return body.v===1&&Number(body.exp)>Date.now();}catch{return false;}}
function loginPage(message="") { return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V10 Private Login</title><style>body{font-family:system-ui;background:#f8fafc;margin:0;min-height:100vh;display:grid;place-items:center;color:#0f172a}.box{width:min(92vw,380px);background:white;padding:24px;border-radius:16px;box-shadow:0 8px 30px #0002}input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cbd5e1;border-radius:10px;margin:10px 0}button{width:100%;padding:12px;border:0;border-radius:10px;background:#0f172a;color:white;font-weight:700}.err{background:#fee2e2;padding:10px;border-radius:10px}</style></head><body><div class="box"><h2>Investment V10</h2><p>Private owner access</p>${message?`<div class="err">${message}</div>`:""}<form method="POST" action="/auth/login"><input type="password" name="password" autocomplete="current-password" placeholder="Private password" required><button type="submit">Sign in</button></form></div></body></html>`; }


function bearer(req) {
  const h = req.headers.get("authorization") || "";
  return h.startsWith("Bearer ") ? h.slice(7) : "";
}
function ingestAuth(req, env) {
  return !!env.INGEST_TOKEN && bearer(req) === env.INGEST_TOKEN;
}
function ageSeconds(ts) {
  if (!ts) return 999999999;
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return 999999999;
  return Math.max(0, Math.round((Date.now()-d.getTime())/1000));
}
async function stateGet(env,key) {
  return await env.DB.prepare("SELECT value,updated_at FROM app_state WHERE key=?")
    .bind(key).first();
}
async function stateSet(env,key,value) {
  const now=nowIso();
  await env.DB.prepare(`
    INSERT INTO app_state(key,value,updated_at) VALUES(?,?,?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
  `).bind(key,String(value??""),now).run();
}
async function upsertHealth(env,source,status,note,when=nowIso()) {
  await env.DB.prepare(`
    INSERT INTO health(source,status,updated_at,note) VALUES(?,?,?,?)
    ON CONFLICT(source) DO UPDATE SET status=excluded.status,
      updated_at=excluded.updated_at,note=excluded.note
  `).bind(source,status,when,note||"").run();
}
function lunoPairs(env) {
  return String(env.LUNO_PAIRS||"XBTMYR,ETHMYR,XRPMYR,SOLMYR")
    .split(",").map(x=>x.trim().toUpperCase()).filter(Boolean).slice(0,10);
}
async function refreshLuno(env) {
  const pairs=lunoPairs(env), received=nowIso();
  let ok=0; const errors=[];
  for(const pair of pairs){
    try{
      const r=await fetch(
        "https://api.luno.com/api/1/ticker?pair="+encodeURIComponent(pair),
        {headers:{accept:"application/json"}}
      );
      if(!r.ok) throw new Error("upstream");
      const x=await r.json();
      const price=Number(x.last_trade||0), bid=Number(x.bid||0),
            ask=Number(x.ask||0), vol=Number(x.rolling_24_hour_volume||0);
      if(!(price>0)) throw new Error("bad-data");
      const qts=x.timestamp?new Date(Number(x.timestamp)).toISOString():received;

      await env.DB.prepare(`
        INSERT INTO market_quotes(
          source,market,symbol,price,bid,ask,volume,quote_ts,received_at,status
        ) VALUES('Luno','CRYPTO',?,?,?,?,?,?,?,'CURRENT')
        ON CONFLICT(source,market,symbol) DO UPDATE SET
          price=excluded.price,bid=excluded.bid,ask=excluded.ask,volume=excluded.volume,
          quote_ts=excluded.quote_ts,received_at=excluded.received_at,status=excluded.status
      `).bind(pair,price,bid,ask,vol,qts,received).run();
      ok++;
    } catch {
      errors.push(pair);
    }
  }
  const status=ok===pairs.length?"CURRENT":ok>0?"PARTIAL":"ERROR";
  await upsertHealth(
    env,"Luno Market",status,
    `${ok}/${pairs.length} pairs refreshed` + (errors.length?"; failed: "+errors.join(", "):""),
    received
  );
  return {source:"Luno Market",status,ok,total:pairs.length};
}
async function refreshLight(env,force=false) {
  const minAge=Math.max(30,Number(env.LIGHT_REFRESH_MIN_SECONDS||120));
  const last=await stateGet(env,"last_light_refresh");
  const age=last?ageSeconds(last.updated_at):999999999;
  if(!force && age<minAge)
    return {skipped:true,reason:"fresh-enough",age_seconds:age};

  const started=nowIso();
  const results=[await refreshLuno(env)];
  await upsertHealth(
    env,"Equity Market Feed","NOT CONNECTED",
    "Trusted HTTP equity feed not connected yet. Equity judgement remains blocked."
  );
  await stateSet(env,"last_light_refresh",started);
  return {skipped:false,started_at:started,results};
}
function withAge(rows) {
  return rows.map(x=>({...x,
    price_age_sec:ageSeconds(x.price_updated_at),
    signal_age_sec:ageSeconds(x.signal_updated_at)}));
}
async function api(req,env,url) {
  const p=url.pathname;

  if(p==="/api/refresh-light" && (req.method==="POST"||req.method==="GET")){
    try{
      return json(await refreshLight(env,url.searchParams.get("force")==="1"));
    }catch{
      await upsertHealth(env,"Light Refresh","ERROR","Refresh failed. Check private logs.");
      return json({ok:false,error:"REFRESH_FAILED"},500);
    }
  }

  if(p==="/api/health" && req.method==="GET"){
    const {results=[]}=await env.DB.prepare(
      "SELECT source,status,updated_at,note FROM health ORDER BY source"
    ).all();
    return json({health:results.map(x=>({...x,age_sec:ageSeconds(x.updated_at)}))});
  }

  if(p==="/api/quotes" && req.method==="GET"){
    const {results=[]}=await env.DB.prepare(`
      SELECT source,market,symbol,price,bid,ask,volume,quote_ts,received_at,status
      FROM market_quotes ORDER BY market,symbol LIMIT 100
    `).all();
    return json({quotes:results.map(x=>({...x,age_sec:ageSeconds(x.received_at)}))});
  }

  if(p==="/api/buy-ideas" && req.method==="GET"){
    const {results=[]}=await env.DB.prepare(`
      SELECT market,symbol,name,price,action,setup_grade,safety_status,
      technical_score,validation_status,rr,reason,price_updated_at,signal_updated_at,
      data_status,updated_at
      FROM buy_ideas
      ORDER BY CASE action WHEN 'BUY CANDIDATE A' THEN 1
      WHEN 'BUY CANDIDATE B' THEN 2 ELSE 9 END, technical_score DESC LIMIT 50
    `).all();
    return json({ideas:withAge(results)});
  }

  if(p==="/api/positions" && req.method==="GET"){
    const {results=[]}=await env.DB.prepare(`
      SELECT platform,market,symbol,quantity,avg_buy,current_price,pnl_pct,
      action,reason,price_updated_at,signal_updated_at,data_status,updated_at
      FROM positions
      ORDER BY CASE WHEN action LIKE 'HARD RISK%' THEN 1
      WHEN action LIKE 'EXIT%' THEN 2 WHEN action LIKE 'REDUCE%' THEN 3 ELSE 9 END,symbol
    `).all();
    return json({positions:withAge(results)});
  }

  if(p==="/api/history" && req.method==="GET"){
    const {results=[]}=await env.DB.prepare(`
      SELECT market,symbol,entry_price,exit_price,pnl_pct,exit_reason,closed_at
      FROM closed_trades ORDER BY closed_at DESC LIMIT 100
    `).all();
    return json({trades:results});
  }

  if(p==="/api/ingest" && req.method==="POST"){
    if(!ingestAuth(req,env)) return json({error:"unauthorized"},401);

    let body;
    try { body=await req.json(); }
    catch { return json({error:"bad_request"},400); }

    const now=nowIso(), stmts=[];

    for(const h of (body.health||[])){
      stmts.push(env.DB.prepare(`
        INSERT INTO health(source,status,updated_at,note) VALUES(?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET status=excluded.status,
        updated_at=excluded.updated_at,note=excluded.note
      `).bind(h.source,h.status,h.updated_at||now,h.note||""));
    }

    for(const x of (body.buy_ideas||[])){
      stmts.push(env.DB.prepare(`
        INSERT INTO buy_ideas(
          market,symbol,name,price,action,setup_grade,safety_status,
          technical_score,validation_status,rr,reason,price_updated_at,
          signal_updated_at,data_status,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(market,symbol) DO UPDATE SET
          name=excluded.name,price=excluded.price,action=excluded.action,
          setup_grade=excluded.setup_grade,safety_status=excluded.safety_status,
          technical_score=excluded.technical_score,
          validation_status=excluded.validation_status,rr=excluded.rr,
          reason=excluded.reason,price_updated_at=excluded.price_updated_at,
          signal_updated_at=excluded.signal_updated_at,
          data_status=excluded.data_status,updated_at=excluded.updated_at
      `).bind(
        x.market,x.symbol,x.name||"",Number(x.price||0),x.action||"WAIT",
        x.setup_grade||"U",x.safety_status||"BLOCKED",Number(x.technical_score||0),
        x.validation_status||"NOT VALIDATED",Number(x.rr||0),x.reason||"",
        x.price_updated_at||null,x.signal_updated_at||null,
        x.data_status||"UNVALIDATED",x.updated_at||now
      ));
    }

    for(const x of (body.positions||[])){
      stmts.push(env.DB.prepare(`
        INSERT INTO positions(
          platform,market,symbol,quantity,avg_buy,current_price,pnl_pct,
          action,reason,price_updated_at,signal_updated_at,data_status,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(platform,market,symbol) DO UPDATE SET
          quantity=excluded.quantity,avg_buy=excluded.avg_buy,
          current_price=excluded.current_price,pnl_pct=excluded.pnl_pct,
          action=excluded.action,reason=excluded.reason,
          price_updated_at=excluded.price_updated_at,
          signal_updated_at=excluded.signal_updated_at,
          data_status=excluded.data_status,updated_at=excluded.updated_at
      `).bind(
        x.platform,x.market,x.symbol,Number(x.quantity||0),Number(x.avg_buy||0),
        Number(x.current_price||0),Number(x.pnl_pct||0),
        x.action||"HOLD / MONITOR",x.reason||"",
        x.price_updated_at||null,x.signal_updated_at||null,
        x.data_status||"UNVALIDATED",x.updated_at||now
      ));
    }

    try{
      if(stmts.length) await env.DB.batch(stmts);
      return json({ok:true,written:stmts.length});
    }catch{
      return json({ok:false,error:"INGEST_FAILED"},500);
    }
  }

  return json({error:"not_found"},404);
}

const manifest={
  name:"Investment Decision V10",
  short_name:"V10 Invest",
  start_url:"/",
  display:"standalone",
  background_color:"#f8fafc",
  theme_color:"#0f172a",
  icons:[{src:"/icon.svg",sizes:"any",type:"image/svg+xml",purpose:"any maskable"}]
};

const APP_HTML=`<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0f172a"><link rel="manifest" href="/manifest.webmanifest">
<title>Private Investment V10</title><style>
body{font-family:system-ui;margin:0;background:#f8fafc;color:#0f172a}
header{background:#0f172a;color:white;padding:16px}
nav{display:flex;gap:8px;overflow:auto;padding:10px;background:white;position:sticky;top:0;z-index:2}
button{padding:10px 12px;border:0;border-radius:10px;background:#e2e8f0;font-weight:600}
button.active{background:#0f172a;color:white}button.primary{background:#2563eb;color:white}
main{padding:14px;max-width:900px;margin:auto}.card{background:white;border-radius:14px;padding:14px;margin:10px 0;box-shadow:0 2px 10px #0001}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#e2e8f0;font-size:12px}
.pass{background:#dcfce7}.block{background:#fee2e2}.warn{background:#fef3c7}
small{color:#64748b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.topline{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
</style></head><body>
<header><div class="topline"><div><b>Investment Decision V10.4B</b><br>
<small style="color:#cbd5e1">Private • Owner password • No auto-trade</small></div>
<div><span id="live" class="badge warn">CHECKING</span></div></div></header>
<nav><button data-tab="home" class="active">HOME</button>
<button data-tab="buy">BUY IDEAS</button><button data-tab="pos">MY POSITIONS</button>
<button data-tab="history">HISTORY</button><button id="logout">LOG OUT</button></nav><main id="app"></main>
<script>
const $=s=>document.querySelector(s),app=$("#app"),live=$("#live");
let currentTab="home",lastLightAttempt=0;
async function api(path,opts={}){const r=await fetch(path,opts);if(r.status===401){location.href="/";throw new Error("AUTH")}if(!r.ok)throw new Error("HTTP");return r.json()}
function esc(x){return String(x??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function age(sec){sec=Number(sec||0);if(sec<60)return sec+"s";if(sec<3600)return Math.round(sec/60)+"m";return(sec/3600).toFixed(1)+"h"}
function freshClass(sec,limit=300){return Number(sec)<=limit?"pass":Number(sec)<=limit*3?"warn":"block"}
async function lightRefresh(force=false){
  const now=Date.now(); if(!force&&now-lastLightAttempt<60000)return; lastLightAttempt=now;
  try{live.textContent="REFRESHING";live.className="badge warn";
    await api("/api/refresh-light"+(force?"?force=1":""),{method:"POST"});
    live.textContent="CURRENT";live.className="badge pass";
  }catch{live.textContent="REFRESH ERROR";live.className="badge block";}
}
async function render(tab){
  currentTab=tab;document.querySelectorAll("nav button[data-tab]").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
  try{
    if(tab==="home"){
      const[h,q]=await Promise.all([api("/api/health"),api("/api/quotes")]);
      const health=h.health.map(x=>'<div class="card"><b>'+esc(x.source)+'</b><p><span class="badge '+freshClass(x.age_sec,300)+'">'+esc(x.status)+'</span> <span class="badge">age '+age(x.age_sec)+'</span></p><small>'+esc(x.note)+'</small></div>').join("");
      const quotes=q.quotes.map(x=>'<div class="card"><b>'+esc(x.symbol)+'</b> <small>'+esc(x.source)+'</small><p>'+esc(x.price)+'</p><span class="badge '+freshClass(x.age_sec,180)+'">price age '+age(x.age_sec)+'</span></div>').join("");
      app.innerHTML='<h2>System health</h2><div class="grid">'+health+'</div><h2>Fresh quotes</h2><div class="grid">'+(quotes||'<div class="card">No quotes yet.</div>')+'</div><div class="card"><button id="force" class="primary">Refresh now</button><p><small>Fail-closed: stale or unvalidated data cannot become an actionable judgement.</small></p></div>';
      $("#force").onclick=()=>lightRefresh(true).then(()=>render("home"));
    } else if(tab==="buy"){
      const d=await api("/api/buy-ideas");
      app.innerHTML='<h2>Buy ideas</h2>'+(d.ideas.map(x=>'<div class="card"><b>'+esc(x.symbol)+'</b> <small>'+esc(x.market)+' • '+esc(x.name)+'</small><p>'+esc(x.price)+' • <b>'+esc(x.action)+'</b></p><span class="badge '+(x.safety_status==="PASS"?"pass":"block")+'">'+esc(x.safety_status)+'</span> <span class="badge">'+esc(x.setup_grade)+'</span><p>Score '+esc(x.technical_score)+' • R:R '+esc(x.rr)+'</p><p><span class="badge '+freshClass(x.price_age_sec,180)+'">price '+age(x.price_age_sec)+'</span> <span class="badge '+freshClass(x.signal_age_sec,1800)+'">signal '+age(x.signal_age_sec)+'</span></p><small>'+esc(x.validation_status)+' • '+esc(x.data_status)+'<br>'+esc(x.reason)+'</small></div>').join("")||'<div class="card">No validated ideas yet.</div>');
    } else if(tab==="pos"){
      const d=await api("/api/positions");
      app.innerHTML='<h2>My positions</h2>'+(d.positions.map(x=>'<div class="card"><b>'+esc(x.symbol)+'</b> <small>'+esc(x.platform)+' • '+esc(x.market)+'</small><p>Buy '+esc(x.avg_buy)+' → '+esc(x.current_price)+' • P/L '+esc(x.pnl_pct)+'%</p><b>'+esc(x.action)+'</b><p><span class="badge '+freshClass(x.price_age_sec,180)+'">price '+age(x.price_age_sec)+'</span> <span class="badge '+freshClass(x.signal_age_sec,1800)+'">signal '+age(x.signal_age_sec)+'</span></p><small>'+esc(x.data_status)+' • '+esc(x.reason)+'</small></div>').join("")||'<div class="card">No synced positions yet.</div>');
    } else if(tab==="history"){
      const d=await api("/api/history");
      app.innerHTML='<h2>History</h2>'+(d.trades.map(x=>'<div class="card"><b>'+esc(x.symbol)+'</b> <small>'+esc(x.market)+'</small><p>'+esc(x.entry_price)+' → '+esc(x.exit_price)+' • '+esc(x.pnl_pct)+'%</p><small>'+esc(x.exit_reason)+' • '+esc(x.closed_at)+'</small></div>').join("")||'<div class="card">No closed trades yet.</div>');
    }
  }catch{app.innerHTML='<div class="card">Unable to load data. Check private system status.</div>'}
}
async function onOpen(){await lightRefresh(false);await render(currentTab)}
document.querySelectorAll("nav button[data-tab]").forEach(b=>b.onclick=()=>render(b.dataset.tab));
$("#logout").onclick=()=>fetch("/auth/logout",{method:"POST"}).then(()=>location.href="/");
document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")onOpen()});
setInterval(()=>{if(document.visibilityState==="visible")onOpen()},60000);
if("serviceWorker"in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});
onOpen();
</script></body></html>`;

const ICON=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="96" fill="#0f172a"/><path d="M96 350l86-92 67 54 121-144" fill="none" stroke="#fff" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/><circle cx="370" cy="168" r="24" fill="#22c55e"/></svg>`;
const SW=`self.addEventListener("install",e=>self.skipWaiting());self.addEventListener("activate",e=>self.clients.claim());self.addEventListener("fetch",()=>{});`;

export default{
  async fetch(req,env){
    const url=new URL(req.url);

    if(url.pathname==="/auth/login" && req.method==="POST"){
      if(!env.OWNER_PASSWORD || !env.SESSION_SECRET) return new Response(loginPage("Private login is not configured."),{status:500,headers:HTML_HEADERS});
      let supplied=""; try{const form=await req.formData(); supplied=String(form.get("password")||"");}catch{}
      if(!(await safeEqualText(supplied,env.OWNER_PASSWORD))) return new Response(loginPage("Invalid password."),{status:401,headers:HTML_HEADERS});
      const session=await makeSession(env);
      return new Response(null,{status:303,headers:{"location":"/","set-cookie":`v10_session=${session}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict`,"cache-control":"no-store"}});
    }
    if(url.pathname==="/auth/logout" && req.method==="POST"){
      return new Response(null,{status:204,headers:{"set-cookie":"v10_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict","cache-control":"no-store"}});
    }

    // Machine write endpoint uses separate long secret and does not require human session.
    if(url.pathname==="/api/ingest") return api(req,env,url);

    const authed=await validSession(req,env);
    if(!authed){
      if(url.pathname.startsWith("/api/")) return json({error:"unauthorized"},401);
      return new Response(loginPage(),{status:200,headers:HTML_HEADERS});
    }

    if(url.pathname.startsWith("/api/")) return api(req,env,url);
    if(url.pathname==="/manifest.webmanifest") return new Response(JSON.stringify(manifest),{headers:{"content-type":"application/manifest+json","cache-control":"no-store"}});
    if(url.pathname==="/icon.svg") return new Response(ICON,{headers:{"content-type":"image/svg+xml","cache-control":"public,max-age=86400"}});
    if(url.pathname==="/sw.js") return new Response(SW,{headers:{"content-type":"application/javascript","cache-control":"no-store"}});
    return new Response(APP_HTML,{headers:HTML_HEADERS});
  },
  async scheduled(event,env,ctx){ctx.waitUntil(refreshLight(env,true))}
};
