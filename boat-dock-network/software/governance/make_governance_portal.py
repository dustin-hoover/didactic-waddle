#!/usr/bin/env python3
"""Boat Dock Network — cooperative governance portal (self-contained artifact).

Makes doc 16 tangible for members: see your WAKE voice, read open proposals, and vote
Snapshot-style with tenure-weighted, anti-whale-capped weight. Owner (admin) creates and
opens/closes proposals and seeds member units for demos. Persisted to the artifact `db`;
identity via the `user` capability. No CDN, no web fonts.

Production truth lives in software/api/governance.py + governance_schema.sql (the WAKE
ledger, monthly accrual, forfeiture/redistribution). This artifact is the member UI /
prototype; in production units come from the ledger, not the seed panel.

Publish with: capabilities {"db":{}, "user":{}}.
Usage: python3 make_governance_portal.py <out_html>
"""
import sys

HTML = r"""<title>Boat Dock Network — Vote</title>
<style>
:root{--bg:#eef1f2;--surface:#fff;--ink:#0b1620;--muted:#5a6b75;--line:#d3dde1;
 --accent:#0e7c8b;--accent2:#eb6834;--gold:#f2b705;--good:#1baf7a;--bad:#d95926;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0b1116;--surface:#131c22;
 --ink:#e9f1f4;--muted:#93a6b0;--line:#25333b;--accent:#2bb3c4;--accent2:#f0904a;--good:#2bb3a0;--bad:#f0904a;}}
:root[data-theme="dark"]{--bg:#0b1116;--surface:#131c22;--ink:#e9f1f4;--muted:#93a6b0;--line:#25333b;
 --accent:#2bb3c4;--accent2:#f0904a;--good:#2bb3a0;--bad:#f0904a;}
*{box-sizing:border-box} html,body{margin:0} body{background:var(--bg);color:var(--ink);
 font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 padding:0 16px calc(40px + env(safe-area-inset-bottom));line-height:1.5}
.wrap{max-width:820px;margin:0 auto}
.hero{padding:calc(34px + env(safe-area-inset-top)) 0 10px}
.eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent)}
h1{font-size:clamp(26px,5vw,40px);line-height:1.05;margin:8px 0 8px;letter-spacing:-.02em}
.lede{font-size:clamp(15px,2vw,17px);color:var(--muted);max-width:62ch;margin:0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}
.card h2{margin:0 0 4px;font-size:19px}
.hint{color:var(--muted);font-size:13px;margin:2px 0 10px}
.you{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.you .t{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px}
.you .t b{display:block;font-size:24px;font-variant-numeric:tabular-nums} .you .t span{font-size:11px;color:var(--muted);text-transform:uppercase}
.prop{border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0;background:var(--surface)}
.prop h3{margin:0 0 2px;font-size:17px} .prop .meta{color:var(--muted);font-size:12px;margin-bottom:8px}
.chip{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:6px}
.c-open{background:#1baf7a22;color:var(--good)} .c-draft{background:#9bb2bb33;color:var(--muted)}
.c-passed{background:#0e7c8b22;color:var(--accent)} .c-failed{background:#d9592622;color:var(--bad)}
.body{font-size:14px;margin:6px 0 10px;white-space:pre-wrap}
.bars{margin:10px 0}
.bar{height:10px;border-radius:6px;background:var(--bg);overflow:hidden;margin:5px 0;border:1px solid var(--line)}
.bar>i{display:block;height:100%}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted);flex-wrap:wrap}
.legend b{color:var(--ink);font-variant-numeric:tabular-nums}
.vote{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.vote button{flex:1;min-width:96px;border:1px solid var(--line);background:var(--surface);color:var(--ink);
 border-radius:10px;padding:10px;font:inherit;font-weight:700;cursor:pointer}
.vote button.sel[data-c=for]{border-color:var(--good);box-shadow:0 0 0 1px var(--good)}
.vote button.sel[data-c=against]{border-color:var(--bad);box-shadow:0 0 0 1px var(--bad)}
.vote button.sel[data-c=abstain]{border-color:var(--muted);box-shadow:0 0 0 1px var(--muted)}
.status{font-size:12px;margin-top:8px}
.pass{color:var(--good);font-weight:700} .fail{color:var(--bad);font-weight:700}
label.fld{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px;text-transform:uppercase;letter-spacing:.04em}
input,textarea,select{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:9px 11px;width:100%}
.row{display:flex;gap:10px;flex-wrap:wrap} .row>div{flex:1;min-width:140px}
.btn{background:var(--accent);color:#fff;border:none;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer;font:inherit}
.btn.sm{padding:7px 11px;font-size:13px} .btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.admin{display:none} .admin.show{display:block}
table{width:100%;border-collapse:collapse;font-size:13px} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)} th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase}
.wake{background:linear-gradient(180deg,transparent,#f2b70510);border:1px solid var(--line);border-radius:12px;padding:12px;margin-top:10px;font-size:13px;color:var(--muted)} .wake b{color:var(--ink)}
.note{color:var(--muted);font-size:12px;margin-top:10px}
@media (max-width:640px){.you{grid-template-columns:1fr 1fr}}
</style>
<div class="wrap">
<div class="hero">
  <div class="eyebrow">Beaver Lake, Arkansas · member-owned</div>
  <h1>Your voice in the co-op</h1>
  <p class="lede">Boat Dock Network is governed by its members. You earn <b>WAKE</b> — one
  voting unit per month you're a member (1.5&times; if you host a node) — and vote on how the
  network is built and run. Not a tradable token; you can't buy votes.</p>
</div>

<div class="card">
  <h2>Your WAKE</h2>
  <p class="hint" id="whoNote">Identifying you…</p>
  <div class="you">
    <div class="t"><b id="myUnits">—</b><span>WAKE units</span></div>
    <div class="t"><b id="myWeight">—</b><span>Voting weight</span></div>
    <div class="t"><b id="myShare">—</b><span>Share of vote</span></div>
  </div>
  <div class="wake"><b>How weight works.</b> Weight = 1 + your units (capped at 120 ≈ 10
  years), then no member may exceed the greater of <b>2%</b> or one equal share of the total
  — so tenure counts but no whale can capture the vote (doc 16).</div>
</div>

<div class="card">
  <h2>Proposals</h2>
  <p class="hint">Open proposals are live — cast or change your vote until they close.</p>
  <div id="props"></div>
</div>

<div class="card admin" id="adminCard">
  <h2>Steward tools (owner only)</h2>
  <p class="hint">Create and run proposals. Seed member units for a demo — in production
  units come from the WAKE ledger (accrual/forfeiture), not here.</p>
  <label class="fld">Title</label><input id="p_title" placeholder="e.g. Build War Eagle zone next">
  <label class="fld">Details</label><textarea id="p_body" rows="3" placeholder="What members are deciding, and why."></textarea>
  <div class="row">
    <div><label class="fld">Category</label>
      <select id="p_cat"><option>build_priority</option><option>pricing</option><option>host_terms</option><option>surplus</option><option>bylaw</option></select></div>
    <div><label class="fld">Quorum %</label><input id="p_quorum" type="number" value="15"></div>
    <div><label class="fld">Pass % (66.7 for bylaws)</label><input id="p_pass" type="number" value="50"></div>
    <div><label class="fld">Days open</label><input id="p_days" type="number" value="7"></div>
  </div>
  <button class="btn" id="p_create" style="margin-top:12px">Create proposal (draft)</button>
  <hr style="border:none;border-top:1px solid var(--line);margin:16px 0">
  <h2 style="font-size:16px">Member roster &amp; units (demo seed)</h2>
  <div class="row"><div><label class="fld">Member email/key</label><input id="m_key" placeholder="member@email"></div>
    <div><label class="fld">Name</label><input id="m_name"></div>
    <div><label class="fld">Units</label><input id="m_units" type="number" value="0"></div>
    <div style="flex:.5"><label class="fld">Host?</label><select id="m_host"><option value="0">no</option><option value="1">yes</option></select></div></div>
  <button class="btn ghost sm" id="m_save" style="margin-top:10px">Add / update member</button>
  <div style="overflow-x:auto;margin-top:10px"><table id="rosterTbl"><thead><tr><th>Member</th><th>Units</th><th>Host</th><th>Weight</th></tr></thead><tbody></tbody></table></div>
  <div class="note" id="govStats"></div>
</div>

<p class="note">Prototype governance front-end for the cooperative. Votes + proposals are
stored for this artifact's organization; production runs on the secured DockOS governance
service (WAKE ledger, accrual, redistribution). WAKE is a non-transferable governance unit,
not a security; economics come from member patronage dividends (doc 16).</p>
</div>

<script>
const VOTE_CAP=120, BASE=1, WHALE=0.02;
let DB=null, USER=null, ME=null, myId=null, isOwner=false, enrollTried=false;
let members=[];   // {id,key,name,units,is_host}
let proposals=[]; // {id,...}
let votes=[];     // {id,proposal_ref,member_key,choice,units_at_cast}

const $=id=>document.getElementById(id);
const raw=u=>BASE+Math.min(Number(u)||0,VOTE_CAP);
function clip(map){ // map: key->raw weight ; returns key->clipped
  const ks=Object.keys(map), n=ks.length, tot=ks.reduce((s,k)=>s+map[k],0);
  if(!n||tot<=0) return map;
  const cap=Math.max(WHALE,1/n)*tot; const o={};
  for(const k of ks) o[k]=Math.min(map[k],cap); return o;
}
function activeWeights(){ // clipped weights over all roster members
  const rawm={}; members.forEach(m=>rawm[m.key]=raw(m.units)); return clip(rawm);
}
function myKey(){ return myId; }

// ---------- capabilities (contract 0.2.52) ----------
(async()=>{
  try{ DB = window.claude&&claude.use? await claude.use('db'):null; }catch(e){ DB=null; }
  try{ USER = window.claude&&claude.use? await claude.use('user'):null; }catch(e){ USER=null; }
  try{ ME = USER? await USER.me() : null; }catch(e){ ME=null; }   // me() never null when USER present
  myId = ME? ME.id : null;                                        // opaque per-org id
  isOwner = ME? !!ME.isOwner : false;
  const nm = (ME&&ME.name)||'';
  $('whoNote').textContent = DB
    ? (myId ? ('Signed in'+(nm?' as '+nm:'')+' — you can vote.') : 'You can browse proposals; sign in via the co-op link to vote.')
    : 'Read-only preview — open the shared co-op link to vote.';
  if(isOwner) $('adminCard').className='admin card show';
  if(DB){ subscribe(); } else { renderProps(); }
})();

// auto-enroll the signed-in viewer as a base-vote member (1 vote) once, if new.
// production seeds members + units from the WAKE ledger (governance.py), not here.
function maybeEnroll(){
  if(enrollTried || !DB || !myId) return;
  if(members.some(m=>m.key===myId)){ enrollTried=true; return; }
  enrollTried=true;
  DB.collection('gov_members').add({key:myId, name:(ME&&ME.name)||'', units:0,
    is_host:false, ts:new Date().toISOString()}).catch(()=>{});
}

function subscribe(){
  try{ DB.collection('gov_members').onSnapshot(s=>{members=s.docs.map(d=>({id:d.id,...d.data()})).filter(x=>x&&x.key); maybeEnroll(); renderAll();}, ()=>{});}catch(e){}
  try{ DB.collection('gov_proposals').orderBy('ts','desc').limit(200).onSnapshot(s=>{proposals=s.docs.map(d=>({id:d.id,...d.data()})).filter(Boolean); renderAll();}, ()=>{});}catch(e){}
  try{ DB.collection('gov_votes').limit(5000).onSnapshot(s=>{votes=s.docs.map(d=>({id:d.id,...d.data()})).filter(Boolean); renderAll();}, ()=>{});}catch(e){}
}

function renderAll(){ renderMe(); renderProps(); if(isOwner) renderRoster(); }

function renderMe(){
  const k=myKey(); const me=members.find(m=>m.key===k);
  const units=me?Number(me.units)||0:0;
  const cw=activeWeights(); const tot=Object.values(cw).reduce((s,w)=>s+w,0)||0;
  const myw = me? (cw[k]!=null?cw[k]:raw(units)) : raw(0);
  $('myUnits').textContent = me? units : '0';
  $('myWeight').textContent = myw.toFixed(myw<10?2:0);
  $('myShare').textContent = tot? (100*myw/tot).toFixed(1)+'%' : '—';
}

function tally(pid){
  const cw=activeWeights(); const totActive=Object.values(cw).reduce((s,w)=>s+w,0)||0;
  const agg={for:0,against:0,abstain:0}; let part=0;
  votes.filter(v=>v.proposal_ref===pid).forEach(v=>{ const w=cw[v.member_key]||0; if(w<=0)return; agg[v.choice]=(agg[v.choice]||0)+w; part+=w; });
  const decisive=agg.for+agg.against;
  return {totActive, agg, part, turnout: totActive?100*part/totActive:0,
          approval: decisive?100*agg.for/decisive:0};
}

function renderProps(){
  const box=$('props'); const order={open:0,draft:1,passed:2,failed:3};
  const ps=proposals.slice().sort((a,b)=>(order[a.status]??9)-(order[b.status]??9));
  if(!ps.length){ box.innerHTML='<p class="hint">No proposals yet'+(isOwner?' — create one below.':'.')+'</p>'; return; }
  const k=myKey();
  box.innerHTML=ps.map(p=>{
    const t=tally(p.id); const q=Number(p.quorum_pct)||15, pp=Number(p.pass_pct)||50;
    const my=votes.find(v=>v.proposal_ref===p.id && v.member_key===k);
    const mx=Math.max(t.agg.for,t.agg.against,t.agg.abstain,1);
    const bar=(v,c)=>'<div class="bar"><i style="width:'+(100*v/mx).toFixed(1)+'%;background:'+c+'"></i></div>';
    const quorumMet=t.turnout>=q, willPass=quorumMet&&t.approval>=pp;
    const open=p.status==='open';
    const canVote=DB&&k&&open&&members.some(m=>m.key===k);
    const voteBtns=['for','against','abstain'].map(c=>
      '<button data-c="'+c+'" data-p="'+p.id+'" class="'+(my&&my.choice===c?'sel':'')+'"'+(canVote?'':' disabled')+'>'+c[0].toUpperCase()+c.slice(1)+'</button>').join('');
    const finalTxt = p.status==='passed'?'<span class="pass">PASSED</span>':p.status==='failed'?'<span class="fail">FAILED</span>':'';
    return '<div class="prop">'
      +'<h3>'+esc(p.title)+'<span class="chip c-'+p.status+'">'+p.status.toUpperCase()+'</span></h3>'
      +'<div class="meta">'+(p.category||'')+' · quorum '+q+'% · pass '+pp+'%'+(p.closes_at?' · closes '+(p.closes_at||'').slice(0,10):'')+'</div>'
      +(p.body?'<div class="body">'+esc(p.body)+'</div>':'')
      +'<div class="bars">'+bar(t.agg.for,'var(--good)')+bar(t.agg.against,'var(--bad)')+bar(t.agg.abstain,'var(--muted)')+'</div>'
      +'<div class="legend"><span>For <b>'+t.agg.for.toFixed(1)+'</b></span><span>Against <b>'+t.agg.against.toFixed(1)+'</b></span><span>Abstain <b>'+t.agg.abstain.toFixed(1)+'</b></span></div>'
      +'<div class="status">Turnout <b>'+t.turnout.toFixed(1)+'%</b> vs '+q+'% quorum ('+(quorumMet?'met':'not met')+') · Approval <b>'+t.approval.toFixed(1)+'%</b> vs '+pp+'% '
        +(open?('→ '+(willPass?'<span class="pass">passing</span>':'<span class="fail">not passing</span>')):finalTxt)+'</div>'
      +(open?('<div class="vote">'+voteBtns+'</div>'):'')
      +(isOwner?('<div class="vote" style="margin-top:8px">'
          +(p.status==='draft'?'<button class="btn sm" data-open="'+p.id+'">Open voting</button>':'')
          +(open?'<button class="btn sm ghost" data-close="'+p.id+'">Close &amp; finalize</button>':'')+'</div>'):'')
      +'</div>';
  }).join('');
  // wire vote buttons
  box.querySelectorAll('.vote button[data-c]').forEach(b=>b.onclick=()=>castVote(b.dataset.p,b.dataset.c));
  box.querySelectorAll('button[data-open]').forEach(b=>b.onclick=()=>openProp(b.dataset.open));
  box.querySelectorAll('button[data-close]').forEach(b=>b.onclick=()=>closeProp(b.dataset.close));
}

function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

async function castVote(pid,choice){
  const k=myKey(); if(!DB||!k) return;
  const me=members.find(m=>m.key===k); if(!me){ alert('You must be an active member to vote.'); return; }
  const existing=votes.find(v=>v.proposal_ref===pid && v.member_key===k);
  const rec={proposal_ref:pid, member_key:k, choice, units_at_cast:Number(me.units)||0, ts:new Date().toISOString()};
  try{
    if(existing && DB.doc){ await DB.doc('gov_votes/'+existing.id).set(rec); }
    else if(existing && DB.collection){ await DB.collection('gov_votes').doc(existing.id).set(rec); }
    else { await DB.collection('gov_votes').add(rec); }
  }catch(e){ /* fallback: add */ try{ await DB.collection('gov_votes').add(rec); }catch(_){} }
}
async function openProp(pid){ if(!DB) return; const days=7; const closes=new Date(Date.now()+days*864e5).toISOString();
  try{ await docSet('gov_proposals',pid,{status:'open',opens_at:new Date().toISOString(),closes_at:closes}); }catch(e){}
}
async function closeProp(pid){ if(!DB) return; const p=proposals.find(x=>x.id===pid); const t=tally(pid);
  const q=Number(p.quorum_pct)||15, pp=Number(p.pass_pct)||50;
  const passed=(t.turnout>=q)&&(t.approval>=pp);
  try{ await docSet('gov_proposals',pid,{status:passed?'passed':'failed'}); }catch(e){}
}
async function docSet(coll,id,patch){
  // merge-update a doc across possible db shapes
  const cur=(coll==='gov_proposals'?proposals:members).find(x=>x.id===id)||{};
  const merged=Object.assign({},cur,patch); delete merged.id;
  if(DB.doc){ return DB.doc(coll+'/'+id).set(merged); }
  if(DB.collection){ const c=DB.collection(coll); if(c.doc) return c.doc(id).set(merged); }
  throw new Error('no doc setter');
}

$('p_create')&&($('p_create').onclick=async()=>{
  if(!DB) return; const title=$('p_title').value.trim(); if(!title){ $('p_title').focus(); return; }
  const rec={title, body:$('p_body').value.trim(), category:$('p_cat').value,
    quorum_pct:Number($('p_quorum').value)||15, pass_pct:Number($('p_pass').value)||50,
    status:'draft', created_by:myKey()||'owner', ts:new Date().toISOString()};
  try{ await DB.collection('gov_proposals').add(rec); $('p_title').value='';$('p_body').value=''; }catch(e){}
});
$('m_save')&&($('m_save').onclick=async()=>{
  if(!DB) return; const key=$('m_key').value.trim(); if(!key){ $('m_key').focus(); return; }
  const rec={key, name:$('m_name').value.trim()||key, units:Number($('m_units').value)||0, is_host:$('m_host').value==='1', ts:new Date().toISOString()};
  const ex=members.find(m=>m.key===key);
  try{ if(ex){ await docSet('gov_members',ex.id,rec);} else { await DB.collection('gov_members').add(rec);} $('m_key').value='';$('m_name').value='';$('m_units').value='0'; }catch(e){}
});

function renderRoster(){
  const cw=activeWeights(); const tot=Object.values(cw).reduce((s,w)=>s+w,0)||0;
  const tb=document.querySelector('#rosterTbl tbody');
  tb.innerHTML=members.slice().sort((a,b)=>raw(b.units)-raw(a.units)).map(m=>{
    const w=cw[m.key]!=null?cw[m.key]:raw(m.units);
    return '<tr><td>'+esc(m.name||m.key)+'<br><span style="color:var(--muted)">'+esc(m.key)+'</span></td><td>'+(Number(m.units)||0)+'</td><td>'+(m.is_host?'★':'')+'</td><td>'+w.toFixed(w<10?2:0)+'</td></tr>';
  }).join('') || '<tr><td colspan="4" style="color:var(--muted)">No members seeded yet.</td></tr>';
  $('govStats').textContent='Active members: '+members.length+' · total voting weight: '+tot.toFixed(1)+
    ' · anti-whale cap: max(2%, 1 equal share) = '+(tot?(Math.max(WHALE,1/Math.max(members.length,1))*tot).toFixed(1):'—')+' per member.';
}
</script>
"""
open(sys.argv[1], "w").write(HTML)
print(f"wrote {sys.argv[1]} ({len(HTML)//1024} KB)")
