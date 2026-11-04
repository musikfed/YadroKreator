/* PegineLab Factory: all build state lives in SQLite, not the browser. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const active = new Set(["queued", "running", "stopping"]);
const labels = {queued:"В очереди",running:"Собирается",stopping:"Останавливается",success:"Готово",failed:"Ошибка",stopped:"Остановлено",interrupted:"Прервано"};
let selected = null, selectedIrila = null, offset = 0, loading = false, overview = null, refreshedLog = false;
let logInitial = true, logFinalized = false, logFullRequested = false;
let updateState = null, checkingUpdate = false, lastAutoCheck = 0;
let updateHadActive = false, updateAutoReloaded = false;
let panelServiceState = null, panelActionBusy = false, panelReconnect = false, panelReconnectAfter = 0;

const date = (iso) => iso ? new Date(iso).toLocaleString("ru-RU") : "—";
// Stopwatch from persisted timestamps; build prediction is approximate only.
const clockDuration = (s) => {
  if(s===null || s===undefined || !Number.isFinite(s))return "—";
  const n=Math.max(0,Math.floor(s));
  return [Math.floor(n/3600),Math.floor(n%3600/60),n%60].map(v=>String(v).padStart(2,"0")).join(":");
};
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
  const valid=["overview","builds","irila","helper","system"];
  const configured=(overview?.registered_projects||[]).find(p=>tab==="project-"+p.slug);
  // Old #artifacts bookmarks open WIFICAM's own Images tab, not Overview.
  const current=tab==="artifacts"?"builds":(valid.includes(tab)||configured?tab:"overview");
  const names={overview:"Обзор",builds:"WIFICAM T23N",irila:"Irila Baikal",helper:"WifCam Helper",system:"Система"};
  if(configured)names[current]=configured.title;
  document.querySelectorAll("[data-panel]").forEach(el=>el.hidden=el.dataset.panel!==current);
  document.querySelectorAll("[data-tab]").forEach(el=>el.classList.toggle("active",el.dataset.tab===current));
  $text("pageName",names[current]);document.title="PegineLab · "+names[current];
  if(current==="builds")refreshLog();
  if(current==="irila") refreshIrilaLog();
}
// Each project now has ONE working screen. No separate global image tab.
function setWificamMode(_mode){ /* legacy #artifacts routes to #builds */ }
function setProjectSubtab(project,target){
  const buttons=[...document.querySelectorAll('[data-project-subtab="'+project+'"]')];
  if(!buttons.some(btn=>btn.dataset.target===target))return;
  for(const btn of buttons){
    const selected=btn.dataset.target===target;
    btn.classList.toggle("active",selected);
    btn.setAttribute("aria-selected",String(selected));
    const area=$(btn.dataset.target);
    if(area)area.hidden=!selected;
  }
}
function updateHelperBranchCompatibility(){
  const supported=$("sourceBranch").value==="mymarrchWFcam";
  $("helperPreset").disabled=!supported;
  if(!supported)$("helperPreset").checked=false;
  $text("helperBranchNote",supported
    ?"Helper-профиль доступен для mymarrchWFcam."
    :"Для этой ветки Helper-профиль не утверждён; сборка идёт без него.");
}
function renderRegisteredProjects(projects){
  const nav=$("registeredProjectNav"),panels=$("registeredProjectPanels"),summary=$("registryProjectList");
  const cards=$("registeredProjectCards");cards.replaceChildren();
  $text("projectCount",String(3+projects.length).padStart(2,"0"));
  const previous=[...document.querySelectorAll('.panel[data-panel^="project-"]')]
    .find(p=>p.dataset.panel===location.hash.slice(1));
  nav.replaceChildren();
  panels.replaceChildren();
  summary.replaceChildren();
  for(const p of projects){
    const tab="project-"+p.slug;
    const card=element("div","profile");
    const icon=element("div","profile-icon","◈");
    const info=element("div","profile-text");
    info.append(element("strong","",p.title),element("small","",p.repository+" · "+p.branch));
    const observe=p.mode==="observe"||p.build_mode==="observe";
    info.append(element("span","tag neutral",observe?"НАБЛЮДЕНИЕ · БЕЗ СБОРКИ":"КОНТРАКТ · АДАПТЕР ОЖИДАЕТ"));
    const cardLink=element("a","round-btn","↗");cardLink.href="#"+tab;
    cardLink.title="Открыть "+p.title;
    card.append(icon,info,cardLink);cards.append(card);
    const link=element("a","nav","▧  "+p.title);
    link.href="#"+tab;link.dataset.tab=tab;nav.append(link);
    const project=element("section","panel");
    project.dataset.panel=tab;project.hidden=true;
    const heading=element("div","page-heading");
    const header=element("div");
    const eyebrow=element("small","","GITHUB PROJECT / ISOLATED WORKSPACE");
    const title=element("h1","",p.title);
    const description=element("p","",observe
       ?"Проект подключён для наблюдения. Исходники и Git доступны; мониторинг и сборка требуют самостоятельной интеграции."
       :"Проект заявил параметры сборки контрактом v1. До утверждения адаптера исполнение запрещено.");
    header.append(eyebrow,title,description);heading.append(header);project.append(heading);
    const tabs=element("div","project-subnav");
    tabs.setAttribute("role","tablist");tabs.setAttribute("aria-label","Разделы "+p.title);
    // Only expose actual capabilities. Never render fake Jobs/Reports tabs.
    const items=observe?[
      ["source","Исходники и GitHub"],
      ["settings","Подключение"],
    ]:[
      ["source","Исходники и GitHub"],
      ["build","Контракт сборки"],
      ["images","Заявленные результаты"],
      ["settings","Конфигурация"],
    ];
    const sections=new Map();
    for(const [mode,label] of items){
      const btn=element("button","project-tab",label);
      btn.type="button";btn.dataset.projectMode=mode;btn.setAttribute("role","tab");
      const area=element("div","surface project-detail");
      area.dataset.projectView=mode;area.hidden=mode!=="source";
      if(mode==="source"){
        area.append(element("h3","","Исходники на GitHub"));
        const anchor=element("a","small-link",p.repository+" · "+p.branch);
        anchor.href="https://github.com/"+p.repository+"/tree/"+p.branch;
        anchor.target="_blank";anchor.rel="noopener noreferrer";
        area.append(anchor);
        const sha=element("p","muted","Проверено при регистрации. Для свежего SHA запроси GitHub вручную.");
        area.append(sha);
        const refresh=element("button","secondary","↻ Проверить актуальный Git SHA");
        refresh.type="button";
        refresh.addEventListener("click",async()=>{
          refresh.disabled=true;
          try{
            const data=await api("/api/projects/"+encodeURIComponent(p.slug)+"/git-ref");
            sha.textContent="Текущая ветка: "+data.branch+" · "+data.sha;
          }catch(error){sha.textContent="Проверка GitHub не удалась: "+error.message;}
          finally{refresh.disabled=false;}
        });
        area.append(refresh);
      }else if(mode==="build"){
        area.append(element("h3","",observe?"Режим наблюдения":"Профиль сборки ядра"));
        area.append(element("p","muted",observe
           ?"Компиляция не предусмотрена. Реальные сигналы появятся после подключения проверенного источника метрик; фиктивные данные не создаются."
           :"Конвейер ожидает утверждённый локальный адаптер/toolchain. Контракт описывает сборку, но не разрешает выполнение сценариев GitHub."));
        if(p.contract?.adapter)area.append(element("p","muted","Заявленный адаптер: "+p.contract.adapter+
          " · SHA контракта: "+p.contract.source_sha));
      }else if(mode==="images"){
        area.append(element("h3","",observe?"Отчёты и файлы проекта":"Образы этого проекта"));
        area.append(element("p","muted",observe
          ?"Нет подключённого источника отчётов. Для наблюдения нужно настроить отдельный адаптер метрик."
          :"Нет опубликованных артефактов этого проекта. Образы другого проекта сюда не попадают."));
        for(const item of p.contract?.outputs||[]){
          area.append(element("p","muted",item.type+" · ожидаемый путь: "+item.path));
        }
      }else if(mode==="logs"){
        area.append(element("h3","","Журнал проекта"));
        area.append(element("p","muted",observe
          ?"События недоступны до подключения собственного адаптера наблюдения."
          :"Пока нет заданий. После подключения собственного адаптера сюда будут поступать реальные логи сборок."));
      }else{
        area.append(element("h3","","Изолированная конфигурация"));
        area.append(element("p","muted","Источник: "+p.repository+" · ветка: "+p.branch+" · режим: "+
         (observe?"наблюдение":"ожидает утверждённого адаптера")));
        area.append(element("p","muted","Регистрация не запускает компилятор, не изменяет systemd, Docker и базу старых заданий."));
      }
      sections.set(mode,area);
      btn.addEventListener("click",()=>{
        for(const [key,sec] of sections)sec.hidden=key!==mode;
        for(const child of tabs.querySelectorAll("button")){
          const selected=child.dataset.projectMode===mode;
          child.classList.toggle("active",selected);
          child.setAttribute("aria-selected",String(selected));
        }
      });
      tabs.append(btn);project.append(area);
    }
    tabs.firstChild.classList.add("active");
    for(const child of tabs.children)child.setAttribute("aria-selected",String(child===tabs.firstChild));
    project.insertBefore(tabs,project.children[1]);panels.append(project);
    const row=element("div","registered-project-item");
    const jump=element("a","small-link",p.title+" · "+p.repository+" / "+p.branch);
    jump.href="#"+tab;
    row.append(jump,element("span","tag neutral",observe?"НАБЛЮДЕНИЕ":"АДАПТЕР ОЖИДАЕТ"));summary.append(row);
  }
  if(!projects.length){
    summary.append(element("p","muted","Пока подключены только штатные проекты WIFICAM, Irila и Helper."));
  }
  if(previous || projects.some(p=>location.hash==="#project-"+p.slug))setTab();
}
async function registerGitHub(kind){
  const branch=kind==="branch"?$("registryBranch").value.trim():$("registryProjectBranch").value.trim();
  const data=kind==="branch"
    ?{kind,branch,confirm:"REGISTER-BRANCH"}
    :{kind,slug:$("registrySlug").value.trim(),title:$("registryTitle").value.trim(),
       repository:$("registryRepo").value.trim(),branch,
       mode:$("registryMode").value,confirm:"REGISTER-PROJECT"};
  const message=kind==="branch"
    ?"Добавить ветку "+branch+" к настоящей сборке WIFICAM?"
    :"Подключить "+data.title+" в режиме «"+(data.mode==="observe"?"Наблюдение":"Кандидат на сборку")+
      "»? Неподтверждённые скрипты и Docker-команды не запускаются.";
  if(!confirm(message))return;
  $text("registryMessage","Проверяем существование ветки в GitHub…");
  try{
    await api("/api/projects/register",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    await refresh();
    $text("registryMessage",kind==="branch"
      ?"Ветка зарегистрирована. Перейди в WIFICAM → Сборки и журнал и выбери её."
      :data.mode==="observe"?"Наблюдаемый проект подключён вручную, сборка отключена."
       :"Контракт проверен. Для исполнения потребуется проверенный адаптер сборки.");
    if(kind==="project")location.hash="project-"+data.slug;
    else location.hash="builds";
    setTab();
  }catch(error){$text("registryMessage","Не удалось зарегистрировать: "+error.message);}
}
let helperBusy=false;
async function refreshHelper() {
  try {
    const helper=await api("/api/helper/status");
    $text("helperGitSha",helper.source_sha?helper.source_sha.slice(0,12):"Нет локального Git");
    $text("helperUnitState",helper.service_state+" · "+helper.service_unit);
    $text("helperReportCount",helper.report_count===null?"Нет отдельной SQLite":helper.report_count+" · последний: "+(helper.last_test||"—"));
    $text("helperDatabasePath",helper.report_database);
    const installed=helper.service_installed&&helper.source_present;
    $("helperStart").disabled=helperBusy||!installed||helper.service_state==="active";
    $("helperRestart").disabled=helperBusy||!installed||helper.service_state!=="active";
    $("helperStop").disabled=helperBusy||!installed||helper.service_state!=="active";
    $text("helperActionNote",installed
      ?"Helper управляется независимо. Журнал и результаты тестов не входят в SQLite прошивок."
      :"Helper ещё не установлен как отдельная служба. Сначала запусти scripts/install-user-service.sh на CORE через SSH.");
  }catch(error){
    $text("helperUnitState","Недоступно");
    $text("helperActionNote","Не получилось прочитать состояние отдельного Helper: "+error.message);
  }
}
async function helperAction(action) {
  if(helperBusy)return;
  const question={start:"Запустить только WifCam Helper?",stop:"Остановить только WifCam Helper?",restart:"Перезапустить только WifCam Helper?"}[action];
  if(!question||!confirm(question))return;
  helperBusy=true;
  try {
    const result=await api("/api/helper/service/"+action,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirm:"HELPER-"+action.toUpperCase()})
    });
    toast("WifCam Helper: "+result.helper.service_state);
  }catch(error){toast("Helper: "+error.message)}
  finally {helperBusy=false;await refreshHelper()}
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
  if(job.id===(job.profile==="irila_preflight"?selectedIrila:selected))item.classList.add("selected");
  const left=element("div","job-main");
  left.append(element("strong","",job.profile==="t23n_sd"?"WIFICAM · T23N SD":job.profile==="irila_preflight"?"IRILA · аудит источников":"Неизвестный профиль"));
  left.append(element("small","",date(job.created_at)+" · "+job.id.slice(0,8)));
  if(job.repo_ref)left.append(element("small","",job.repo_ref+" · "+(job.source_sha?job.source_sha.slice(0,12):"Git fetch pending")));
  if(job.elapsed_seconds!==null && job.elapsed_seconds!==undefined)
    left.append(element("small","", "Время "+clockDuration(job.elapsed_seconds)));
  item.append(left,statusPill(job.status));
  item.addEventListener("click",()=>job.profile==="irila_preflight"?selectIrila(job.id):select(job.id));
  return item;
}
function select(id) {
  if(selected!==id){selected=id;offset=0;refreshedLog=false;
    logInitial=true;logFinalized=false;logFullRequested=false;
    $("log").textContent="";$text("logBytes","0 Б");}
  location.hash="builds";setTab();renderJobs();refreshLog();
}
function selectIrila(id) {
  selectedIrila=id;
  setProjectSubtab("irila","irilaHistory");
  location.hash="irila";
  setTab();
  renderJobs();
  refreshIrilaLog();
}
async function refreshIrilaLog(){
  if(!selectedIrila)return;
  const job=overview?.jobs?.find(j=>j.id===selectedIrila&&j.profile==="irila_preflight");
  if(!job)return;
  try {
    const result=await api("/api/jobs/"+job.id+"/log?tail=1");
    $("irilaLog").textContent="IRILA SOURCE AUDIT · "+(labels[job.status]||job.status)+"\n\n"+(result.text||"Журнал пока пуст");
  }catch(e){$("irilaLog").textContent="Ошибка журнала Irila: "+e.message}
}
async function runIrilaAudit(){
  if(!confirm("Запустить только проверку исходников Irila/main? Без сборки IMG, root, loop или записи дисков."))return;
  try {
    const result=await api("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({profile:"irila_preflight",branch:"main"})});
    selectedIrila=result.job_id;
    $("irilaLog").textContent="Задание добавлено в очередь...\n";
    toast("Аудит Irila запущен; настоящую IMG собирает отдельный GitHub Actions workflow");
    await refresh();
    refreshIrilaLog();
  }catch(e){toast("Irila: "+e.message)}
}
async function showIrilaReport(){
  if(!selectedIrila)return;
  try {
    const report=await api("/api/jobs/"+selectedIrila+"/irila-audit");
    $("irilaLog").textContent=JSON.stringify(report,null,2);
  }catch(e){toast("Отчёт Irila: "+e.message)}
}
async function downloadIrilaReport(){
  if(!selectedIrila)return;
  const job=overview?.jobs?.find(j=>j.id===selectedIrila&&j.profile==="irila_preflight");
  if(!job||job.status!=="success")return;
  try{
    const report=await api("/api/jobs/"+job.id+"/irila-audit");
    if(report.profile!=="irila_preflight")throw Error("Неверный профиль отчёта");
    const blob=new Blob([JSON.stringify(report,null,2)+"\n"],{type:"application/json"});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement("a");
    anchor.href=url;
    anchor.download="Irila_Baikal_audit_"+job.id.slice(0,8)+".json";
    document.body.append(anchor);anchor.click();anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){toast("Скачивание Irila: "+e.message)}
}
async function stopIrila(){
  if(!selectedIrila||!confirm("Остановить только текущий аудит Irila?"))return;
  try{await api("/api/jobs/"+selectedIrila+"/stop",{method:"POST"});await refresh();}
  catch(e){toast("Не удалось остановить Irila: "+e.message)}
}

const jobKind = (job) => job?.profile==="t23n_sd" ? "WIFICAM T23N · прошивка SD" :
  job?.profile==="irila_preflight" ? "Irila Baikal · проверка исходников" : "Неизвестный профиль";
function renderActiveJob(jobs) {
  // The server persists actual state in SQLite; never assume T23N is active.
  const running = (overview?.active_job && active.has(overview.active_job.status)
    ? overview.active_job : jobs.find(j=>active.has(j.status)));
  const pill=$("activeJobState");
  const open=$("activeJobOpen");
  const last=jobs.find(j=>!active.has(j.status));
  $text("lastJobSummary",last?
    "Последняя операция: "+jobKind(last)+" · "+(labels[last.status]||last.status)+
      " · "+date(last.finished_at||last.created_at) :
    "История очищена или запусков пока не было.");
  if(!running) {
    pill.className="tag neutral";
    pill.textContent="СВОБОДНО";
    $text("activeJobName","Нет активных заданий");
    $text("activeJobDescription","Очередь свободна. Выбери нужный проект ниже; сборка не запускается автоматически.");
    $text("activeJobBranch","Проект: —");
    $text("activeJobRuntime","Время: —");
    $text("activeJobSource","Git SHA: —");
    open.disabled=true;
    return;
  }
  pill.className="state state-"+running.status;
  pill.textContent=labels[running.status]||running.status;
  $text("activeJobName",jobKind(running));
  $text("activeJobDescription",running.status==="queued"?
    "Задание передано systemd и ожидает запуска. Никаких других сборок сейчас не допускается.":
    running.status==="stopping"?
    "Получена команда остановки. Ждём подтверждения завершения процесса.":
    "Задание выполняется в собственном дереве проекта. Подробные этапы — в его журнале.");
  $text("activeJobBranch","Ветка: "+(running.repo_ref||"—")+" · ID "+running.id.slice(0,8));
  $text("activeJobRuntime","Время: "+clockDuration(running.elapsed_seconds));
  $text("activeJobSource","Git SHA: "+(running.source_sha?running.source_sha.slice(0,12):"ещё не получен"));
  open.disabled=false;
}
function renderJobs() {
  if(!overview)return;
  const jobs=overview.jobs||[];
  const cameraJobs=jobs.filter(j=>j.profile==="t23n_sd");
  const irilaJobs=jobs.filter(j=>j.profile==="irila_preflight");
  $text("jobsNumber",jobs.length);
  $text("buildCount",cameraJobs.length);
  $text("navBuildCount",cameraJobs.length);
  const running=(overview.active_job && active.has(overview.active_job.status))?overview.active_job:jobs.find(j=>active.has(j.status));
  $text("currentStatus",running?jobKind(running)+" · "+(labels[running.status]||running.status):"Нет активных задач");
  renderActiveJob(jobs);
  $("newBuild").disabled=!!running || !!(updateState && ["queued","running"].includes(updateState.phase) && ["apply","rollback"].includes(updateState.action));
  const recent=$("recentJobs");recent.replaceChildren();
  const list=$("jobsList");list.replaceChildren();
  if(!jobs.length)recent.append(element("p","empty","История пока пуста"));
  if(!cameraJobs.length)list.append(element("p","empty","Пока нет сборок WIFICAM"));
  for(const job of cameraJobs) {list.append(jobItem(job));}
  const irilaList=$("irilaJobs");irilaList.replaceChildren();
  if(!irilaJobs.length)irilaList.append(element("p","empty","Пока нет аудитов Irila"));
  for(const job of irilaJobs)irilaList.append(jobItem(job));
  if(!selectedIrila && irilaJobs.length)selectedIrila=irilaJobs[0].id;
  const irilaCurrent=irilaJobs.find(j=>j.id===selectedIrila);
  $("irilaCheck").disabled=!!running || !!(updateState&&["queued","running"].includes(updateState.phase));
  $("irilaStop").disabled=!irilaCurrent||!active.has(irilaCurrent.status);
  $("irilaReport").disabled=!irilaCurrent||irilaCurrent.status!=="success";
  const irilaArtifact=(overview.artifact_records||[]).find(a=>a.job_id===irilaCurrent?.id);
  $("irilaExport").disabled=!irilaArtifact?.available;
  $("irilaDeleteArtifact").disabled=!irilaArtifact?.available;
  if(cameraJobs.length){
    recent.append(element("div","lane-history-heading camera","WIFICAM T23N · SD-прошивки"));
    for(const job of cameraJobs.slice(0,2))recent.append(jobItem(job,true));
  }
  if(irilaJobs.length){
    recent.append(element("div","lane-history-heading irila","IRILA BAIKAL · отдельные аудиты"));
    for(const job of irilaJobs.slice(0,2))recent.append(jobItem(job,true));
  }
  const current=jobs.find(j=>j.id===selected);
  if(!selected&&cameraJobs.length){selected=cameraJobs[0].id;offset=0;
    logInitial=true;logFinalized=false;logFullRequested=false;}
  const selectedJob=cameraJobs.find(j=>j.id===selected)||null;
  $("stopBuild").disabled=!selectedJob||!active.has(selectedJob.status);
  $("fullBuildLog").disabled=!selectedJob || active.has(selectedJob.status);
  $text("logState",selectedJob?(labels[selectedJob.status]||selectedJob.status):"Выберите задачу");
  $text("logTitle",selectedJob?"Журнал · "+selectedJob.id.slice(0,8):"Консоль сборки");
  renderBuildTimeline(selectedJob);
  const cameraArtifact=(overview.artifact_records||[]).find(a=>a.job_id===selectedJob?.id);
  $("validateBuild").disabled=!cameraArtifact?.available;
  $("downloadSelected").disabled=!cameraArtifact?.available;
  $("deleteSelectedArtifact").disabled=!cameraArtifact?.available;
  renderSavedValidation(selectedJob);
  if(panelServiceState)renderPanelService(panelServiceState);
}
function renderOverview(data) {
  overview=data;renderJobs();
  $text("wificamBuildRoot",data.paths.wificam_build);
  $text("irilaBuildRoot",data.paths.irila_build);
  $text("helperSourcePath",data.paths.helper);
  if(Array.isArray(data.allowed_branches)){
    const selector=$("sourceBranch");
    const signature=JSON.stringify(data.allowed_branches);
    // Overview refreshes every 2.5 s; do not reset an open dropdown.
    if(selector.dataset.branches!==signature){
      const selectedBranch=selector.value||"mymarrchWFcam";
      selector.replaceChildren();
      for(const name of data.allowed_branches){
        const option=element("option","",name);
        option.value=name;selector.append(option);
      }
      selector.value=data.allowed_branches.includes(selectedBranch)?selectedBranch:data.allowed_branches[0];
      selector.dataset.branches=signature;
    }
    updateHelperBranchCompatibility();
  }
  const projects=data.registered_projects||[];
  const currentIds=projects.map(p=>p.slug+":"+(p.mode||"build")+":"+p.branch).join(",");
  if(window.registeredIds!==currentIds){
    renderRegisteredProjects(projects);
    window.registeredIds=currentIds;
  }
  const m=data.metrics;
  metric("load","loadBar","loadInfo",m.load_1.toFixed(2),m.load_1,m.cpus||32,"1 мин · "+m.cpus+" логических CPU");
  metric("memory","memBar","memInfo",size(m.memory_used),m.memory_used,m.memory_total,"из "+size(m.memory_total));
  metric("disk","diskBar","diskInfo",size(m.disk_total-m.disk_used),m.disk_used,m.disk_total,"Свободно · использовано "+Math.round(m.disk_used/m.disk_total*100)+"%");
  renderFactoryArtifacts(data);
  $text("pathRoot",data.paths.root);
  $text("pathProject",data.paths.project);
  $text("pathThingino",data.paths.thingino);
}
function renderFactoryArtifacts(data){
  const camera=$("artifactList"),irila=$("irilaArtifactList");
  camera.replaceChildren();irila.replaceChildren();
  const records=data.artifact_records||[];
  for(const record of records){
    const list=record.profile==="t23n_sd"?camera:irila;
    const item=element("div","artifact factory-output-row");
    const info=element("div","artifact-info");
    const name=record.profile==="t23n_sd"?"SD-образ":"Аудит источников";
    info.append(element("strong","",name+" · "+record.job_id.slice(0,8)));
    const state=record.deleted?"Удалён с сервера":
       record.available?"Файл готов · "+size(record.bytes):
       record.status==="success"?"Сборка завершена, но файл отсутствует":
       labels[record.status]||record.status;
    info.append(element("small","",state+" · "+date(record.created_at)));
    if(record.source_sha)info.append(element("code","","SHA "+record.source_sha.slice(0,12)));
    if(record.details)info.append(element("small","factory-error",record.details.slice(0,160)));
    const actions=element("div","artifact-actions");
    const log=element("button","secondary","Журнал");
    log.type="button";log.addEventListener("click",()=>record.profile==="t23n_sd"
      ?select(record.job_id):selectIrila(record.job_id));
    actions.append(log);
    if(record.available){
      const check=element("button","secondary","✓ Проверить");
      check.type="button";
      check.addEventListener("click",()=>record.profile==="t23n_sd"
        ?(select(record.job_id),validateSelected())
        :(selectIrila(record.job_id),showIrilaReport()));
      actions.append(check);
      const download=element("button","secondary","↓ Скачать");
      download.type="button";download.addEventListener("click",()=>record.profile==="t23n_sd"
        ?downloadImage(record.job_id):(selectIrila(record.job_id),downloadIrilaReport()));
      actions.append(download);
      const remove=element("button","danger","🗑 Удалить");
      remove.type="button";remove.addEventListener("click",()=>deleteLocalArtifact(record));
      actions.append(remove);
    }
    item.append(info,actions);list.append(item);
  }
  if(!records.some(a=>a.profile==="t23n_sd"))camera.append(element("p","empty","Сборок SD пока нет"));
  if(!records.some(a=>a.profile==="irila_preflight"))irila.append(element("p","empty","Пока нет локальных аудитов"));
  const baseline=(data.images||[]).find(x=>String(x.label||"").startsWith("Эталон 0.1_test"));
  if(baseline){
    const locked=element("div","artifact factory-output-row");
    const info=element("div","artifact-info");
    info.append(element("strong","","Эталон восстановления 0.1_test · защищён"),
      element("small","",baseline.name+" · "+size(baseline.bytes)),
      element("small","factory-protected","Исторический проверенный SD boot; не результат новой сборки и не удаляется в фабрике."));
    locked.append(info);camera.append(locked);
  }
}
async function deleteLocalArtifact(record){
  const kind=record.profile==="t23n_sd"?"SD-образ":"отчёт аудита";
  if(!confirm("Удалить только "+kind+" задания "+record.job_id.slice(0,8)+
     " с Huananzhi? История, журнал, исходники Git и остальные образы сохранятся."))return;
  const phrase="УДАЛИТЬ "+record.job_id.slice(0,8);
  if(prompt("Для подтверждения введи: "+phrase)!==phrase)return;
  try{
    const res=await api("/api/jobs/"+record.job_id+"/artifacts/delete",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirm:"DELETE-LOCAL-ARTIFACT:"+record.job_id})
    });
    toast("Файл удалён: освобождено "+size(res.bytes_freed)+". Журнал сохранён.");
    await refresh();
  }catch(error){toast("Не удалено: "+error.message);}
}
async function refreshGitHubArtifacts(project){
  const id=project==="irila"?"irilaGithubArtifactList":"wificamGithubArtifactList";
  const container=$(id);container.replaceChildren(element("p","muted","Читаем GitHub Actions через gh на CORE…"));
  try{
    const res=await api("/api/projects/"+project+"/github-artifacts");
    container.replaceChildren();
    if(!res.artifacts.length)container.append(element("p","muted","GitHub Actions-артефактов пока нет."));
    for(const artifact of res.artifacts){
      const row=element("div","factory-gh-output");
      row.append(element("strong","",artifact.name),
                 element("small","",size(artifact.bytes)+" · "+date(artifact.created_at)+
                   " · "+(artifact.expired?"Срок хранения истёк":"Сохранён в GitHub")));
      if(artifact.sha)row.append(element("code","","Git "+artifact.sha.slice(0,12)));
      const link=element("a","secondary","↗ Открыть и скачать в GitHub");
      link.href=artifact.url;link.target="_blank";link.rel="noopener noreferrer";
      row.append(link);
      const check=element("a","secondary","✓ Проверка CI / журнал");
      check.href=artifact.url;check.target="_blank";check.rel="noopener noreferrer";
      row.append(check);
      if(res.deletion_enabled&&!artifact.expired){
        const remove=element("button","danger","🗑 Удалить из GitHub Actions");
        remove.type="button";remove.addEventListener("click",()=>deleteGitHubArtifact(project,artifact));
        row.append(remove);
      }
      container.append(row);
    }
  }catch(error){
    container.replaceChildren(element("p","muted","Список GitHub недоступен: "+error.message+
      " · Используй ссылку GitHub Actions. Для доступа нужен авторизованный gh CLI на CORE."));
  }
}
async function deleteGitHubArtifact(project,artifact){
  const promptValue="УДАЛИТЬ GH "+artifact.id;
  if(!confirm("Удалить ТОЛЬКО Actions-артефакт #"+artifact.id+
       " из проекта "+project+" на GitHub? Коммиты и исходники НЕ удаляются."))return;
  if(prompt("Введи точно: "+promptValue)!==promptValue)return;
  try{
    await api("/api/projects/"+project+"/github-artifacts/"+artifact.id+"/delete",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirm:"DELETE-GITHUB-ACTIONS:"+project+":"+artifact.id})
    });
    toast("GitHub Actions-артефакт удалён; исходники и Git-история сохранены.");
    await refreshGitHubArtifacts(project);
  }catch(error){toast("GitHub не очищен: "+error.message);}
}
async function dispatchIrilaBuild(){
  if(!confirm("Запустить утверждённый GitHub Actions workflow сборки Irila IMG из main? "+
    "Сборка не выполняется на Huananzhi; для удалённого запуска нужен gh auth."))return;
  try{
    await api("/api/projects/irila/github-build",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirm:"RUN-IRILA-GITHUB-BUILD"})
    });
    toast("Отправлен запрос в GitHub Actions. Результат ещё неизвестен; следи за журналом workflow.");
    await refreshGitHubArtifacts("irila");
  }catch(error){toast("GitHub IMG не запущен: "+error.message);}
}
function renderBuildTimeline(job) {
  $text("buildStarted","Начало: "+date(job?.started_at));
  $text("buildFinished","Конец: "+date(job?.finished_at));
  $text("buildElapsed","Длительность: "+clockDuration(job?.elapsed_seconds));
  const bar=$("buildProgressFill"), track=$("buildProgressTrack");
  const percent=job?.progress_percent;
  bar.classList.toggle("indeterminate",percent===null||percent===undefined);
  bar.style.width=(percent===null||percent===undefined)?"35%":percent+"%";
  if(percent===null||percent===undefined)track.removeAttribute("aria-valuenow");
  else track.setAttribute("aria-valuenow",String(percent));
  const label=job?.status==="success"?"Сборка завершена · 100%":
    job?.status==="running" && job?.estimate_seconds ?
       "Ориентир по "+job.estimate_samples+" прошлым сборкам · "+
       percent+"% по времени"+(job.eta_seconds===null?" · дольше прогноза":
         " · осталось около "+clockDuration(job.eta_seconds)):
    job?.status==="running"?"Сборка идёт · нет исторических данных для ETA":
    job?.status==="queued"?"Ожидание systemd":job?.status==="failed"?
      "Завершилось с ошибкой":"Прогресс —";
  $text("buildProgressText",label+" · фактический процент компиляции неизвестен");
}
function renderSavedValidation(job) {
  const report=$("preflightReport");
  const result=job?.validation;
  if(!result){report.hidden=true;return;}
  report.hidden=false;
  $text("preflightStatus",result.verified?"✓ Проверено: структура SD":
    "Проверка устарела");
  $text("preflightDetails",result.verified?
    "SHA256 "+result.sha256+" · MBR, LBA34, FAT16/uImage, ext4 · физическая камера НЕ проверена":
    result.message||"Повторите проверку");
  const img=$("preflightDiagram");
  img.hidden=!result.verified;
  if(result.verified)img.src="/api/jobs/"+job.id+"/layout.svg";
  else img.removeAttribute("src");
}
async function validateSelected(){
  if(!selected)return;
  const job=overview?.jobs?.find(j=>j.id===selected);
  if(!job || job.status!=="success"){toast("Сначала нужна завершённая сборка");return;}
  $("validateBuild").disabled=true;
  $text("preflightStatus","Проверяем байты образа...");
  $("preflightReport").hidden=false;
  try{
    const result=await api("/api/jobs/"+selected+"/validate",{method:"POST"});
    $text("preflightStatus",result.verified?"✓ Проверка структуры пройдена":"Проверка не пройдена");
    $text("preflightDetails",result.verified?
      "SHA256 "+result.sha256+" · MSPL LBA34 · BOOT FAT16/uImage · ROOTFS ext4":
      result.error);
    $("preflightDiagram").hidden=!result.verified;
    if(result.verified)$("preflightDiagram").src="/api/jobs/"+selected+"/layout.svg?ts="+Date.now();
    toast("Проверена структура образа. Аппаратный тест ещё требуется.");
  }catch(e){
    $("preflightDiagram").hidden=true;
    $text("preflightStatus","✕ Структура не прошла проверку");
    $text("preflightDetails",e.message);
    toast("Проверка не пройдена: "+e.message);
  }finally{await refresh();}
}
async function refresh() {
  if(loading)return;
  loading=true;
  try {const data=await api("/api/overview");renderOverview(data);$("connection").textContent="На связи";}
  catch(e){$("connection").textContent="Нет связи";}
  finally{loading=false;}
  if(location.hash==="#builds")refreshLog();
  if(location.hash==="#irila")refreshIrilaLog();
}
async function refreshLog() {
  // A browser refresh must NOT replay an archived 9-MB log as if it were
  // a new compilation. Start at EOF - 64 KiB; only poll new output on
  // genuinely active jobs. Historical full playback requires a user click.
  if(!selected||refreshedLog||logFinalized)return;
  refreshedLog=true;
  const selectedAtStart=selected;
  const initial=logInitial && !logFullRequested;
  try{
    const path="/api/jobs/"+selected+"/log?"+(initial?"tail=1":"offset="+offset);
    const result=await api(path);
    if(selectedAtStart!==selected)return;
    const terminal=$("log");
    if(initial){
      terminal.textContent=result.archive?
        "АРХИВ ЗАВЕРШЁННОЙ СБОРКИ — это сохранённые строки, новая компиляция не запущена.\n"+
        (result.truncated?"Показаны последние 64 КиБ. Для полного вывода нажми «Показать полный архив».\n":"")+"\n":
        "СБОРКА АКТИВНА — показываются последние строки, далее только новые сообщения.\n\n";
    }else if(offset===0)terminal.textContent="";
    if(result.text){
      const nearBottom=terminal.scrollHeight-terminal.scrollTop-terminal.clientHeight<100;
      terminal.textContent+=result.text;
      if(terminal.textContent.length>350000)terminal.textContent=terminal.textContent.slice(-250000);
      if(nearBottom)terminal.scrollTop=terminal.scrollHeight;
    }
    if(!result.text&&!initial&&offset===0)terminal.textContent="Журнал пока пуст.\n";
    offset=result.offset;
    logInitial=false;
    $text("logBytes",size(offset));
    if(!active.has(result.status) && !result.more){
      logFinalized=true;
      logFullRequested=false;
    }
    if(result.more)setTimeout(()=>{refreshedLog=false;refreshLog();},200);
  }catch(e){$("connection").textContent="Ошибка журнала";}
  finally{refreshedLog=false;}
}

async function downloadImage(jobId){
  // One click: the UI passes an existing successful job ID internally.
  // Server restricts private export to the trusted LAN, and re-checks the
  // finished raw image's SHA256/MBR/MSPL/FAT16/ext4 before sending bytes.
  const button=document.activeElement;
  if(button && button.tagName==="BUTTON")button.disabled=true;
  toast("Проверяем SHA256 и готовим .img — без повторной компиляции…");
  try {
    const response=await fetch("/api/jobs/"+jobId+"/download",{
      method:"POST", credentials:"same-origin", cache:"no-store",
      headers:{"X-PegineLab-Action":"1"}
    });
    if(!response.ok){
      let message="Ошибка HTTP "+response.status;
      try{message=(await response.json()).error||message;}catch(_e){}
      throw new Error(message);
    }
    const blob=await response.blob();
    const name="WIFICAM_T23N_"+jobId.slice(0,8)+".img";
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a");
    a.href=url; a.download=name; a.style.display="none";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    toast("Образ скачан. Сверьте SHA256, затем запишите на SD с LBA0.");
    await refresh();
  }catch(e){
    toast("Не удалось скачать: "+e.message);
  }finally {
    if(button && button.tagName==="BUTTON" && button.isConnected)button.disabled=false;
  }
}
function shortSha(sha) { return sha ? sha.slice(0,12) : "—"; }
const stepOrder=["queued","fetch","checkout","dependencies","tests","restart","done"];
function renderUpdateSteps(data){
  // During failure the backend reports step="failed"; highlight the
  // last real stage using persisted index instead of losing its position.
  const index=data.phase==="failed" && Number.isInteger(data.step_index)
    ?Math.max(0,Math.min(6,data.step_index))
    :Math.max(0,stepOrder.indexOf(data.step||"queued"));
  const busy=["queued","running"].includes(data.phase);
  const success=data.phase==="success" && ["apply","rollback"].includes(data.action);
  const failed=data.phase==="failed";
  // The update checker has no installer steps; hide the timeline for checks.
  const visible=["apply","rollback"].includes(data.action) &&
    (busy || success || failed);
  $("updateSteps").hidden=!visible;
  $("updateProgressFill").parentElement.hidden=!visible;
  $("updateProgressCaption").hidden=!visible;
  document.querySelectorAll("[data-update-step]").forEach(el=>{
    const i=stepOrder.indexOf(el.dataset.updateStep);
    el.classList.toggle("passed",visible && (success || i<index));
    el.classList.toggle("current",visible && busy && i===index);
    el.classList.toggle("failed",visible && failed && i===index);
  });
  const pct=success?100:Math.max(0,Math.round(Math.max(0,index)/6*100));
  $("updateProgressFill").style.width=pct+"%";
  $text("updateProgressCaption",failed?
    "Ошибка на этапе «"+(data.failed_step||data.step||"неизвестно")+"». Подробности ниже, в журнале обновления панели.":
    success?"Обновление завершено. Панель переподключается…":
    "Выполняется шаг "+(Math.max(0,index)+1)+" из 7 · "+(data.message||""));
  $("updateReconnect").hidden=!(busy && data.step==="restart");
}
function renderUpdate(data) {
  updateState=data;
  renderUpdateSteps(data);
  // Dedicated updater console, never append the selected kernel/firmware
  // job log from #builds to #system.
  const consoleEl=$("updateLog");
  const atBottom=consoleEl.scrollHeight-consoleEl.scrollTop-consoleEl.clientHeight<90;
  const body=(data.operation_log||"").trim();
  const viewText=body || "Ожидаем запуска проверки/обновления панели…";
  if(consoleEl.textContent!==viewText) consoleEl.textContent=viewText;
  if(atBottom) consoleEl.scrollTop=consoleEl.scrollHeight;
  $text("updateConsoleStatus",data.phase==="failed"?"Ошибка — смотри конец журнала":
    ["queued","running"].includes(data.phase)?"Выполняется "+(data.action||"операция"):
    data.phase==="success"?"Последняя операция завершена":"Отдельный журнал установщика");
  const isBusy=["queued","running"].includes(data.phase);
  const buildBusy=!!(overview?.jobs||[]).find(j=>active.has(j.status));
  $text("updateInstalled",shortSha(data.installed_sha));
  $text("updateRemote",shortSha(data.remote_sha));
  $text("updatePrevious",data.rollback_sha ? shortSha(data.rollback_sha) : "Нет сохранённой");
  $text("updateMessage",data.message || "Проверить GitHub main на наличие новой версии.");
  let label=data.phase==="failed" ? "Ошибка обновления" :
    isBusy ? "Выполняется: "+data.action :
    data.update_available ? "Доступна новая версия" :
    data.checked_at ? "Обновлений нет" : "Не проверялось";
  $text("updateStatus",label);
  $("updateNotice").hidden=!data.update_available;
  $("checkUpdate").disabled=isBusy;
  $("applyUpdate").disabled=isBusy || buildBusy || !data.update_available;
  $("rollbackUpdate").disabled=isBusy || buildBusy || !data.rollback_available;
  if(overview)renderJobs();
  if(panelServiceState)renderPanelService(panelServiceState);
  if(isBusy && ["apply","rollback"].includes(data.action))updateHadActive=true;
  // Wait for recorded success (not merely HEAD changing), then reload once
  // to replace stale JS/CSS after Waitress has come back online.
  if(updateHadActive && !updateAutoReloaded && data.phase==="success" &&
     ["apply","rollback"].includes(data.action)){
    updateAutoReloaded=true;
    setTimeout(()=>window.location.reload(),1200);
  }
}
async function refreshUpdate(automatic=false) {
  if(checkingUpdate)return;
  checkingUpdate=true;
  try {
    const state=await api("/api/update");
    renderUpdate(state);
    const checked=state.checked_at?Date.parse(state.checked_at):0;
    const stale=!checked || (Date.now()-checked>15*60*1000);
    if(automatic && stale && !["queued","running","failed"].includes(state.phase) &&
       Date.now()-lastAutoCheck>15*60*1000) {
      lastAutoCheck=Date.now();
      await api("/api/update/check",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
      renderUpdate(await api("/api/update"));
    }
  }catch(e){
    if(updateState && ["queued","running"].includes(updateState.phase)){
      $("updateReconnect").hidden=false;
      $text("updateReconnect","Веб-панель временно недоступна. Проверяем связь автоматически…");
    }else if(!updateState)$text("updateMessage","GitHub-проверка недоступна: "+e.message);
  }finally{checkingUpdate=false;}
}
async function updateAction(action) {
  const state=updateState||{};
  const label=action==="check"?"Проверить новую версию на GitHub?":
    action==="apply"?"Обновить YadroKreator? Веб-панель кратко перезапустится; историю сборок и прошивки это не затронет.":
    "Откатить YadroKreator на предыдущую сохранённую версию? Панель перезапустится.";
  if(action!=="check" && !confirm(label))return;
  try {
    await api("/api/update/"+action,{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(action==="apply"?{expected_sha:state.remote_sha}:{})});
    toast(action==="check"?"Проверка GitHub запущена":"Операция отправлена в systemd");
    await refreshUpdate();
  }catch(e){toast(e.message);}
}
function renderPanelService(data) {
  panelServiceState=data;
  const running=data.state==="active";
  const readable={active:"● Работает",inactive:"■ Остановлена",failed:"Ошибка службы",
    activating:"Запускается",deactivating:"Останавливается",
    reloading:"Перезапуск",unknown:"Не удалось проверить"};
  for(const id of ["panelServiceStatus","systemServiceStatus"]){
    $(id).textContent=readable[data.state] || readable.unknown;
  }
  for(const id of ["panelServiceMessage","systemServiceMessage"]){
    $(id).textContent=panelReconnect?"Перезапуск: ждём восстановления страницы…":
      data.message || "Управление системной службой Huananzhi";
  }
  const busy=panelActionBusy || ["queued","running"].includes(updateState?.phase);
  const activeBuild=!!(overview?.jobs||[]).find(j=>active.has(j.status));
  ["panelStart","systemStart"].forEach(id=>$(id).disabled=true);
  ["panelRestart","systemRestart"].forEach(id=>$(id).disabled=!running||busy);
  ["panelStop","systemStop"].forEach(id=>$(id).disabled=!running||busy);
}
async function refreshPanelService() {
  try {
    const state=await api("/api/panel/service");
    renderPanelService(state);
    if(panelReconnect && Date.now()>=panelReconnectAfter && state.state==="active"){
      panelReconnect=false;
      window.location.reload();
    }
  }catch(e){
    if(panelReconnect) {
      ["panelServiceMessage","systemServiceMessage"].forEach(id=>$(id).textContent=
        "Перезапуск службы. Соединение временно недоступно…");
    }else {
      renderPanelService({state:"unknown",message:"Статус недоступен: "+e.message});
    }
  }
}
async function panelServiceAction(action) {
  if(panelActionBusy)return;
  const text=action==="stop-all"?
    "ПОЛНОСТЬЮ остановить YadroKreator? Будут остановлены его systemd-сборки, служба и таймер обновления, а также контейнеры с меткой этого проекта, если есть. Ubuntu, SSH и чужие проекты останутся работать. Запуск снова — через SSH, bash start.sh.":
    "Перезапустить ТОЛЬКО веб-панель :62404? Браузер временно потеряет связь, сборки останутся отдельно.";
  if(!confirm(text))return;
  const buildBusy=!!(overview?.jobs||[]).find(j=>active.has(j.status));
  if(action==="stop-all" && buildBusy &&
     !confirm("Есть активная сборка! Полная остановка ПРЕРВЁТ компиляцию и текущий кандидат образа. Отменить сборку и остановить проект?"))return;
  panelActionBusy=true;
  if(panelServiceState)renderPanelService(panelServiceState);
  try {
    await api("/api/panel/service/"+action,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({confirm:action.toUpperCase(),cancel_builds:action==="stop-all"&&buildBusy})
    });
    if(action==="stop-all"){
      ["panelServiceMessage","systemServiceMessage"].forEach(id=>
        $(id).textContent="Полная остановка проекта запланирована. Для запуска: SSH на Huananzhi → bash start.sh");
      toast("Все задачи YadroKreator выключаются; восстановление через SSH");
    }else{
      panelReconnect=true;
      panelReconnectAfter=Date.now()+3500;
      toast("Перезапускаем панель. Восстановление страницы автоматически…");
    }
  }catch(e){toast("Действие не выполнено: "+e.message);}
  finally {
    panelActionBusy=false;
    if(!panelReconnect && panelServiceState)renderPanelService(panelServiceState);
  }
}
async function start() {
  const branch=$("sourceBranch").value;
  const helper_preset=$("helperPreset").checked;
  if(!confirm("Получить "+branch+" напрямую с GitHub и собрать из точного коммита?" +(helper_preset?" С утверждённым профилем WifCam Helper.":"") +" Новый образ останется на сервере, камера не прошивается."))return;
  try {
    const r=await api("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({profile:"t23n_sd",branch,helper_preset})});
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
  $("newBuild").addEventListener("click",start);
  $("sourceBranch").addEventListener("change",updateHelperBranchCompatibility);
  // WIFICAM build, image inventory and log are on the same page.
  for(const button of document.querySelectorAll("[data-project-subtab]")){
    button.addEventListener("click",()=>setProjectSubtab(
      button.dataset.projectSubtab,button.dataset.target));
  }
  setProjectSubtab("helper","helperStatus");
  $("registryMode").addEventListener("change",()=>{
    $("registryModeHint").textContent=$("registryMode").value==="build"
      ?"Обязателен peginelab.project.json в корне ветки GitHub; пока нет утверждённого адаптера — компиляция недоступна."
      :"Только вручную выбранный репозиторий. Ни сборка, ни опрос метрик не включаются автоматически.";
  });
  $("registerWificamBranch").addEventListener("submit",event=>{
    event.preventDefault();void registerGitHub("branch");
  });
  $("registerGithubProject").addEventListener("submit",event=>{
    event.preventDefault();void registerGitHub("project");
  });
  $("activeJobOpen").addEventListener("click",()=>{
    const current=overview?.active_job && active.has(overview.active_job.status)
      ? overview.active_job : overview?.jobs?.find(j=>active.has(j.status));
    if(!current)return;
    if(current.profile==="t23n_sd")select(current.id);
    else if(current.profile==="irila_preflight")selectIrila(current.id);
    else toast("Для этого профиля ещё нет отдельного журнала");
  });
  $("stopBuild").addEventListener("click",stop);
  $("irilaCheck").addEventListener("click",runIrilaAudit);
  $("irilaStop").addEventListener("click",stopIrila);
  $("irilaReport").addEventListener("click",showIrilaReport);
  $("irilaExport").addEventListener("click",downloadIrilaReport);
  $("validateBuild").addEventListener("click",validateSelected);
  $("downloadSelected").addEventListener("click",()=>selected&&downloadImage(selected));
  $("deleteSelectedArtifact").addEventListener("click",()=>{
    const rec=(overview?.artifact_records||[]).find(a=>a.job_id===selected);
    if(rec?.available)void deleteLocalArtifact(rec);
  });
  $("irilaDeleteArtifact").addEventListener("click",()=>{
    const rec=(overview?.artifact_records||[]).find(a=>a.job_id===selectedIrila);
    if(rec?.available)void deleteLocalArtifact(rec);
  });
  $("irilaGithubBuild").addEventListener("click",dispatchIrilaBuild);
  $("irilaGithubRefresh").addEventListener("click",()=>refreshGitHubArtifacts("irila"));
  $("wificamGithubRefresh").addEventListener("click",()=>refreshGitHubArtifacts("builds"));
  $("checkUpdate").addEventListener("click",()=>updateAction("check"));
  $("applyUpdate").addEventListener("click",()=>updateAction("apply"));
  $("rollbackUpdate").addEventListener("click",()=>updateAction("rollback"));
  ["panelRestart","systemRestart"].forEach(id=>$(id).addEventListener("click",()=>panelServiceAction("restart")));
  ["panelStop","systemStop"].forEach(id=>$(id).addEventListener("click",()=>panelServiceAction("stop-all")));
  $("systemRefresh").addEventListener("click",refreshPanelService);
  $("helperRefresh").addEventListener("click",refreshHelper);
  ["start","stop","restart"].forEach(action=>{
    const id="helper"+action.charAt(0).toUpperCase()+action.slice(1);
    $(id).addEventListener("click",()=>helperAction(action));
  });

  $("clearView").addEventListener("click",()=>{
    offset=0; logInitial=true;logFinalized=false;logFullRequested=false;
    $("log").textContent="";refreshLog();
  });
  $("fullBuildLog").addEventListener("click",()=>{
    if(!selected)return;
    logFullRequested=true;logInitial=false;logFinalized=false;offset=0;
    $("log").textContent="Загружается полный архив по запросу пользователя…\n";
    refreshLog();
  });
  await refresh();
  await refreshUpdate(true);
  await refreshPanelService();
  await refreshHelper();
  setInterval(()=>{refresh();if(location.hash==="#builds")refreshLog();if(location.hash==="#irila")refreshIrilaLog();},2500);
  setInterval(()=>refreshUpdate(true),15000);
  setInterval(refreshPanelService,15000);
  setInterval(()=>{if(location.hash==="#helper")refreshHelper()},15000);
  setInterval(()=>$text("clock",new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})),15000);
  window.addEventListener("focus",refresh);
}
document.addEventListener("DOMContentLoaded",init);
})();
