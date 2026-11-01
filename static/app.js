/* PegineLab Factory: all build state lives in SQLite, not the browser. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const active = new Set(["queued", "running", "stopping"]);
const labels = {queued:"В очереди",running:"Собирается",stopping:"Останавливается",success:"Готово",failed:"Ошибка",stopped:"Остановлено",interrupted:"Прервано"};
let selected = null, offset = 0, loading = false, overview = null, refreshedLog = false;
const date = (iso) => iso ? new Date(iso).toLocaleString("ru-RU") : "—";
const size = (v) => !Number.isFinite(v) ? "—" : (v / 1073741824 >= 1 ? (v / 1073741824).toFixed(1) + " ГБ" : (v / 1048576).toFixed(1) + " МБ");
const $text = (id, value) => { $(id).textContent = String(value); };
const element = (tag, className, text) => {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
};
function toast(message) { const t=$("toast"); t.textContent=message; t.classList.add("show"); clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.classList.remove("show"),4000); }
async function api(path, options={}) {
  const response=await fetch(path,{credentials:"same-origin",cache:"no-store",...options,headers:{"X-PegineLab-Action":"1",...(options.headers||{})}});
  const json=await response.json();
  if (!response.ok) { const e=new Error(json.error || "Ошибка сервера");e.status=response.status;throw e; }
  return json;
}
function setTab() {
  const tab=(location.hash||"#overview").slice(1);
  const valid=["overview","builds","artifacts","system"];
  const current=valid.includes(tab)?tab:"overview";
  const names={overview:"Обзор",builds:"Сборки",artifacts:"Артефакты",system:"Система"};
  document.querySelectorAll("[data-panel]").forEach(el=>el.hidden=el.dataset.panel!==current);
  document.querySelectorAll("[data-tab]").forEach(el=>el.classList.toggle("active",el.dataset.tab===current));
  $text("pageName",names[current]);document.title="PegineLab · "+names[current];
  if(current==="builds") refreshLog();
}
function metric(numberId,barId,infoId,value,part,total,suffix) {
  $text(numberId,value);
  $(barId).style.width = (total > 0 ? Math.max(0,Math.min(100,part/total*100)):0)+"%";
  if(infoId) $text(infoId,suffix);
}
function statusPill(status) {
  return element("span","state state-"+status,labels[status]||status);
}
function jobItem(job,compact=false) {
  const item=element("button",compact?"recent-job":"job-row");
  if(job.id===selected)item.classList.add("selected");
  const left=element("div","job-main");
  left.append(element("strong","",job.profile==="t23n_sd"?"WIFICAM · T23N SD":"Firmware"));
  left.append(element("small","",date(job.created_at)+" · "+job.id.slice(0,8)));
  item.append(left,statusPill(job.status));
  item.addEventListener("click",()=>select(job.id));
  return item;
}
function select(id) {
  if(selected!==id){selected=id;offset=0;refreshedLog=false;$("log").textContent="";$text("logBytes","0 Б");}
  location.hash="builds";setTab();renderJobs();refreshLog();
}
function renderJobs() {
  if(!overview)return;
  const jobs=overview.jobs||[];
  $text("jobsNumber",jobs.length);
  $text("buildCount",jobs.length);
  $text("navBuildCount",jobs.length);
  const running=jobs.find(j=>active.has(j.status));
  $text("currentStatus",running?"● "+labels[running.status]:"Нет активных задач");
  ["heroBuild","newBuild","profileBuild"].forEach(id=>$(id).disabled=!!running);
  const recent=$("recentJobs");recent.replaceChildren();
  const list=$("jobsList");list.replaceChildren();
  if(!jobs.length){recent.append(element("p","empty","История пока пуста"));list.append(element("p","empty","Сборок пока нет"));}
  for(const job of jobs) {list.append(jobItem(job));}
  for(const job of jobs.slice(0,4)) recent.append(jobItem(job,true));
  const current=jobs.find(j=>j.id===selected);
  if(!selected&&jobs.length){selected=jobs[0].id;offset=0;}
  const selectedJob=jobs.find(j=>j.id===selected)||current;
  $("stopBuild").disabled=!selectedJob||!active.has(selectedJob.status);
  $text("logState",selectedJob?(labels[selectedJob.status]||selectedJob.status):"Выберите задачу");
  $text("logTitle",selectedJob?"Журнал · "+selectedJob.id.slice(0,8):"Консоль сборки");
}
function renderOverview(data) {
  overview=data;renderJobs();
  const m=data.metrics;
  metric("load","loadBar","loadInfo",m.load_1.toFixed(2),m.load_1,m.cpus||32,"1 мин · "+m.cpus+" логических CPU");
  metric("memory","memBar","memInfo",size(m.memory_used),m.memory_used,m.memory_total,"из "+size(m.memory_total));
  metric("disk","diskBar","diskInfo",size(m.disk_total-m.disk_used),m.disk_used,m.disk_total,"Свободно · использовано "+Math.round(m.disk_used/m.disk_total*100)+"%");
  const artifacts=$("artifactList");artifacts.replaceChildren();
  if(!data.images.length)artifacts.append(element("p","empty","Пока нет артефактов"));
  for(const image of data.images) {
    const item=element("div","artifact");
    const icon=element("div","artifact-icon","▣");
    const info=element("div","artifact-info");
    info.append(element("strong","",image.label));
    info.append(element("small","",image.name+" · "+size(image.bytes)));
    info.append(element("code","",image.location));
    if(image.sha256)info.append(element("code","hash","SHA256  "+image.sha256));
    item.append(icon,info);artifacts.append(item);
  }
  $text("pathRoot",data.paths.root);
  $text("pathProject",data.paths.project);
  $text("pathThingino",data.paths.thingino);
}
async function refresh() {
  if(loading)return;
  loading=true;
  try {const data=await api("/api/overview");renderOverview(data);$("connection").textContent="На связи";}
  catch(e){$("connection").textContent="Нет связи";}
  finally{loading=false;}
  if(location.hash==="#builds")refreshLog();
}
async function refreshLog() {
  if(!selected||refreshedLog)return;
  refreshedLog=true;
  const selectedAtStart=selected;
  try{
    const result=await api("/api/jobs/"+selected+"/log?offset="+offset);
    if(selectedAtStart!==selected)return;
    if(offset===0&&result.text==="")$("log").textContent="Сборка ожидает запуска…\n";
    if(result.text){
      if(offset===0)$("log").textContent="";
      const terminal=$("log");
      const nearBottom=terminal.scrollHeight-terminal.scrollTop-terminal.clientHeight<100;
      terminal.textContent+=result.text;
      if(terminal.textContent.length>350000)terminal.textContent=terminal.textContent.slice(-250000);
      if(nearBottom)terminal.scrollTop=terminal.scrollHeight;
    }
    offset=result.offset;
    $text("logBytes",size(offset));
    if(result.more)setTimeout(()=>{refreshedLog=false;refreshLog();},200);
  }catch(e){$("connection").textContent="Ошибка журнала";}
  finally {refreshedLog=false;}
}
async function start() {
  if(!confirm("Запустить чистую сборку WIFICAM T23N? Персональный Wi-Fi-образ останется только на сервере."))return;
  try {
    const r=await api("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({profile:"t23n_sd"})});
    toast("Сборка запущена независимо от SSH");selected=r.job_id;offset=0;$("log").textContent="";location.hash="builds";setTab();await refresh();
  }catch(e){toast(e.message);}
}
async function stop() {
  if(!selected||!confirm("Остановить выбранную сборку и её процессы компиляции?"))return;
  try {await api("/api/jobs/"+selected+"/stop",{method:"POST"});toast("Запрошена остановка сборки");await refresh();}
  catch(e){toast(e.message);}
}
async function init() {
  $("clock").textContent=new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"});
  setTab();window.addEventListener("hashchange",setTab);
  ["heroBuild","newBuild","profileBuild"].forEach(id=>$(id).addEventListener("click",start));
  $("stopBuild").addEventListener("click",stop);
  $("clearView").addEventListener("click",()=>{offset=0;$("log").textContent="";refreshLog();});
  await refresh();
  setInterval(()=>{refresh();if(location.hash==="#builds")refreshLog();},2500);
  setInterval(()=>$text("clock",new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})),15000);
  window.addEventListener("focus",refresh);
}
document.addEventListener("DOMContentLoaded",init);
})();
