"""Single-page web UI served at ``/`` (no build step, no external assets)."""

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MARS Research</title>
<style>
:root{--bg:#fafafb;--pn:#fff;--fg:#17171c;--mut:#6e6e7a;--bd:#e4e4ea;--ac:#c1440e;--acs:#fdeee7;--ok:#1a8f4c;--wn:#b7791f;--er:#d33;--sh:0 1px 3px rgba(0,0,0,.06)}
@media(prefers-color-scheme:dark){:root{--bg:#0e0e11;--pn:#17171b;--fg:#ececf1;--mut:#9494a0;--bd:#2a2a31;--ac:#ff7a45;--acs:#2a1a12;--ok:#4cc380;--wn:#e0a94a;--er:#ff6b6b;--sh:none}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,sans-serif;display:flex}
aside{width:280px;flex:none;background:var(--pn);border-right:1px solid var(--bd);display:flex;flex-direction:column;height:100vh}
aside header{padding:16px;border-bottom:1px solid var(--bd)}
.logo{font-weight:800;font-size:20px;letter-spacing:.5px}.logo b{color:var(--ac)}
.badge{display:inline-block;margin-top:6px;font-size:12px;color:var(--mut)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--mut);margin-right:6px}.dot.on{background:var(--ok)}.dot.off{background:var(--er)}
#hist{flex:1;overflow:auto;padding:8px}
.h{padding:9px 10px;border-radius:8px;cursor:pointer;font-size:13px;line-height:1.35;border:1px solid transparent}
.h:hover{background:var(--bg)}.h.act{background:var(--acs);border-color:var(--ac)}
.h small{display:block;color:var(--mut);font-size:11px;margin-top:2px}
.h .x{float:right;color:var(--mut);padding:0 4px;display:none}.h:hover .x{display:inline}
aside footer{padding:12px 16px;border-top:1px solid var(--bd)}
button,.btn{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--bd);background:var(--pn);color:var(--fg);padding:8px 14px}
button:hover{border-color:var(--ac)}button.pri{background:var(--ac);border-color:var(--ac);color:#fff;font-weight:600}
button.pri:hover{filter:brightness(1.08)}button:disabled{opacity:.5;cursor:not-allowed}
input[type=password],input[type=text],textarea{width:100%;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px 12px}
textarea:focus,input:focus{outline:2px solid var(--ac);outline-offset:-1px}
main{flex:1;overflow:auto;height:100vh}
.wrap{max-width:860px;margin:0 auto;padding:28px 20px 80px}
.card{background:var(--pn);border:1px solid var(--bd);border-radius:12px;padding:18px;box-shadow:var(--sh);margin-bottom:16px}
.ask textarea{min-height:84px;resize:vertical;border:0;background:transparent;padding:0}.ask textarea:focus{outline:0}
.bar{display:flex;gap:12px;align-items:center;margin-top:10px;flex-wrap:wrap}.bar .sp{flex:1}
label.chk{display:flex;gap:6px;align-items:center;color:var(--mut);font-size:13px;cursor:pointer}
.eg{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.eg button{font-size:13px;color:var(--mut);border-radius:20px;padding:5px 12px}
h2.t{font-size:13px;text-transform:uppercase;letter-spacing:.8px;color:var(--mut);margin:0 0 10px}
.tl{list-style:none;margin:0;padding:0}.tl li{display:flex;gap:10px;padding:6px 0;font-size:14px;border-bottom:1px dashed var(--bd)}.tl li:last-child{border:0}
.tl .ic{width:20px;text-align:center}.tl .nm{font-weight:600;min-width:84px;text-transform:capitalize}.tl .dt{color:var(--mut);flex:1}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--bd);border-top-color:var(--ac);border-radius:50%;animation:s .8s linear infinite}@keyframes s{to{transform:rotate(360deg)}}
.pill{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;border:1px solid var(--bd)}
.pill.complete{color:var(--ok);border-color:var(--ok)}.pill.insufficient_evidence,.pill.rejected{color:var(--wn);border-color:var(--wn)}
.meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px;color:var(--mut);font-size:13px}
.rep h1,.rep h2,.rep h3,.rep h4{line-height:1.3;margin:1.3em 0 .4em}.rep h1{font-size:24px;margin-top:.2em}.rep h2{font-size:19px}.rep h3{font-size:16px}
.rep p{margin:.6em 0}.rep a{color:var(--ac)}.rep code{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:.9em}
.rep blockquote{margin:.8em 0;padding:2px 14px;border-left:3px solid var(--ac);color:var(--mut)}
.rep table{border-collapse:collapse;margin:1em 0;width:100%}.rep td,.rep th{border:1px solid var(--bd);padding:6px 10px;text-align:left}
sup.c{font-size:.75em}sup.c a{text-decoration:none;font-weight:700;padding:0 1px}
details{border-top:1px solid var(--bd);padding:10px 0}details:first-of-type{border:0}
summary{cursor:pointer;font-weight:600}
.src{padding:8px 0;border-bottom:1px solid var(--bd);font-size:14px}.src:last-child{border:0}
.src .n{display:inline-block;min-width:26px;color:var(--ac);font-weight:700}.src q{display:block;color:var(--mut);font-size:13px;margin:3px 0 0 26px;quotes:none}
.src.hl{background:var(--acs);border-radius:6px}
.warn{color:var(--wn)}.err{color:var(--er)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.empty{text-align:center;color:var(--mut);padding:50px 0 10px}.empty h1{color:var(--fg);margin:0 0 6px}
.keyrow{display:flex;gap:6px;margin-top:8px}
@media(max-width:760px){body{flex-direction:column}aside{width:100%;height:auto;max-height:42vh}main{height:auto}}
</style></head><body>
<aside>
 <header><div class="logo"><b>MARS</b> Research</div>
  <div class="badge" id="health"><span class="dot"></span>connecting…</div></header>
 <div style="padding:10px 10px 0"><button style="width:100%" id="new">+ New research</button></div>
 <div id="hist"></div>
 <footer><div style="font-size:12px;color:var(--mut)">API key</div>
  <div class="keyrow"><input type="password" id="key" placeholder="X-API-Key (if required)" autocomplete="off"></div>
  <div style="margin-top:8px;font-size:12px"><a href="/docs" target="_blank" style="color:var(--mut)">API docs ↗</a></div></footer>
</aside>
<main><div class="wrap">
 <div class="card ask">
  <textarea id="q" maxlength="1000" placeholder="What do you want researched?  (Ctrl/⌘ + Enter to run)"></textarea>
  <div class="bar"><label class="chk"><input type="checkbox" id="appr"> Review findings before writing</label>
   <span class="sp"></span><button id="stop" style="display:none">Stop</button><button class="pri" id="go">Research</button></div>
  <div class="eg" id="eg"></div>
 </div>
 <div id="view"></div>
</div></main>
<script>
const $=id=>document.getElementById(id),LS=window.localStorage;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const state={ctl:null,hist:JSON.parse(LS.getItem("mars.hist")||"[]"),cur:null,server:false};
$("key").value=LS.getItem("mars.key")||"";$("key").onchange=()=>{LS.setItem("mars.key",$("key").value);boot()};
const hdr=()=>{const h={"Content-Type":"application/json"};const k=$("key").value.trim();if(k)h["X-API-Key"]=k;return h};
const EG=["What are the latest advances in solid-state batteries?","Compare Rust and Go for backend services","How effective are GLP-1 drugs for long-term weight loss?"];
$("eg").innerHTML=EG.map(e=>`<button>${esc(e)}</button>`).join("");
$("eg").onclick=e=>{if(e.target.tagName=="BUTTON"){$("q").value=e.target.textContent;$("q").focus()}};

/* ---- markdown (escaped; citations [n] -> links to sources) ---- */
function inl(s,cite){s=esc(s).replace(/`([^`]+)`/g,"<code>$1</code>").replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(^|[^*])\*([^*\s][^*]*?)\*/g,"$1<i>$2</i>")
 .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
 if(cite)s=s.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g,(m,ids)=>"<sup class=c>["+ids.split(/\s*,\s*/).map(i=>`<a href="#s${i}" data-s="${i}">${i}</a>`).join(",")+"]</sup>");return s}
function md(t,cite=true){const L=t.split("\n");let h="",ul=false,ol=false,i=0;const close=()=>{if(ul){h+="</ul>";ul=false}if(ol){h+="</ol>";ol=false}};
 while(i<L.length){const l=L[i];let m;
  if(m=l.match(/^(#{1,4})\s+(.*)/)){close();h+=`<h${m[1].length}>${inl(m[2],cite)}</h${m[1].length}>`}
  else if(m=l.match(/^\s*[-*]\s+(.*)/)){if(!ul){close();h+="<ul>";ul=true}h+=`<li>${inl(m[1],cite)}</li>`}
  else if(m=l.match(/^\s*\d+[.)]\s+(.*)/)){if(!ol){close();h+="<ol>";ol=true}h+=`<li>${inl(m[1],cite)}</li>`}
  else if(m=l.match(/^>\s?(.*)/)){close();h+=`<blockquote>${inl(m[1],cite)}</blockquote>`}
  else if(/^\|.*\|\s*$/.test(l)){close();const rows=[];while(i<L.length&&/^\|.*\|\s*$/.test(L[i])){rows.push(L[i]);i++}i--;
   const cells=r=>r.trim().replace(/^\||\|$/g,"").split("|").map(c=>c.trim());let t="<table>";
   rows.filter(r=>!/^\|[\s:|-]+\|$/.test(r)).forEach((r,k)=>{const tag=k?"td":"th";t+="<tr>"+cells(r).map(c=>`<${tag}>${inl(c,cite)}</${tag}>`).join("")+"</tr>"});h+=t+"</table>"}
  else if(l.trim()){close();h+=`<p>${inl(l,cite)}</p>`}else close();i++}
 close();return h}

/* ---- history ---- */
function saveHist(){LS.setItem("mars.hist",JSON.stringify(state.hist.slice(0,40)))}
function renderHist(){$("hist").innerHTML=state.hist.map(h=>`<div class="h ${state.cur===h.id?"act":""}" data-id="${esc(h.id)}"><span class="x" data-del="${esc(h.id)}">✕</span>${esc(h.question.slice(0,90))}<small>${esc(h.status)} · ${new Date(h.at).toLocaleString()}</small></div>`).join("")||'<div style="padding:12px;color:var(--mut);font-size:13px">No research yet.</div>'}
$("hist").onclick=async e=>{const d=e.target.dataset.del;if(d){state.hist=state.hist.filter(h=>h.id!==d);saveHist();if(state.server)fetch("/reports/"+d,{method:"DELETE",headers:hdr()}).catch(()=>{});if(state.cur===d)$("view").innerHTML="";renderHist();return}
 const el=e.target.closest(".h");if(!el)return;const id=el.dataset.id;state.cur=id;renderHist();
 let r=(state.hist.find(h=>h.id===id)||{}).report;
 if(!r&&state.server){try{const x=await fetch("/reports/"+id,{headers:hdr()});if(x.ok)r=await x.json()}catch{}}
 if(r){$("q").value=r.question;showReport(r,id)}else $("view").innerHTML='<div class="card warn">Report not available.</div>'};
$("new").onclick=()=>{state.cur=null;$("q").value="";$("view").innerHTML="";renderHist();$("q").focus()};
function remember(id,r){state.hist=state.hist.filter(h=>h.id!==id);state.hist.unshift({id,question:r.question,status:r.status,at:Date.now(),report:r});saveHist();state.cur=id;renderHist()}

/* ---- rendering ---- */
function showReport(r,id){const c=r.citation_check||{},u=r.usage||{};
 const src=(r.sources||[]).map(s=>`<div class="src" id="s${s.id}"><span class="n">[${s.id}]</span><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--fg)">${esc(s.title||s.url)}</a>${s.published?` <small style="color:var(--mut)">${esc(s.published)}</small>`:""}${(s.quotes||[]).slice(0,2).map(q=>`<q>“${esc(q)}”</q>`).join("")}</div>`).join("");
 const li=a=>a&&a.length?"<ul>"+a.map(x=>`<li>${inl(x,true)}</li>`).join("")+"</ul>":"";
 $("view").innerHTML=`<div class="card"><div class="meta"><span class="pill ${esc(r.status)}">${esc(r.status.replace("_"," "))}</span>
  <span>${(r.sources||[]).length} sources</span><span>${r.drafts||0} draft(s)</span>${c.coverage!=null?`<span>citation coverage ${Math.round((c.coverage||0)*100)}%</span>`:""}
  ${c.invalid_ids&&c.invalid_ids.length?`<span class="err">invalid citations: ${c.invalid_ids.join(", ")}</span>`:""}</div>
  <div class="rep" id="rep">${md(r.markdown||"")}</div>
  <div class="row"><button id="cp">Copy markdown</button><button id="dl">Download .md</button><button id="rr">Re-run</button></div></div>
  <div class="card"><h2 class="t">Details</h2>
  ${(r.warnings||[]).length?`<details open><summary class="warn">Warnings (${r.warnings.length})</summary>${li(r.warnings)}</details>`:""}
  <details open><summary>Sources (${(r.sources||[]).length})</summary>${src||"<p>None.</p>"}</details>
  ${(r.insights||[]).length?`<details><summary>Insights (${r.insights.length})</summary><ul>${r.insights.map(i=>`<li>${inl(i.text)} <small style="color:var(--mut)">${(i.source_ids||[]).map(n=>"["+n+"]").join("")}</small></li>`).join("")}</ul></details>`:""}
  ${(r.contradictions||[]).length?`<details><summary>Contradictions (${r.contradictions.length})</summary>${li(r.contradictions)}</details>`:""}
  ${(r.gaps||[]).length?`<details><summary>Gaps (${r.gaps.length})</summary>${li(r.gaps)}</details>`:""}
  ${(r.errors||[]).length?`<details><summary class="err">Errors (${r.errors.length})</summary>${li(r.errors)}</details>`:""}
  ${Object.keys(u).length?`<details><summary>Usage</summary><pre style="white-space:pre-wrap">${esc(JSON.stringify(u,null,2))}</pre></details>`:""}</div>`;
 $("cp").onclick=()=>{navigator.clipboard.writeText(r.markdown||"");$("cp").textContent="Copied ✓"};
 $("dl").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([r.markdown||""],{type:"text/markdown"}));a.download="report.md";a.click()};
 $("rr").onclick=()=>{$("q").value=r.question;run()};
 $("rep").onclick=e=>{const a=e.target.closest("a[data-s]");if(!a)return;e.preventDefault();const t=$("s"+a.dataset.s);if(t){t.scrollIntoView({behavior:"smooth",block:"center"});t.classList.add("hl");setTimeout(()=>t.classList.remove("hl"),1800)}}}

const NAMES={planner:"Planning",researcher:"Researching",analyst:"Analysing",approval:"Approval",writer:"Writing",critic:"Reviewing",finalize:"Finalising"};
function stepText(e){switch(e.node){
 case"planner":return (e.tasks||[]).length+" search tasks: "+(e.tasks||[]).map(esc).join(" · ");
 case"researcher":return e.error?`<span class=err>${esc(e.error)}</span>`:`${esc(e.task)} — ${e.sources} sources, ${e.pages_read} pages, ${e.claims} claims`+(e.dropped?` (${e.dropped} dropped)`:"");
 case"analyst":return `${e.insights} insights from ${e.sources} sources`+((e.followups||[]).length?`; follow-ups: ${e.followups.map(esc).join(" · ")}`:"");
 case"writer":return "draft "+e.draft;
 case"critic":return e.approved?"approved":"changes requested: "+(e.issues||[]).map(esc).join("; ");
 case"approval":return e.approved?"approved":"rejected";
 case"finalize":return esc(e.status);default:return""}}

function busy(b){$("go").disabled=b;$("stop").style.display=b?"":"none"}
function tlHtml(steps,live){return `<div class="card"><h2 class="t">Progress</h2><ul class="tl">${steps.map(s=>`<li><span class="ic">✓</span><span class="nm">${esc(NAMES[s.node]||s.node)}</span><span class="dt">${stepText(s)}</span></li>`).join("")}
 ${live?`<li><span class="ic"><span class="spin"></span></span><span class="nm">Working…</span><span class="dt">${esc(live)}</span></li>`:""}</ul></div>`}

/* ---- SSE over fetch (needs POST + headers) ---- */
async function sse(url,body,onEv,signal){const r=await fetch(url,{method:"POST",headers:hdr(),body:JSON.stringify(body),signal});
 if(!r.ok){let d={};try{d=await r.json()}catch{}throw new Error(d.detail||d.code||("HTTP "+r.status))}
 const rd=r.body.getReader(),dec=new TextDecoder();let buf="";
 for(;;){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let k;
  while((k=buf.indexOf("\n\n"))>=0){const blk=buf.slice(0,k);buf=buf.slice(k+2);const d=blk.split("\n").find(x=>x.startsWith("data:"));if(d)onEv(JSON.parse(d.slice(5)))}}}

async function stream(url,body,question){
 const steps=[];let tid="";state.ctl=new AbortController();busy(true);
 $("view").innerHTML=tlHtml(steps,"starting");
 try{await sse(url,body,ev=>{
   if(ev.thread_id)tid=ev.thread_id;
   if(ev.event=="step"){steps.push(ev);$("view").innerHTML=tlHtml(steps,"next step")}
   else if(ev.event=="report"){remember(ev.thread_id,ev.report);showReport(ev.report,ev.thread_id)}
   else if(ev.event=="awaiting_approval")showApproval(ev.thread_id,ev.preview,question,steps);
   else if(ev.event=="error")$("view").innerHTML=tlHtml(steps)+`<div class="card err">${esc(ev.detail||ev.code)}</div>`;
  },state.ctl.signal)}
 catch(e){$("view").innerHTML=tlHtml(steps)+(e.name=="AbortError"?'<div class="card warn">Stopped.</div>':`<div class="card err">${esc(e.message)}</div>`)}
 busy(false)}

function showApproval(tid,p,question,steps){
 $("view").innerHTML=tlHtml(steps)+`<div class="card"><h2 class="t">Review before writing</h2><p>${esc(p.message||"")}</p>
 <details open><summary>Insights (${(p.insights||[]).length})</summary><ul>${(p.insights||[]).map(i=>`<li>${inl(i.text)} <small style="color:var(--mut)">${(i.source_ids||[]).map(n=>"["+n+"]").join("")}</small></li>`).join("")}</ul></details>
 ${(p.gaps||[]).length?`<details><summary>Gaps</summary><ul>${p.gaps.map(g=>`<li>${esc(g)}</li>`).join("")}</ul></details>`:""}
 ${(p.contradictions||[]).length?`<details><summary>Contradictions</summary><ul>${p.contradictions.map(g=>`<li>${esc(g)}</li>`).join("")}</ul></details>`:""}
 <details><summary>Sources (${(p.sources||[]).length})</summary>${(p.sources||[]).map(s=>`<div class="src"><span class="n">[${s.id}]</span><a href="${esc(s.url)}" target="_blank" rel="noopener" style="color:var(--fg)">${esc(s.title||s.url)}</a></div>`).join("")}</details>
 <textarea id="fb" placeholder="Optional guidance for the writer…" style="margin-top:12px;min-height:60px"></textarea>
 <div class="row"><button class="pri" id="ap">Approve &amp; write</button><button id="rj">Reject</button></div></div>`;
 const send=a=>{stream("/research/"+tid+"/approve/stream",{approved:a,feedback:$("fb").value},question)};
 $("ap").onclick=()=>send(true);$("rj").onclick=()=>send(false)}

function run(){const q=$("q").value.trim();if(q.length<5){$("q").focus();return}
 state.cur=null;renderHist();stream("/research/stream",{question:q,require_approval:$("appr").checked},q)}
$("go").onclick=run;$("stop").onclick=()=>state.ctl&&state.ctl.abort();
$("q").addEventListener("keydown",e=>{if(e.key=="Enter"&&(e.ctrlKey||e.metaKey)){e.preventDefault();run()}});

async function boot(){const h=$("health");
 try{const r=await fetch("/health");const d=await r.json();h.innerHTML=`<span class="dot on"></span>${esc(d.provider||"ok")} · ${esc(d.search||"")} · ${d.active_runs} active`;
  if(d.storage!=="off"){const x=await fetch("/reports?limit=30",{headers:hdr()});if(x.ok){state.server=true;const list=await x.json();
   const known=new Set(state.hist.map(h=>h.id));list.forEach(s=>{if(!known.has(s.id))state.hist.push({id:s.id,question:s.question,status:s.status,at:Date.parse(s.created_at)||Date.now()})});
   state.hist.sort((a,b)=>b.at-a.at);renderHist()}}}
 catch{h.innerHTML='<span class="dot off"></span>offline'}}
renderHist();boot();
</script></body></html>"""
