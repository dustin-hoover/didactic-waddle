#!/usr/bin/env python3
"""Boat Dock Network — serviceability + member signup portal (self-contained artifact).
Pin-drop serviceability by zone (embedded lake + zones + nodes), plan selection, and a
member / pre-sale deposit / founding-member / host-node signup persisted to the artifact
`db`. Owner sees a live pipeline panel. No CDN, no web fonts.

Publish with: capabilities {"db":{}, "user":{}}.
Usage: python3 make_portal.py <out_html>
"""
import json, os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(REPO, "data", "portal")
lake = open(os.path.join(D, "lake.geojson")).read()
zones = open(os.path.join(D, "zones.geojson")).read()
nodes = open(os.path.join(D, "nodes.geojson")).read()

HTML = f"""<title>Join Boat Dock Network</title>
<style>
:root{{--bg:#eef1f2;--surface:#fff;--ink:#0b1620;--muted:#5a6b75;--line:#d3dde1;
 --water:#bfe0e6;--water-edge:#4f9aa6;--accent:#0e7c8b;--accent2:#eb6834;--gold:#f2b705;
 --p1:#0e7c8b;--p2:#3f8fa6;--p3:#7faebd;--p4:#9bb2bb;--good:#1baf7a;}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0b1116;--surface:#131c22;
 --ink:#e9f1f4;--muted:#93a6b0;--line:#25333b;--water:#123038;--water-edge:#3d7f8c;
 --accent:#2bb3c4;--accent2:#f0904a;--good:#2bb3a0;}}}}
:root[data-theme="dark"]{{--bg:#0b1116;--surface:#131c22;--ink:#e9f1f4;--muted:#93a6b0;--line:#25333b;
 --water:#123038;--water-edge:#3d7f8c;--accent:#2bb3c4;--accent2:#f0904a;--good:#2bb3a0;}}
*{{box-sizing:border-box}} html,body{{margin:0}} body{{background:var(--bg);color:var(--ink);
 font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 padding:0 16px calc(40px + env(safe-area-inset-bottom));line-height:1.5}}
.wrap{{max-width:860px;margin:0 auto}}
.hero{{padding:calc(34px + env(safe-area-inset-top)) 0 14px}}
.eyebrow{{font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent)}}
h1{{font-size:clamp(28px,5.5vw,44px);line-height:1.05;margin:8px 0 10px;letter-spacing:-.02em;text-wrap:balance}}
.lede{{font-size:clamp(15px,2vw,18px);color:var(--muted);max-width:60ch;margin:0}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}}
.card h2{{margin:0 0 4px;font-size:19px}} .step{{font-family:ui-monospace,monospace;font-size:12px;color:var(--accent);letter-spacing:.06em}}
.hint{{color:var(--muted);font-size:13px;margin:2px 0 12px}}
canvas{{width:100%;height:340px;display:block;border:1px solid var(--line);border-radius:12px;background:var(--bg);cursor:crosshair;touch-action:none}}
.row{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
select,input,textarea{{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:9px 11px;width:100%}}
label.fld{{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px;text-transform:uppercase;letter-spacing:.04em}}
.result{{margin-top:12px;padding:14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);display:none}}
.result.show{{display:block}} .result .big{{font-size:20px;font-weight:700}}
.badge{{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:20px;margin-left:6px}}
.b1{{background:#0e7c8b22;color:var(--accent)}} .b2{{background:#3f8fa622;color:var(--accent)}}
.b3{{background:#9bb2bb33;color:var(--muted)}} .b4{{background:#9bb2bb22;color:var(--muted)}}
.plans{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.plan{{border:1px solid var(--line);border-radius:12px;padding:12px;cursor:pointer;background:var(--surface);text-align:left}}
.plan.sel{{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}}
.plan b{{display:block;font-size:15px}} .plan .sp{{display:block;color:var(--muted);font-size:12px;margin:3px 0 7px}} .plan .pr{{display:block;font-weight:700;font-size:17px}}
.opts{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px}}
.opt{{display:flex;gap:9px;align-items:flex-start;border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer}}
.opt input{{width:auto;margin-top:2px}} .opt b{{font-size:13px}} .opt span{{display:block;color:var(--muted);font-size:12px}}
.cta{{margin-top:14px;background:var(--accent);color:#fff;border:none;border-radius:11px;padding:13px 18px;font-size:16px;font-weight:700;cursor:pointer;width:100%}}
.cta:disabled{{opacity:.5;cursor:not-allowed}}
.note{{color:var(--muted);font-size:12px;margin-top:10px}}
.ok{{display:none;background:#1baf7a18;border:1px solid var(--good);border-radius:12px;padding:14px;margin-top:12px}}
.ok.show{{display:block}}
.admin{{display:none}} .admin.show{{display:block}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0}}
.tile{{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:9px}} .tile b{{display:block;font-size:18px;font-variant-numeric:tabular-nums}} .tile span{{font-size:10px;color:var(--muted);text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase}}
.wake{{background:linear-gradient(180deg,transparent,#f2b70510);border:1px solid var(--line);border-radius:12px;padding:12px;margin-top:10px;font-size:13px;color:var(--muted)}}
.wake b{{color:var(--ink)}}
@media (max-width:680px){{.plans{{grid-template-columns:1fr 1fr}} .opts{{grid-template-columns:1fr}} .tiles{{grid-template-columns:1fr 1fr}}}}
</style>
<div class="wrap">
<div class="hero">
  <div class="eyebrow">Beaver Lake, Arkansas · a member-owned network</div>
  <h1>Gigabit to your dock — and a real say in the network</h1>
  <p class="lede">Boat Dock Network is a cooperative bringing fiber-and-wireless gigabit to the whole
  lake. Check your spot, pick a plan, and reserve your place. Members earn a voice (and help fund
  the build) — no waiting on the government.</p>
</div>

<div class="card">
  <div class="step">STEP 1</div><h2>Find your place on the lake</h2>
  <p class="hint">Click the map where your home or dock is — or pick your area below.</p>
  <canvas id="cv"></canvas>
  <label class="fld" for="zsel">…or choose your area</label>
  <select id="zsel"><option value="">Select a zone…</option></select>
  <div class="result" id="result"></div>
</div>

<div class="card" id="planCard" style="opacity:.55;pointer-events:none">
  <div class="step">STEP 2</div><h2>Choose your plan</h2>
  <p class="hint">Symmetric speeds, no data caps. Final availability confirmed at survey.</p>
  <div class="plans" id="plans"></div>
</div>

<div class="card" id="joinCard" style="opacity:.55;pointer-events:none">
  <div class="step">STEP 3</div><h2>Reserve your spot &amp; join</h2>
  <div class="row"><div style="flex:1;min-width:220px"><label class="fld">Name</label><input id="f_name" autocomplete="name"></div>
    <div style="flex:1;min-width:220px"><label class="fld">Email</label><input id="f_email" type="email" autocomplete="email"></div></div>
  <div class="row"><div style="flex:1;min-width:220px"><label class="fld">Phone (optional)</label><input id="f_phone" autocomplete="tel"></div>
    <div style="flex:2;min-width:220px"><label class="fld">Property address / dock</label><input id="f_addr" autocomplete="street-address"></div></div>
  <label class="fld">I want to…</label>
  <div class="opts">
    <label class="opt"><input type="checkbox" id="o_presale" checked><span><b>Reserve my spot — $100</b>a refundable deposit, credited to your first bill, that funds your zone</span></label>
    <label class="opt"><input type="checkbox" id="o_member" checked><span><b>Become a member — $200</b>a refundable co-op share; starts your WAKE voting units</span></label>
    <label class="opt"><input type="checkbox" id="o_founding"><span><b>Be a founding member</b>early risk capital from lakeshore supporters
      <select id="f_tier" style="margin-top:6px;width:auto"><option value="500">$500</option><option value="1500">$1,500</option><option value="5000">$5,000</option></select></span></label>
    <label class="opt"><input type="checkbox" id="o_host"><span><b>Host a node</b>put a dish/cabinet on my property for 1.5&times; WAKE + a discount</span></label>
  </div>
  <div id="pledgeSum" class="wake" style="background:linear-gradient(180deg,transparent,#0e7c8b12)"></div>
  <div class="wake"><b>What's WAKE?</b> A non-transferable membership unit — you earn 1 per month as a
  member (1.5&times; if you host a node). It's your vote in the co-op, not a tradable token. Economics come
  from member patronage dividends. <span id="pii"></span></div>
  <button class="cta" id="submit" disabled>Reserve my spot</button>
  <div class="ok" id="ok"></div>
  <div class="note" id="statusNote"></div>
</div>

<div class="card admin" id="adminCard">
  <div class="step">CO-OP ADMIN (owner only)</div><h2>Sign-up pipeline</h2>
  <div class="tiles" id="adminTiles"></div>
  <div style="overflow-x:auto"><table id="adminTbl"><thead><tr><th>When</th><th>Zone</th><th>Plan</th><th>Wants</th><th>Contact</th></tr></thead><tbody></tbody></table></div>
</div>

<div class="card admin" id="campaignCard">
  <div class="step">CAMPAIGN COCKPIT (owner only)</div><h2>Member capital vs the build-gate</h2>
  <div class="tiles" id="capTiles"></div>
  <div id="capMix" class="note" style="margin:2px 0 10px"></div>
  <div style="overflow-x:auto"><table id="capTbl"><thead><tr><th>Zone</th><th>Reservations</th><th>Capital</th><th>Gate ($75/prem)</th><th>Status</th></tr></thead><tbody></tbody></table></div>
  <p class="note">Build-gate (doc 18): a zone releases to construction when reservations &ge; 25% of premises
  <b>and</b> committed capital &ge; premises &times; $75. Deposits &amp; shares are refundable, held in escrow until then.</p>
</div>

<p class="note">Prototype front door for the cooperative. Sign-ups are stored for this artifact's
organization; a public launch uses the secured Boat Dock Network backend (see the repo). Serviceability
is planning-grade from GIS + canopy modeling and confirmed at survey. Not an offer of securities.</p>
</div>

<script>
const LAKE={lake}, ZONES={zones}, NODES={nodes};
const PLANS=[
 {{id:'cove',name:'Cove',sp:'300 Mbps symmetric',pr:'$69/mo'}},
 {{id:'shoreline',name:'Shoreline',sp:'1 Gbps symmetric',pr:'$89/mo'}},
 {{id:'deepwater',name:'Deep Water',sp:'2–5 Gbps (fiber)',pr:'$129–199'}},
 {{id:'business',name:'Business / Marina',sp:'1 Gbps – multi-gig',pr:'$199+'}},
];
const PHASE={{1:['Building now','Phase 1','b1'],2:['Next up','Phase 2','b2'],3:['Planned','Phase 3','b3'],4:['Future (demand-gated)','Phase 4','b4']}};
// member-capital instruments + build-gate dials (doc 18)
const DEPOSIT=100, SHARE=200;
const GATE_PER_PREMISE=75, RES_PCT=0.25, PEAK_NEED=3600000;
let state={{zone:null, plan:null}};

// ---------- map ----------
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
function polys(g){{return !g?[]:g.type==='Polygon'?g.coordinates:g.type==='MultiPolygon'?g.coordinates.flat():[];}}
let bb={{minx:1e9,miny:1e9,maxx:-1e9,maxy:-1e9}};
for(const r of polys(LAKE.type?LAKE:LAKE.geometry||LAKE)) for(const[x,y] of r){{bb.minx=Math.min(bb.minx,x);bb.maxx=Math.max(bb.maxx,x);bb.miny=Math.min(bb.miny,y);bb.maxy=Math.max(bb.maxy,y);}}
const lat0=(bb.miny+bb.maxy)/2, kx=Math.cos(lat0*Math.PI/180);
let DPR=1,W=0,H=0,base=1;
function fit(){{DPR=Math.max(1,devicePixelRatio||1);W=cv.clientWidth;H=cv.clientHeight;cv.width=W*DPR;cv.height=H*DPR;
 base=Math.min(W/((bb.maxx-bb.minx)*kx),H/(bb.maxy-bb.miny))*0.92;draw();}}
const sx=x=>( (x*kx)-((bb.minx*kx+bb.maxx*kx)/2))*base + W/2;
const sy=y=>(-y-(-(bb.miny)-(bb.maxy))/2)*base + H/2;
const cssv=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function pcol(p){{return p===1?cssv('--p1'):p===2?cssv('--p2'):p===3?'#7faebd':'#9bb2bb';}}
function drawGeom(g){{for(const r of polys(g)){{ctx.beginPath();r.forEach(([x,y],i)=>{{const X=sx(x),Y=sy(y);i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);}});ctx.closePath();ctx.fill();ctx.stroke();}}}}
let pin=null;
function draw(){{ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);
 ctx.fillStyle=cssv('--water');ctx.strokeStyle=cssv('--water-edge');ctx.lineWidth=1;drawGeom(LAKE.type?LAKE:LAKE.geometry||LAKE);
 ctx.lineWidth=1;
 for(const f of ZONES.features){{const sel=state.zone&&f.properties.zone_id===state.zone.zone_id;const c=pcol(f.properties.phase);
   ctx.fillStyle=c+(sel?'55':'22');ctx.strokeStyle=sel?cssv('--accent2'):c;ctx.lineWidth=sel?2:1;drawGeom(f.geometry);}}
 for(const f of NODES.features){{const[x,y]=f.geometry.coordinates;ctx.beginPath();ctx.arc(sx(x),sy(y),3,0,7);ctx.fillStyle=cssv('--gold')||'#f2b705';ctx.fill();ctx.strokeStyle='#0a1319';ctx.lineWidth=.8;ctx.stroke();}}
 if(pin){{ctx.beginPath();ctx.arc(sx(pin[0]),sy(pin[1]),6,0,7);ctx.fillStyle=cssv('--accent2');ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();}}}}
function invLon(px){{return ( (px-W/2)/base + (bb.minx*kx+bb.maxx*kx)/2 )/kx;}}
function invLat(py){{return -((py-H/2)/base + (-(bb.miny)-(bb.maxy))/2);}}
function pip(lon,lat,g){{let inside=false;for(const r of polys(g)){{for(let i=0,j=r.length-1;i<r.length;j=i++){{const xi=r[i][0],yi=r[i][1],xj=r[j][0],yj=r[j][1];if(((yi>lat)!=(yj>lat))&&(lon<(xj-xi)*(lat-yi)/(yj-yi)+xi))inside=!inside;}}}}return inside;}}
function pick(px,py){{const lon=invLon(px),lat=invLat(py);
 for(const f of ZONES.features){{if(pip(lon,lat,f.geometry)){{pin=[lon,lat];selectZone(f.properties);return;}}}}
 // not inside a zone: choose nearest zone centroid
 let best=null,bd=1e9;for(const f of ZONES.features){{let cx=0,cy=0,n=0;for(const r of polys(f.geometry))for(const[x,y] of r){{cx+=x;cy+=y;n++;}}cx/=n;cy/=n;const d=(cx-lon)**2+(cy-lat)**2;if(d<bd){{bd=d;best=f.properties;}}}}
 pin=[lon,lat];selectZone(best,true);}}
cv.addEventListener('click',e=>{{const r=cv.getBoundingClientRect();pick(e.clientX-r.left,e.clientY-r.top);}});

function nearestNode(lon,lat){{let best=null,bd=1e9;for(const f of NODES.features){{const[x,y]=f.geometry.coordinates;const d=((x-lon)*kx)**2+(y-lat)**2;if(d<bd){{bd=d;best=f.properties;}}}}return best;}}
function selectZone(p,approx){{state.zone=p;const[ph,lbl,cls]=PHASE[p.phase]||PHASE[4];
 const medium = p.pct_los>=80?'mostly fixed wireless, fiber where dense':p.pct_los>=60?'a mix of wireless + fiber/relay':'fiber & relays for many homes (tree-heavy)';
 const nn=pin?nearestNode(pin[0],pin[1]):null;
 document.getElementById('result').className='result show';
 document.getElementById('result').innerHTML=
   '<div class="big">'+p.name+' <span class="badge '+cls+'">'+ph+' · '+lbl+'</span></div>'+
   '<div style="color:var(--muted);font-size:13px;margin-top:4px">'+p.county+' County'+(approx?' (nearest area to your pin)':'')+
   ' · about '+Number(p.premises).toLocaleString()+' premises in your zone</div>'+
   '<div style="margin-top:8px">Likely service here: <b>'+medium+'</b> ('+ (p.pct_los??'~') +'% clear wireless line-of-sight through the trees).'+
   (nn?' Nearest planned node: <b>#'+nn.priority+'</b>.':'')+'</div>';
 // fill zone dropdown selection
 document.getElementById('zsel').value=p.zone_id;
 unlock(); draw();
}}
// dropdown
const zsel=document.getElementById('zsel');
ZONES.features.slice().sort((a,b)=>a.properties.name.localeCompare(b.properties.name)).forEach(f=>{{const o=document.createElement('option');o.value=f.properties.zone_id;o.textContent=f.properties.name+' ('+f.properties.county+')';zsel.appendChild(o);}});
zsel.addEventListener('change',e=>{{const f=ZONES.features.find(z=>z.properties.zone_id===e.target.value);if(f){{let cx=0,cy=0,n=0;for(const r of polys(f.geometry))for(const[x,y] of r){{cx+=x;cy+=y;n++;}}pin=[cx/n,cy/n];selectZone(f.properties);}}}});

// plans
const plansEl=document.getElementById('plans');
PLANS.forEach(p=>{{const d=document.createElement('button');d.className='plan';d.type='button';d.dataset.id=p.id;
 d.innerHTML='<b>'+p.name+'</b><span class="sp">'+p.sp+'</span><span class="pr">'+p.pr+'</span>';
 d.onclick=()=>{{state.plan=p.id;[...plansEl.children].forEach(c=>c.classList.toggle('sel',c.dataset.id===p.id));checkReady();}};plansEl.appendChild(d);}});

function unlock(){{document.getElementById('planCard').style.opacity=1;document.getElementById('planCard').style.pointerEvents='auto';
 document.getElementById('joinCard').style.opacity=1;document.getElementById('joinCard').style.pointerEvents='auto';checkReady();}}
function checkReady(){{const ok=state.zone&&state.plan&&document.getElementById('f_name').value.trim()&&document.getElementById('f_email').value.trim();
 document.getElementById('submit').disabled=!ok;}}
['f_name','f_email'].forEach(id=>document.getElementById(id).addEventListener('input',checkReady));

// ---------- member-capital pledges (doc 18) ----------
function pledgeItems(){{
  const it=[];
  if(document.getElementById('o_presale').checked) it.push({{kind:'reservation_deposit',amount:DEPOSIT}});
  if(document.getElementById('o_member').checked)  it.push({{kind:'membership_share',amount:SHARE}});
  if(document.getElementById('o_founding').checked) it.push({{kind:'founding_capital',amount:+document.getElementById('f_tier').value}});
  return it;
}}
const KLBL={{reservation_deposit:'deposit',membership_share:'share',founding_capital:'founding capital'}};
function updatePledge(){{
  const items=pledgeItems(), tot=items.reduce((s,i)=>s+i.amount,0), el=document.getElementById('pledgeSum');
  el.innerHTML = tot
    ? '<b>Your commitment today: $'+tot.toLocaleString()+'</b> — '+
      items.map(i=>'$'+i.amount.toLocaleString()+' '+KLBL[i.kind]).join(' + ')+
      '. Deposits &amp; shares are refundable, held in escrow until your zone\\'s build-gate clears.'
    : 'No paid commitment selected — you\\'ll join the interest list for your zone.';
  const b=document.getElementById('submit');
  if(!b.disabled||b.textContent==='Reserve my spot'||b.textContent.startsWith('Reserve &'))
    b.textContent = tot? 'Reserve & commit $'+tot.toLocaleString() : 'Join the list';
}}
['o_presale','o_member','o_founding','f_tier'].forEach(id=>document.getElementById(id).addEventListener('change',updatePledge));
updatePledge();

// ---------- capabilities ----------
let DB=null, USER=null;
(async()=>{{
  try{{ DB = window.claude && claude.use ? await claude.use('db') : null; }}catch(e){{ DB=null; }}
  try{{ USER = window.claude && claude.use ? await claude.use('user') : null; }}catch(e){{ USER=null; }}
  const note=document.getElementById('statusNote');
  if(!DB){{ note.textContent='Sign-up service is read-only in this view — your selections won\\'t be saved. Open the shared co-op link to reserve.'; }}
  document.getElementById('pii').textContent = DB? 'Your contact info is stored securely for the cooperative.':'';
  // owner pipeline
  try{{ if(USER && USER.isOwner && USER.isOwner() && DB){{ initAdmin(); }} }}catch(e){{}}
}})();

document.getElementById('submit').addEventListener('click', async ()=>{{
  const btn=document.getElementById('submit'); const note=document.getElementById('statusNote');
  const rec={{
    ts:new Date().toISOString(), zone_id:state.zone.zone_id, zone_name:state.zone.name,
    county:state.zone.county, phase:state.zone.phase, plan:state.plan,
    name:document.getElementById('f_name').value.trim(),
    email:document.getElementById('f_email').value.trim(),
    phone:document.getElementById('f_phone').value.trim(),
    address:document.getElementById('f_addr').value.trim(),
    presale:document.getElementById('o_presale').checked, member:document.getElementById('o_member').checked,
    founding:document.getElementById('o_founding').checked, host:document.getElementById('o_host').checked,
  }};
  const items=pledgeItems(); const tot=items.reduce((s,i)=>s+i.amount,0);
  rec.pledge_total_usd=tot;
  btn.disabled=true; btn.textContent='Saving…';
  try{{
    if(!DB) throw {{code:'not_granted'}};
    const ref=await DB.collection('signups').add(rec);
    const sid=(ref&&ref.id)||null;
    // one pledge record per selected capital instrument (doc 18); production
    // Stripe flow (software/api/capital.py) flips these to 'collected' on payment.
    for(const it of items){{
      await DB.collection('pledges').add({{
        ts:new Date().toISOString(), signup_ref:sid,
        zone_id:rec.zone_id, zone_name:rec.zone_name,
        premises:Number(state.zone.premises)||null,
        kind:it.kind, amount_usd:it.amount, status:'committed', refundable:true,
        name:rec.name, email:rec.email
      }});
    }}
    document.getElementById('ok').className='ok show';
    document.getElementById('ok').innerHTML='<b>You\\'re on the list for '+rec.zone_name+'.</b>'+
      (tot?' Your $'+tot.toLocaleString()+' commitment is recorded — we\\'ll send a secure payment link and hold it in escrow until your zone\\'s build-gate clears.':'')+
      ' We\\'ll confirm serviceability at survey and reach out about '+
      (rec.founding?'founding membership and ':'')+'your reservation. Welcome to the co-op. 🚤';
    btn.textContent=tot?'Committed ✓':'On the list ✓'; note.textContent='';
  }}catch(err){{
    btn.disabled=false; btn.textContent='Reserve my spot'; updatePledge();
    note.textContent = (err&&err.code==='not_granted')
      ? 'This preview can\\'t save sign-ups. Email hello@boatdock.network and we\\'ll reserve your spot.'
      : 'Something went wrong saving that — please try again in a moment.';
  }}
}});

// ---------- owner pipeline (subscribe once) ----------
function initAdmin(){{
  const card=document.getElementById('adminCard'); card.className='admin card show';
  const tiles=document.getElementById('adminTiles'); const tb=document.querySelector('#adminTbl tbody');
  try{{
    DB.collection('signups').orderBy('ts','desc').limit(500).onSnapshot(snap=>{{
      const rows=snap.docs.map(d=>d.data()).filter(Boolean);
      const total=rows.length, presale=rows.filter(r=>r.presale).length, founding=rows.filter(r=>r.founding).length, host=rows.filter(r=>r.host).length;
      tiles.innerHTML=[['Total',total],['Reservations',presale],['Founding',founding],['Host offers',host]]
        .map(([k,v])=>'<div class="tile"><b>'+v+'</b><span>'+k+'</span></div>').join('');
      tb.innerHTML=rows.slice(0,60).map(r=>{{const wants=[r.presale&&'reserve',r.member&&'member',r.founding&&'founding',r.host&&'host'].filter(Boolean).join(', ');
        const when=(r.ts||'').slice(0,10);
        return '<tr><td>'+when+'</td><td>'+(r.zone_name||'')+'</td><td>'+(r.plan||'')+'</td><td>'+wants+'</td><td>'+(r.name||'')+'<br><span style="color:var(--muted)">'+(r.email||'')+'</span></td></tr>';}}).join('')
        || '<tr><td colspan="5" style="color:var(--muted)">No sign-ups yet.</td></tr>';
    }}, err=>{{ /* terminal db error: leave panel as-is */ }});
  }}catch(e){{}}
  // campaign cockpit: capital vs the build-gate, per zone (doc 18 §5)
  try{{
    DB.collection('pledges').limit(2000).onSnapshot(snap=>{{
      renderCockpit(snap.docs.map(d=>d.data()).filter(Boolean));
    }}, err=>{{}});
  }}catch(e){{}}
}}

function renderCockpit(pls){{
  document.getElementById('campaignCard').className='admin card show';
  const byZone={{}};
  ZONES.features.forEach(f=>{{const p=f.properties;byZone[p.zone_id]={{name:p.name,premises:Number(p.premises)||0,cap:0,res:0}};}});
  let totCap=0,totDep=0,totSh=0,totFnd=0;
  for(const p of pls){{
    const amt=Number(p.amount_usd)||0; totCap+=amt; const z=byZone[p.zone_id];
    if(z) z.cap+=amt;
    if(p.kind==='reservation_deposit'){{ totDep+=amt; if(z) z.res++; }}
    else if(p.kind==='membership_share') totSh+=amt;
    else if(p.kind==='founding_capital') totFnd+=amt;
  }}
  const gateMet=z=>z.premises&&z.res>=Math.ceil(z.premises*RES_PCT)&&z.cap>=z.premises*GATE_PER_PREMISE;
  const nMet=Object.values(byZone).filter(gateMet).length;
  document.getElementById('capTiles').innerHTML=[
    ['$'+Math.round(totCap).toLocaleString(),'Capital committed'],
    [(100*totCap/PEAK_NEED).toFixed(1)+'%','of $3.6M peak need'],
    [nMet,'Zones at build-gate'],
    ['$'+Math.round(totDep+totSh).toLocaleString(),'Refundable (dep+share)']
  ].map(([v,k])=>'<div class="tile"><b>'+v+'</b><span>'+k+'</span></div>').join('');
  document.getElementById('capMix').innerHTML='Funding mix — deposits $'+Math.round(totDep).toLocaleString()+
    ' · shares $'+Math.round(totSh).toLocaleString()+' · founding $'+Math.round(totFnd).toLocaleString()+'.';
  const rows=Object.values(byZone).filter(z=>z.cap>0||z.res>0).sort((a,b)=>b.cap-a.cap);
  document.querySelector('#capTbl tbody').innerHTML = rows.map(z=>{{
    const rt=Math.ceil(z.premises*RES_PCT), gt=z.premises*GATE_PER_PREMISE, met=gateMet(z);
    return '<tr><td>'+z.name+'</td><td>'+z.res+' / '+rt+'</td><td>$'+Math.round(z.cap).toLocaleString()+
      '</td><td>$'+Math.round(gt).toLocaleString()+'</td><td>'+
      (met?'<b style="color:var(--good)">GATE MET</b>':'building demand')+'</td></tr>';
  }}).join('') || '<tr><td colspan="5" style="color:var(--muted)">No pledges yet.</td></tr>';
}}

addEventListener('resize',fit); fit();
</script>
"""
open(sys.argv[1], "w").write(HTML)
print(f"wrote {sys.argv[1]} ({len(HTML)//1024} KB)")
