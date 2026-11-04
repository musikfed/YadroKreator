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
  const valid=["overview","builds","irila","helper","artifacts","system"];
  const current=valid.includes(tab)?tab:"overview";
  const names={overview:"Обзор",builds:"WIFICAM T23N",irila:"Irila Baikal",helper:"WifCam Helper",artifacts:"Образы WIFICAM",system:"Система"};
  document.querySelectorAll("[data-panel]").forEach(el=>el.hidden=el.dataset.panel!==current);
  document.querySelectorAll("[data-tab]").forEach(el=>el.classList.toggle("active",el.dataset.tab===current));
  $text("pageName",names[current]);document.title="PegineLab · "+names[current];
  if(current==="builds") refreshLog();
  if(current==="irila") refreshIrilaLog();
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
  $("irilaExport").disabled=!irilaCurrent||irilaCurrent.status!=="success";
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
  $("validateBuild").disabled=!selectedJob || selectedJob.status!=="success";
  renderSavedValidation(selectedJob);
  if(panelServiceState)renderPanelService(panelServiceState);
}
function renderOverview(data) {
  overview=data;renderJobs();
  $text("wificamBuildRoot",data.paths.wificam_build);
  $text("irilaBuildRoot",data.paths.irila_build);
  $text("helperSourcePath",data.paths.helper);
  if(Array.isArray(data.allowed_branches)){
    for(const option of $("sourceBranch").options)option.disabled=!data.allowed_branches.includes(option.value);
  }
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
    if(image.job_id){
      const actions=element("div","artifact-actions");
      const checked=image.validation?.verified===true;
      actions.append(element("small","",checked?"✓ Структура проверена":
        "Проверка будет выполнена при скачивании (без пересборки)"));
      const button=element("button","secondary","✓ Проверить SD");
      button.addEventListener("click",()=>{select(image.job_id);validateSelected();});
      actions.append(button);
      const download=element("button","secondary","↓ Скачать образ .img");
      // A successful job already contains a complete SD candidate. The
      // server validates its real bytes automatically during download.
      download.disabled=false;
      download.title=checked?"Скачать проверенный образ с сервера":
        "Скачать готовый образ; SHA256 и SD-разделы будут проверены автоматически";
      download.addEventListener("click",()=>downloadImage(image.job_id));
      actions.append(download);
      // The opaque internal job UUID never needs to be typed by the user.
      item.append(actions);
    }
    item.append(icon,info);artifacts.append(item);
  }
  $text("pathRoot",data.paths.root);
  $text("pathProject",data.paths.project);
  $text("pathThingino",data.paths.thingino);
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
  $("checkUpdate").addEventListener("click",()=>updateAction("check"));
  $("applyUpdate").addEventListener("click",()=>updateAction("apply"));
  $("rollbackUpdate").addEventListener("click",()=>updateAction("rollback"));
  ["panelRestart","systemRestart"].forEach(id=>$(id).addEventListener("click",()=>panelServiceAction("restart")));
  ["panelStop","systemStop"].forEach(id=>$(id).addEventListener("click",()=>panelServiceAction("stop-all")));
  $("systemRefresh").addEventListener("click",refreshPanelService);

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
  setInterval(()=>{refresh();if(location.hash==="#builds")refreshLog();if(location.hash==="#irila")refreshIrilaLog();},2500);
  setInterval(()=>refreshUpdate(true),15000);
  setInterval(refreshPanelService,15000);
  setInterval(()=>$text("clock",new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"})),15000);
  window.addEventListener("focus",refresh);
}
document.addEventListener("DOMContentLoaded",init);
})();
