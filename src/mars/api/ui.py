"""Single-page web UI served at ``/`` (no build step, no external assets)."""

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MARS Research</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" media="(prefers-color-scheme: light)">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.js"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.0/mermaid.min.js"></script>
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
main{flex:1;display:flex;flex-direction:column;height:100vh;min-height:0;overflow:hidden}
.scroll{flex:1;overflow:auto;min-height:0}
.wrap{max-width:860px;margin:0 auto;padding:28px 20px 24px}
.dock{flex:none;padding:8px 20px 18px;background:linear-gradient(to top,var(--bg) 80%,transparent)}
.dock .in{max-width:860px;margin:0 auto}.dock .card{margin:0;box-shadow:0 2px 14px rgba(0,0,0,.12)}
.dock .hint{text-align:center;font-size:11px;color:var(--mut);margin-top:6px}
.files{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}.files:empty{display:none}
.fc{font-size:12px;border:1px solid var(--bd);border-radius:20px;padding:3px 6px 3px 10px;display:flex;gap:6px;align-items:center;max-width:100%}
.fc span.n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:240px}.fc small{color:var(--mut)}
.fc.ok{border-color:var(--ok)}.fc.dup{border-color:var(--wn)}.fc.bad{border-color:var(--er);color:var(--er)}.fc .x{cursor:pointer;color:var(--mut);padding:0 4px}
button.ic{padding:6px 10px;font-size:16px;line-height:1}
#drop{position:fixed;inset:0;z-index:50;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.55);backdrop-filter:blur(2px)}
#drop div{border:2px dashed var(--ac);border-radius:16px;padding:40px 60px;background:var(--pn);font-size:18px;font-weight:600;text-align:center}
#drop small{display:block;color:var(--mut);font-weight:400;font-size:13px;margin-top:6px}
body.drag #drop{display:flex}
#view:not(:empty)~#hero{display:none}
#hero{text-align:center;padding:12vh 0 0}#hero h1{font-size:28px;margin:0 0 6px}#hero p{color:var(--mut);margin:0}
#hero .eg{justify-content:center;margin-top:22px}
.card{background:var(--pn);border:1px solid var(--bd);border-radius:14px;padding:16px 18px;box-shadow:var(--sh);margin-bottom:16px}
.ask textarea{min-height:28px;max-height:220px;resize:none;border:0;background:transparent;padding:0;display:block}.ask textarea:focus{outline:0}
.bar{display:flex;gap:12px;align-items:center;margin-top:10px;flex-wrap:wrap}.bar .sp{flex:1}
label.chk{display:flex;gap:6px;align-items:center;color:var(--mut);font-size:13px;cursor:pointer}
.eg{display:flex;gap:8px;flex-wrap:wrap}.eg button{font-size:13px;color:var(--mut);border-radius:20px;padding:5px 12px}
h2.t{font-size:13px;text-transform:uppercase;letter-spacing:.8px;color:var(--mut);margin:0 0 10px}
.tl{list-style:none;margin:0;padding:0}.tl li{display:flex;gap:10px;padding:6px 0;font-size:14px;border-bottom:1px dashed var(--bd)}.tl li:last-child{border:0}
.tl .ic{width:20px;text-align:center}.tl .nm{font-weight:600;min-width:84px;text-transform:capitalize}.tl .dt{color:var(--mut);flex:1}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--bd);border-top-color:var(--ac);border-radius:50%;animation:s .8s linear infinite}@keyframes s{to{transform:rotate(360deg)}}
.pill{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;border:1px solid var(--bd)}
.pill.complete{color:var(--ok);border-color:var(--ok)}.pill.insufficient_evidence,.pill.rejected{color:var(--wn);border-color:var(--wn)}
.meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px;color:var(--mut);font-size:13px}
.rep h1,.rep h2,.rep h3,.rep h4{line-height:1.3;margin:1.3em 0 .4em}.rep h1{font-size:24px;margin-top:.2em}.rep h2{font-size:19px}.rep h3{font-size:16px}
.rep p{margin:.6em 0}.rep a{color:var(--ac)}.rep code{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:.9em}
.rep hr{border:0;border-top:1px solid var(--bd);margin:1.4em 0}
.rep .mj.blk{display:block;overflow-x:auto;margin:.9em 0;text-align:center}.rep .mj:not([data-ok]){font-family:ui-monospace,monospace;font-size:.92em;color:var(--mut)}
.viz{margin:1em 0;padding:12px;border:1px solid var(--bd);border-radius:10px;background:var(--pn)}
.viz .vf{margin:0;overflow:auto;font:12px/1.45 ui-monospace,monospace;color:var(--mut)}
.viz .vc{position:relative;height:320px}.viz .vb{text-align:right;margin-top:6px}.viz .svb{font-size:12px;padding:2px 10px;border-radius:6px}
.viz.mermaid[data-ok]{text-align:center;overflow-x:auto}.viz.mermaid svg{max-width:100%;height:auto}
.cb{margin:.9em 0;border:1px solid var(--bd);border-radius:10px;overflow:hidden;background:var(--bg)}
.cb .ch{display:flex;justify-content:space-between;align-items:center;padding:4px 10px;border-bottom:1px solid var(--bd);font-size:12px;color:var(--mut)}
.cb .cpb{font-size:12px;padding:2px 10px;border-radius:6px}
.cb pre{margin:0;padding:12px 14px;overflow:auto;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.cb pre code.hljs{background:transparent;padding:0}
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
@media(max-width:760px){body{flex-direction:column}aside{width:100%;height:auto;max-height:42vh}main{height:auto;flex:1}}
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
<div id="drop"><div>Drop files to add them to your documents<small>PDF, Word, PowerPoint, Excel, images, text</small></div></div>
<main>
 <div class="scroll" id="scroll"><div class="wrap">
  <div id="mock" class="card warn" style="display:none"><b>Demo mode:</b> no LLM API key is configured on the server, so results are placeholder text. Set <code>ANTHROPIC_API_KEY</code>, <code>OPENAI_API_KEY</code> or <code>GOOGLE_API_KEY</code> (and optionally <code>TAVILY_API_KEY</code>) in your deployment's environment variables, then redeploy.</div>
  <div id="view"></div>
  <div id="hero"><h1>What do you want researched?</h1><p>Plans, searches the web and your documents, verifies quotes, and writes a cited report.</p><div class="eg" id="eg"></div></div>
 </div></div>
 <div class="dock"><div class="in">
  <div class="card ask">
   <div class="files" id="files"></div>
   <textarea id="q" rows="1" maxlength="1000" placeholder="Ask a research question…"></textarea>
   <div class="bar"><button class="ic" id="att" title="Attach files (or drag &amp; drop)" aria-label="Attach files">📎</button><input type="file" id="pick" multiple hidden>
    <label class="chk"><input type="checkbox" id="appr"> Review findings before writing</label>
    <span class="sp"></span><button id="stop" style="display:none">Stop</button><button class="pri" id="go">Research</button></div>
  </div>
  <div class="hint">Enter to run · Shift+Enter for a new line</div>
 </div></div>
</main>
<script>
const $=id=>document.getElementById(id),LS=window.localStorage;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const state={docs:false,ctl:null,hist:JSON.parse(LS.getItem("mars.hist")||"[]"),cur:null,server:false};
$("key").value=LS.getItem("mars.key")||"";$("key").onchange=()=>{LS.setItem("mars.key",$("key").value);boot()};
const hdr=()=>{const h={"Content-Type":"application/json"};const k=$("key").value.trim();if(k)h["X-API-Key"]=k;return h};
const EG=["What are the latest advances in solid-state batteries?","Compare Rust and Go for backend services","How effective are GLP-1 drugs for long-term weight loss?"];
$("eg").innerHTML=EG.map(e=>`<button>${esc(e)}</button>`).join("");
$("eg").onclick=e=>{if(e.target.tagName=="BUTTON"){$("q").value=e.target.textContent;$("q").focus();grow()}};

/* ---- markdown (escaped; citations [n] -> links to sources) ---- */
const MATH=/\$\$[\s\S]+?\$\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\]|\$(?![\s$])[^$\n]+?(?<![\s\\])\$(?!\d)/g;
function inl(s,cite){const keep=[];const hold=h=>{keep.push(h);return "\u0000"+(keep.length-1)+"\u0000"};
 s=String(s??"").replace(/`([^`]+)`/g,(m,c)=>hold("<code>"+esc(c)+"</code>"));
 s=s.replace(MATH,m=>{let d=false,t;if(m.startsWith("$$")){d=true;t=m.slice(2,-2)}else if(m.startsWith("\\(")||m.startsWith("\\[")){d=m[1]=="[";t=m.slice(2,-2)}else t=m.slice(1,-1);
  return hold(`<span class="mj${d?" blk":""}" data-tex="${esc(t.trim())}">${esc(m)}</span>`)});
 s=esc(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(^|[^*])\*([^*\s][^*]*?)\*/g,"$1<i>$2</i>")
 .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
 if(cite)s=s.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g,(m,ids)=>"<sup class=c>["+ids.split(/\s*,\s*/).map(i=>`<a href="#s${i}" data-s="${i}">${i}</a>`).join(",")+"]</sup>");
 return s.replace(/\u0000(\d+)\u0000/g,(m,i)=>keep[+i])}
function md(t,cite=true){const L=t.split("\n");let h="",ul=false,ol=false,i=0;const close=()=>{if(ul){h+="</ul>";ul=false}if(ol){h+="</ol>";ol=false}};
 while(i<L.length){const l=L[i];let m;
  if(m=l.match(/^\s*(```+|~~~+)\s*([\w+#.-]*)/)){close();const lang=m[2],fence=m[1][0],buf=[];i++;while(i<L.length&&!L[i].trim().startsWith(fence.repeat(3))){buf.push(L[i]);i++}
   if(lang=="chart"||lang=="mermaid"){const raw=esc(buf.join("\n"));
    h+=`<div class="viz ${lang}" data-${lang=="chart"?"spec":"src"}="${raw}"><pre class="vf"><code>${raw}</code></pre></div>`;i++;continue}
   h+=`<div class="cb"><div class="ch"><span>${esc(lang||"code")}</span><button class="cpb" type="button">Copy</button></div><pre><code${lang?` class="language-${esc(lang)}"`:""}>${esc(buf.join("\n"))}</code></pre></div>`;i++;continue}
  if(/^\s*(\$\$|\\\[)/.test(l)){close();const t0=l.trim(),end=t0.startsWith("$$")?"$$":"\\]";let body=t0.slice(2);
   while(!body.includes(end)&&i+1<L.length){i++;body+="\n"+L[i]}const k=body.indexOf(end);if(k>=0)body=body.slice(0,k);
   h+=`<div class="mj blk" data-tex="${esc(body.trim())}">${esc(body)}</div>`;i++;continue}
  if(m=l.match(/^(#{1,4})\s+(.*)/)){close();h+=`<h${m[1].length}>${inl(m[2],cite)}</h${m[1].length}>`}
  else if(/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)){close();h+="<hr>"}
  else if(m=l.match(/^\s*[-*]\s+(.*)/)){if(!ul){close();h+="<ul>";ul=true}h+=`<li>${inl(m[1],cite)}</li>`}
  else if(m=l.match(/^\s*\d+[.)]\s+(.*)/)){if(!ol){close();h+="<ol>";ol=true}h+=`<li>${inl(m[1],cite)}</li>`}
  else if(m=l.match(/^>\s?(.*)/)){close();h+=`<blockquote>${inl(m[1],cite)}</blockquote>`}
  else if(/^\|.*\|\s*$/.test(l)){close();const rows=[];while(i<L.length&&/^\|.*\|\s*$/.test(L[i])){rows.push(L[i]);i++}i--;
   const cells=r=>r.trim().replace(/^\||\|$/g,"").split("|").map(c=>c.trim());let t="<table>";
   rows.filter(r=>!/^\|[\s:|-]+\|$/.test(r)).forEach((r,k)=>{const tag=k?"td":"th";t+="<tr>"+cells(r).map(c=>`<${tag}>${inl(c,cite)}</${tag}>`).join("")+"</tr>"});h+=t+"</table>"}
  else if(l.trim()){close();h+=`<p>${inl(l,cite)}</p>`}else close();i++}
 close();return h}
/* math (KaTeX) and code highlighting (highlight.js) load from a CDN; without them the raw text still shows */
function typeset(root){if(!root)return;
 root.querySelectorAll(".viz.chart:not([data-ok])").forEach(drawChart);root.querySelectorAll(".viz.mermaid:not([data-ok])").forEach(drawMermaid);
 if(window.katex)root.querySelectorAll(".mj:not([data-ok])").forEach(el=>{try{katex.render(el.dataset.tex,el,{displayMode:el.classList.contains("blk"),throwOnError:false});el.dataset.ok=1}catch{}});
 if(window.hljs)root.querySelectorAll("pre code:not([data-hl])").forEach(el=>{try{hljs.highlightElement(el);el.dataset.hl=1}catch{}})}
const PAL=["#4e79a7","#f28e2b","#59a14f","#e15759","#76b7b2","#edc948","#b07aa1","#ff9da7"],dark=()=>matchMedia("(prefers-color-scheme: dark)").matches;
function drawChart(el){let s;try{s=JSON.parse(el.dataset.spec)}catch{return}
 if(!window.Chart||!["bar","line","pie","doughnut","radar","scatter","polarArea"].includes(s.type))return;
 const dk=dark(),fg=dk?"#ececf1":"#17171c",gr=dk?"#2a2a31":"#e4e4ea",round=["pie","doughnut","polarArea"].includes(s.type);
 const num=v=>v==null?null:+v,pt=v=>v&&typeof v=="object"?{x:+v.x,y:+v.y}:num(v);
 const datasets=(s.datasets||[]).slice(0,8).map((d,i)=>({label:String(d.label??""),data:(d.data||[]).slice(0,200).map(s.type=="scatter"?pt:num),
  backgroundColor:round?PAL:PAL[i%8]+"cc",borderColor:round?(dk?"#17171b":"#fff"):PAL[i%8],borderWidth:2,tension:.25}));
 const ax=t=>({ticks:{color:fg},grid:{color:gr},title:{display:!!t,text:t||"",color:fg}});
 el.innerHTML='<div class="vc"><canvas></canvas></div><div class="vb"><button class="svb" type="button">Save PNG</button></div>';
 const ch=new Chart(el.querySelector("canvas"),{type:s.type,data:{labels:(s.labels||[]).slice(0,200).map(String),datasets},
  options:{responsive:true,maintainAspectRatio:false,color:fg,plugins:{title:{display:!!s.title,text:s.title||"",color:fg,font:{size:14}},legend:{display:datasets.length>1||round,labels:{color:fg}}},
   scales:round?{}:s.type=="radar"?{r:{ticks:{color:fg,backdropColor:"transparent"},grid:{color:gr},pointLabels:{color:fg}}}:{x:ax(s.xLabel),y:ax(s.yLabel)}}});
 el.dataset.ok=1;el.querySelector(".svb").onclick=()=>{const a=document.createElement("a");a.href=ch.toBase64Image();a.download=((s.title||"chart").replace(/\W+/g,"_"))+".png";a.click()}}
let mmN=0;async function drawMermaid(el){if(!window.mermaid)return;const id="mm"+(++mmN);
 try{mermaid.initialize({startOnLoad:false,securityLevel:"strict",theme:dark()?"dark":"default"});const{svg}=await mermaid.render(id,el.dataset.src);el.innerHTML=svg;el.dataset.ok=1}
 catch{const e=document.getElementById("d"+id);if(e)e.remove()}}
addEventListener("load",()=>typeset(document.body));
document.addEventListener("click",e=>{const b=e.target.closest(".cpb");if(!b)return;const c=b.closest(".cb").querySelector("code");
 navigator.clipboard.writeText(c.textContent).then(()=>{b.textContent="Copied ✓";setTimeout(()=>b.textContent="Copy",1500)})});

/* ---- history ---- */
function saveHist(){LS.setItem("mars.hist",JSON.stringify(state.hist.slice(0,40)))}
function renderHist(){$("hist").innerHTML=state.hist.map(h=>`<div class="h ${state.cur===h.id?"act":""}" data-id="${esc(h.id)}"><span class="x" data-del="${esc(h.id)}">✕</span>${esc(h.question.slice(0,90))}<small>${esc(h.status)} · ${new Date(h.at).toLocaleString()}</small></div>`).join("")||'<div style="padding:12px;color:var(--mut);font-size:13px">No research yet.</div>'}
$("hist").onclick=async e=>{const d=e.target.dataset.del;if(d){state.hist=state.hist.filter(h=>h.id!==d);saveHist();if(state.server)fetch("/reports/"+d,{method:"DELETE",headers:hdr()}).catch(()=>{});if(state.cur===d)$("view").innerHTML="";renderHist();return}
 const el=e.target.closest(".h");if(!el)return;const id=el.dataset.id;state.cur=id;renderHist();
 let r=(state.hist.find(h=>h.id===id)||{}).report;
 if(!r&&state.server){try{const x=await fetch("/reports/"+id,{headers:hdr()});if(x.ok)r=await x.json()}catch{}}
 if(r){$("q").value=cq(r.question);grow();showReport(r,id)}else $("view").innerHTML='<div class="card warn">Report not available.</div>'};
$("new").onclick=()=>{state.cur=null;$("q").value="";grow();$("view").innerHTML="";renderHist();$("q").focus()};
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
 typeset($("view"));$("view").scrollIntoView({block:"start"});$("cp").onclick=()=>{navigator.clipboard.writeText(r.markdown||"");$("cp").textContent="Copied ✓"};
 $("dl").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([r.markdown||""],{type:"text/markdown"}));a.download="report.md";a.click()};
 $("rr").onclick=()=>{$("q").value=cq(r.question);run(true)};
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
 $("view").innerHTML=tlHtml(steps,"starting");toEnd();
 try{await sse(url,body,ev=>{
   if(ev.thread_id)tid=ev.thread_id;
   if(ev.event=="step"){steps.push(ev);$("view").innerHTML=tlHtml(steps,"next step");toEnd()}
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
 typeset($("view"));const send=a=>{stream("/research/"+tid+"/approve/stream",{approved:a,feedback:$("fb").value},question)};
 $("ap").onclick=()=>send(true);$("rj").onclick=()=>send(false)}

function run(again){const q=$("q").value.trim();if(q.length<5){$("q").focus();return}
 if(chips.some(c=>c.msg=="indexing…")){return}
 let ids=chips.filter(c=>c.id).map(c=>c.id);
 if(ids.length){state.docIds=ids;chips.length=0;renderChips()}else if(again)ids=state.docIds||[];else state.docIds=[];
 state.cur=null;renderHist();$("q").value="";grow();
 stream("/research/stream",{question:q,require_approval:$("appr").checked,document_ids:ids},q)}
$("go").onclick=()=>run();$("stop").onclick=()=>state.ctl&&state.ctl.abort();
$("q").addEventListener("keydown",e=>{if(e.key=="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();run()}});
const grow=()=>{const t=$("q");t.style.height="auto";t.style.height=Math.min(t.scrollHeight,220)+"px"};
$("q").addEventListener("input",grow);

/* ---- attach / drag & drop: files are indexed as internal documents ---- */
const ah=()=>{const h={},k=$("key").value.trim();if(k)h["X-API-Key"]=k;return h};
const chips=[];
function renderChips(){$("files").innerHTML=chips.map((c,i)=>`<div class="fc ${c.cls}" title="${esc(c.tip||c.name)}"><span>${c.icon}</span><span class="n">${esc(c.name)}</span><small>${esc(c.msg)}</small><span class="x" data-i="${i}" title="Dismiss">✕</span></div>`).join("")}
$("files").onclick=e=>{const i=e.target.dataset.i;if(i!=null){chips.splice(+i,1);renderChips()}};
async function upload(list){const files=[...list];if(!files.length)return;
 if(!state.docs){chips.push({name:"Documents are off",msg:"set MARS_DOCS_DB on the server",cls:"bad",icon:"✕"});renderChips();return}
 for(let i=0;i<files.length;i+=20){const batch=files.slice(i,i+20);
  const mine=batch.map(f=>{const c={name:f.name,msg:"indexing…",cls:"",icon:"⏳"};chips.push(c);return c});renderChips();
  const fd=new FormData();batch.forEach(f=>fd.append("files",f,f.name));
  try{const r=await fetch("/documents",{method:"POST",headers:ah(),body:fd});
   if(!r.ok){let d={};try{d=await r.json()}catch{}throw new Error(d.detail||d.code||("HTTP "+r.status))}
   (await r.json()).forEach((x,k)=>{const c=mine[k];if(!c)return;
    if(x.document)c.id=x.document.id;
    if(x.status=="indexed"){c.cls="ok";c.icon="✓";c.msg=x.document.chunks+" passages"}
    else if(x.status=="duplicate"){c.cls="dup";c.icon="＝";c.msg="already indexed"}
    else{c.cls="bad";c.icon="✕";c.msg=x.error||"failed";c.tip=c.msg}})}
  catch(e){mine.forEach(c=>{c.cls="bad";c.icon="✕";c.msg=e.message})}
  renderChips()}}
$("att").onclick=()=>$("pick").click();
$("pick").onchange=e=>{upload(e.target.files);e.target.value=""};
let dragN=0;const hasFiles=e=>e.dataTransfer&&[...e.dataTransfer.types].includes("Files");
addEventListener("dragenter",e=>{if(hasFiles(e)){e.preventDefault();dragN++;document.body.classList.add("drag")}});
addEventListener("dragover",e=>{if(hasFiles(e))e.preventDefault()});
addEventListener("dragleave",e=>{if(hasFiles(e)&&--dragN<=0){dragN=0;document.body.classList.remove("drag")}});
addEventListener("drop",e=>{if(hasFiles(e)){e.preventDefault();dragN=0;document.body.classList.remove("drag");upload(e.dataTransfer.files)}});
$("q").addEventListener("paste",e=>{const f=e.clipboardData&&e.clipboardData.files;if(f&&f.length){e.preventDefault();upload(f)}});
const cq=q=>String(q).replace(/\s*\(about the attached documents?:.*\)$/,"");
const toEnd=()=>{const s=$("scroll");s.scrollTop=s.scrollHeight};

async function boot(){const h=$("health");
 try{const r=await fetch("/health");const d=await r.json();h.innerHTML=`<span class="dot on"></span>${esc(d.provider||"ok")} · ${esc(d.search||"")} · ${d.active_runs} active`;
  $("mock").style.display=(d.provider==="mock")?"":"none";
  state.docs=!!d.documents;$("att").style.opacity=state.docs?"":".45";
  if(d.storage!=="off"){const x=await fetch("/reports?limit=30",{headers:hdr()});if(x.ok){state.server=true;const list=await x.json();
   const known=new Set(state.hist.map(h=>h.id));list.forEach(s=>{if(!known.has(s.id))state.hist.push({id:s.id,question:s.question,status:s.status,at:Date.parse(s.created_at)||Date.now()})});
   state.hist.sort((a,b)=>b.at-a.at);renderHist()}}}
 catch{h.innerHTML='<span class="dot off"></span>offline'}}
renderHist();boot();
</script></body></html>"""
