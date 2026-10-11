'use strict';
const $ = id => document.getElementById(id);
const ui = {boot:null, current:null, sessions:[], source:null, activeId:null, traceOpen:innerWidth>1024, sidebarOpen:false, sending:false, messageKey:'', attachmentKey:'', stepRows:[], drafts:new Map()};
function el(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function icon(name){const n=el('img');n.src=`/static/icons/${name}.svg`;n.alt='';return n;}
function notice(text=''){$('notice').textContent=text;$('notice').hidden=!text;}
function nearBottom(n){return n.scrollHeight-n.scrollTop-n.clientHeight<70;}
function stored(key,value){try{if(value===undefined)return localStorage.getItem(key);if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}catch{}return null;}
async function api(path, data){const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-Comma-Token':ui.boot.csrf_token},body:data===undefined?undefined:JSON.stringify(data)});const value=await response.json();if(!response.ok)throw new Error(value.error||`请求失败 (${response.status})`);return value;}
function settings(){return {model:$('model').value,perception:$('perception').value,task_id:ui.current?.experiment||'free'};}
function applySettings(value){if(!Array.from($('model').options).some(o=>o.value===value.model)){const option=el('option','',value.model.split('/').pop()+' · 历史模型');option.value=value.model;$('model').append(option);}$('model').value=value.model;$('perception').value=value.perception||'vision';updateHint();}
function updateHint(){const task=ui.boot.tasks.find(t=>t.id===(ui.current?.settings.task_id||'free'));$('perception-label').hidden=ui.boot.lesson<2;$('task-hint').textContent=task?.id==='free'?'自由探索 · Enter 发送，Shift + Enter 换行':task?.title||'';$('task-hint').title=task?.note||'';}
function panels(){document.querySelector('.workspace').classList.toggle('trace-hidden',!ui.traceOpen);$('toggle-trace').classList.toggle('active',ui.traceOpen);$('toggle-trace').setAttribute('aria-expanded',String(ui.traceOpen));$('sidebar').classList.toggle('open',ui.sidebarOpen);$('scrim').hidden=!(ui.sidebarOpen||(ui.traceOpen&&innerWidth<=1024));}
function disconnect(){ui.source?.close();ui.source=null;}
function connect(id){disconnect();const source=new EventSource(`/api/sessions/${id}/events`);ui.source=source;source.addEventListener('snapshot',event=>{if(ui.current?.id!==id)return;const before=ui.current.busy;render(JSON.parse(event.data));$('connection').textContent='本机服务已连接';if(before!==ui.current.busy)refreshSessions();});source.onerror=()=>{$('connection').textContent='连接中断，正在重连…';};source.onopen=()=>{$('connection').textContent='本机服务已连接';};}
async function refreshSessions(){const result=await api('/api/sessions');ui.sessions=result.sessions;ui.activeId=result.active_id;renderSessions();controls();}
function renderSessions(){
  const search=$('search').value.toLowerCase();
  const row=s=>{
    const button=el('button','session'+(ui.current?.id===s.id?' active':'')+(s.busy?' running':''));
    button.type='button';button.title=s.title;button.setAttribute('aria-label',s.title);
    if(ui.current?.id===s.id)button.setAttribute('aria-current','true');
    button.append(icon(s.experiment?'read':'chat'));
    const body=el('span','session-content');body.append(el('span','session-title',s.title));
    const state=s.busy?'执行中':s.readonly?'已保存':({error:'出错',cancelled:'已停止',timeout:'超时',ready:'未开始',completed:'已完成',waiting:'等待继续'}[s.status]||'会话');
    body.append(el('small','',`${s.experiment?'固定实验':(s.settings.model||'').split('/').pop()} · ${state}`));
    button.append(body);button.onclick=()=>openSession(s.id);return button;
  };
  const matches=ui.sessions.filter(s=>s.title.toLowerCase().includes(search));
  $('experiments').replaceChildren(...matches.filter(s=>s.experiment).map(row));
  const nodes=matches.filter(s=>!s.experiment&&!s.legacy).map(row);
  if(!nodes.length)nodes.push(el('div','section-label',search?'没有匹配的会话':'你的对话会保存在这里'));
  $('sessions').replaceChildren(...nodes);
  $('session-count').textContent=ui.sessions.filter(s=>!s.experiment&&!s.legacy).length||'';
  const legacy=matches.filter(s=>s.legacy);
  $('legacy-history').hidden=!legacy.length;
  $('legacy-count').textContent=legacy.length;
  $('legacy-sessions').replaceChildren(...legacy.map(row));
  if(search||ui.current?.legacy)$('legacy-history').open=true;
}
function setPrompt(value){$('prompt').value=value;$('prompt').style.height='auto';$('prompt').style.height=Math.min($('prompt').scrollHeight,160)+'px';}
async function openSession(id){
  try{
    if(ui.current)ui.drafts.set(ui.current.id,$('prompt').value);
    notice();const snapshot=await api(`/api/sessions/${id}`);
    disconnect();ui.current=null;resetViews();applySettings(snapshot.settings);render(snapshot);
    setPrompt(ui.drafts.get(id)??(!snapshot.messages.length?snapshot.initial_prompt||'':''));controls();
    stored('comma-session',id);ui.sidebarOpen=false;panels();renderSessions();
    if(!snapshot.readonly)connect(id);else $('connection').textContent='已保存的运行记录';
  }catch(error){notice(error.message);}
}
function renderExperiment(snapshot){
  const task=snapshot?.experiment;
  $('experiment-intro').hidden=!task||!!snapshot.messages.length;
  $('reset-experiment').hidden=!task;
  if(task){$('experiment-title').textContent=snapshot.title;$('experiment-note').textContent=snapshot.experiment_note;}
  $('readonly-copy').textContent=task?'这是上次保存的实验。点击右上角“重置实验”即可重新开始。':'这是旧版逐轮记录，未保存完整续聊上下文。';
  $('continue-new').hidden=!!task;
}
function resetViews(){ui.messageKey='';ui.attachmentKey='';ui.stepRows=[];$('messages').replaceChildren();$('steps').replaceChildren();$('attachments').replaceChildren();$('run-links').replaceChildren();$('run-history').hidden=true;}
function newChat(preserve=false){disconnect();ui.current=null;renderExperiment(null);updateHint();stored('comma-session',null);resetViews();notice();if(!preserve)applySettings({model:ui.boot.default_model,perception:'vision',task_id:'free'});if(!ui.boot.models.includes($('model').value))$('model').value=ui.boot.default_model;$('prompt').value='';$('prompt').style.height='';$('chat-title').textContent='新对话';$('welcome').hidden=false;$('trace-current').textContent='等待开始';$('trace-stats').textContent='工具调用与结果将在这里实时显示';$('trace-empty').hidden=false;$('connection').textContent='本机服务已连接';$('export').removeAttribute('href');$('export').classList.add('disabled');ui.sidebarOpen=false;panels();renderSessions();controls();renderLearning();$('prompt').focus();}
function controls(){const busy=!!ui.current?.busy, readonly=!!ui.current?.readonly, elsewhere=ui.activeId&&ui.activeId!==ui.current?.id;$('awaiting-step').hidden=!ui.current?.awaiting_continue||busy||readonly;$('continue-step').disabled=ui.sending||!!elsewhere;$('clear-history').disabled=ui.sending||!ui.sessions.some(session=>!session.experiment&&session.id!==ui.current?.id&&session.id!==ui.activeId);$('send').hidden=busy;$('stop').hidden=!busy;$('stop').disabled=ui.sending;$('send').disabled=readonly||ui.sending||elsewhere||!$('prompt').value.trim();$('check').disabled=busy||readonly||ui.sending||!!elsewhere;$('prompt').disabled=readonly||ui.sending;$('prompt').placeholder=elsewhere?'另一会话正在执行，请先等待完成…':ui.current?.awaiting_continue?'补充要求，或点击“继续下一步”…':'给模型一个任务…';$('readonly').hidden=!readonly;$('composer').hidden=readonly;$('reset-experiment').disabled=busy||ui.sending;for(const id of ['model','perception']){$(id).disabled=busy||ui.sending||!!(ui.current?.experiment&&ui.current.messages.length);$(id).title=ui.current?.experiment&&ui.current.messages.length?'重置实验后可更换设置':'';}$('status-dot').classList.toggle('busy',busy);}
function messageContent(node,text){const blocks=String(text).split(/```[^\n]*\n([\s\S]*?)```/g);blocks.forEach((part,index)=>{if(index%2){const pre=el('pre');pre.append(el('code','',part));node.append(pre);}else node.append(document.createTextNode(part));});}
function renderMessages(snapshot){const key=JSON.stringify([snapshot.messages,snapshot.busy]);if(key===ui.messageKey)return;ui.messageKey=key;const scroll=$('chat-scroll'),bottom=nearBottom(scroll);const fragment=document.createDocumentFragment();for(const message of snapshot.messages){const article=el('article',`message ${message.role}`);const label=el('div','message-label');if(message.role==='assistant')label.append(icon('agent'));label.append(document.createTextNode(message.role==='user'?'你':snapshot.settings.model.split('/').pop()));const body=el('div','message-content');messageContent(body,message.text);article.append(label,body);fragment.append(article);}if(snapshot.busy)fragment.append(el('div','pending-reply','正在执行，工具步骤会实时出现在右侧'));$('messages').replaceChildren(fragment);if(bottom)scroll.scrollTop=scroll.scrollHeight;}
function readableToolOutput(text){
  try{
    const data=JSON.parse(text);
    if(data&&typeof data==='object'&&!Array.isArray(data)){
      const field=typeof data.content==='string'?'content':typeof data.diff==='string'?'diff':null;
      if(field){const body=data[field];delete data[field];return body+'\n\n'+JSON.stringify(data,null,2);}
    }
    return JSON.stringify(data,null,2);
  }catch{return text;}
}
function renderSteps(trace){const scroll=$('trace-scroll'),bottom=nearBottom(scroll);trace.steps.forEach((step,i)=>{let row=ui.stepRows[i];if(!row){row=el('li','step');const symbol=el('span','step-icon'),body=el('div','step-body');body.append(el('div','step-title'),el('div','step-detail'),el('div','step-meta'));const output=el('details','tool-output');output.append(el('summary','','查看工具输出'),el('pre'));body.append(output);row.append(symbol,body);$('steps').append(row);ui.stepRows.push(row);}const key=JSON.stringify(step);if(row.dataset.state===key)return;row.dataset.state=key;row.className=`step ${step.status}`;const symbol=step.status==='error'?'close':step.status==='done'?'check':({list_files:'search',read_course_file:'read',check_agent:'check',edit_course_file:'edit',search_file:'search',read_file:'read',edit:'edit',bash:'command',get_window_state:'eye',click:'monitor'}[step.tool]||'think');row.firstChild.replaceChildren(icon(symbol));row.querySelector('.step-title').textContent=step.title;row.querySelector('.step-detail').textContent=step.detail;const output=row.querySelector('.tool-output');output.hidden=!step.output;output.querySelector('pre').textContent=readableToolOutput(step.output||'');row.querySelector('.step-meta').textContent=[step.number?`#${step.number}`:'',step.repeat_of?`同 #${step.repeat_of} 参数 · 第 ${step.repeat_count} 次`:'',step.duration!=null?`${step.duration.toFixed(1)}s`:''].filter(Boolean).join(' · ');});$('trace-empty').hidden=trace.steps.length>0;if(bottom)scroll.scrollTop=scroll.scrollHeight;}
function renderRunLinks(snapshot){
  const runs=snapshot.runs||[];
  $('run-history').hidden=!runs.length;
  $('run-count').textContent=`(${runs.length})`;
  $('run-links').replaceChildren(...runs.map((run,i)=>{const a=el('a','',`第 ${i+1} 轮 · ${run.title}`);a.href=`/api/runs/${run.id}/export`;a.setAttribute('download','');return a;}));
}
function renderAttachments(snapshot){const key=JSON.stringify([snapshot.images,snapshot.code_file,snapshot.run_id]);if(key===ui.attachmentKey)return;ui.attachmentKey=key;const nodes=snapshot.images.map((image,i)=>{const b=el('button');b.type='button';b.setAttribute('aria-label',`查看截图 ${i+1}`);const img=el('img');img.src=image.url;img.alt=`观察截图 ${i+1}`;img.loading='lazy';b.append(img);b.onclick=()=>{$('full-image').src=image.url;$('image-dialog').showModal();};return b;});if(snapshot.code_file){const a=el('a','', '查看本轮代码文件 ↗');a.href=`/api/runs/${snapshot.run_id}/files/${snapshot.code_file}`;a.target='_blank';a.rel='noopener';nodes.push(a);}$('attachments').replaceChildren(...nodes);}
function render(snapshot){if(snapshot.removed){newChat(true);refreshSessions().catch(error=>notice(error.message));return;}if(ui.current?.id===snapshot.id&&ui.current.messages.length&&!snapshot.messages.length){resetViews();ui.drafts.delete(snapshot.id);setPrompt(snapshot.initial_prompt||'');}ui.current=snapshot;renderExperiment(snapshot);updateHint();if(snapshot.learning){ui.boot.learning=snapshot.learning;renderLearning();}ui.activeId=snapshot.active_id;$('chat-title').textContent=snapshot.title;$('welcome').hidden=!!snapshot.experiment||snapshot.messages.length>0;renderMessages(snapshot);renderSteps(snapshot.trace);renderAttachments(snapshot);renderRunLinks(snapshot);$('trace-current').textContent=snapshot.trace.current;$('trace-stats').textContent=`${snapshot.trace.calls} 次调用 · ${snapshot.trace.errors} 次错误 · ${snapshot.trace.tokens.toLocaleString()} tokens`;if(snapshot.run_id){$('export').href=`/api/runs/${snapshot.run_id}/export`;$('export').classList.remove('disabled');}else{$('export').removeAttribute('href');$('export').classList.add('disabled');}controls();}
async function send(llmOnly=false){const text=llmOnly?'请只回复：LLM 接口已连接。':$('prompt').value.trim();if(!text||ui.sending||ui.current?.busy)return;ui.sending=true;notice();controls();try{if(!ui.current){ui.current=await api('/api/sessions',settings());stored('comma-session',ui.current.id);}const snapshot=await api(`/api/sessions/${ui.current.id}/messages`,{text,llm_only:llmOnly});render(snapshot);if(!llmOnly){ui.drafts.delete(snapshot.id);$('prompt').value='';$('prompt').style.height='';}connect(snapshot.id);await refreshSessions();$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;}catch(error){notice(error.message);}finally{ui.sending=false;controls();}}
async function clearHistory(){
  if($('clear-history').disabled)return;
  ui.sending=true;controls();notice();
  try{
    const result=await api('/api/sessions/clear-history',{keep_id:ui.current?.id||null});
    ui.sessions=result.sessions;ui.activeId=result.active_id;
    if(ui.current&&!ui.sessions.some(session=>session.id===ui.current.id))newChat(true);
    renderSessions();notice(result.cleared?`已清空 ${result.cleared} 条历史对话。`:'没有需要清理的历史对话。');
  }catch(error){notice(error.message);}
  finally{ui.sending=false;controls();}
}
$('clear-history').onclick=clearHistory;
async function chooseTask(id){
  if(id==='shell'){newChat(true);setPrompt('请使用 bash 工具输出 COMMA_SHELL_OK，并告诉我当前工作目录。');}
  else{const session=ui.sessions.find(s=>s.experiment===id);if(session)await openSession(session.id);}
  updateHint();controls();$('prompt').focus();
}
async function changeSettings(){
  const value=settings();if(!ui.boot.models.includes(value.model))value.model=ui.boot.default_model;
  if(ui.current?.experiment){
    const id=ui.current.id;ui.sending=true;controls();
    try{const snapshot=await api(`/api/sessions/${id}/settings`,{model:value.model,perception:value.perception});if(ui.current?.id===id)render(snapshot);await refreshSessions();}
    catch(error){if(ui.current?.id===id)applySettings(ui.current.settings);notice(error.message);}
    finally{ui.sending=false;controls();}
  }else{if(ui.current)newChat(true);applySettings(value);updateHint();controls();}
}
$('reset-experiment').onclick=async()=>{
  if(!ui.current?.experiment||$('reset-experiment').disabled)return;
  const id=ui.current.id;ui.sending=true;controls();notice();
  try{
    const snapshot=await api(`/api/sessions/${id}/reset`,{});ui.drafts.delete(id);
    if(ui.current?.id===id){resetViews();render(snapshot);setPrompt(snapshot.initial_prompt);connect(id);notice('实验已重置，提示词已恢复。');}
    await refreshSessions();
  }catch(error){notice(error.message);}
  finally{ui.sending=false;controls();if(ui.current?.id===id)$('prompt').focus();}
};
let checkingAgent=false;
function renderLearning(){
  const progress=ui.boot?.learning;
  $('learning').hidden=!progress;
  if(!progress)return;
  const running=ui.current?.busy&&ui.current.runner;
  const active=running||progress.runner;
  $('learning-title').textContent=active==='student'?'我的 Agent':'教学 Chat';
  $('learning-mode').textContent=active==='student'?'自动循环':'单步模式';
  const helpers=progress.checks.filter(row=>['1','2','3','4'].includes(row.id)&&row.status==='passed').length;
  $('learning-count').textContent=!progress.edit?.ready?`阶段 1/3 · Edit ${progress.edit?.passed||0}/2`:helpers<4?`阶段 2/3 · 辅助函数 ${helpers}/4`:`阶段 3/3 · Loop ${progress.ready?'已完成':'待完成'}`;
  $('learning').classList.toggle('ready',active==='student');
  const transition=running&&running!==progress.runner;
  $('learning-detail').textContent=transition?'本轮继续使用当前实现；下一轮根据最新检查结果切换。':progress.ready?'全部检查通过。下一条消息运行你保存的 agent.py，也可以让它调用工具检查自己。':progress.edit?.ready?'一起完成四个辅助函数，再写核心 Loop。编辑后自动检查，点击继续解释结果或推进下一阶段。':'先与 Chat 接入 Edit，再一起完成辅助函数和核心 Loop。每次工具返回后点击继续。';
  const allChecks=[...(progress.edit?.checks||[]),...progress.checks];
  $('learning-checks').replaceChildren(...(allChecks.length?allChecks.map(row=>el('li',row.status,`${row.status==='passed'?'✓':'○'} ${row.title}：${row.detail}`)):[el('li','',progress.detail)]));
  $('check-agent').disabled=checkingAgent;
  $('check-agent').textContent=checkingAgent?'检查中…':'检查我的代码';
}
async function refreshLearning(force=false){
  if(!ui.boot?.learning||checkingAgent)return;
  checkingAgent=true;renderLearning();
  try{ui.boot.learning=await api(force?'/api/learning/check':'/api/learning',force?{}:undefined);renderLearning();}
  catch(error){if(force)notice(error.message);}
  finally{checkingAgent=false;renderLearning();}
}
$('check-agent').onclick=()=>refreshLearning(true);
$('continue-step').onclick=async()=>{
  if(!ui.current?.awaiting_continue||$('continue-step').disabled)return;
  const id=ui.current.id, runId=ui.current.run_id;
  ui.sending=true;notice();controls();
  try{
    const snapshot=await api(`/api/sessions/${id}/continue`,{run_id:runId});
    if(ui.current?.id===id){render(snapshot);connect(id);}
    await refreshSessions();
  }catch(error){notice(error.message);}
  finally{ui.sending=false;controls();}
};
function learningWelcome(){
  if(!ui.boot.learning)return;
  document.querySelector('#welcome h1').textContent='和 Chat 一起，写出你的 Agent。';
  document.querySelector('#welcome > p').textContent='三个阶段：接入 Edit、完成辅助函数、写出核心 Loop。编辑后自动检查。';
  const prompts=[['edit','1 · 接入 Edit','声明工具，连接执行','请直接读取 lesson_01_agent/tools.py 和 README，和我一起接入 Edit。简短解释两个函数，给出这次需要手动保存的代码。'],['edit','2 · 完成辅助函数','四个函数，一起完成','Edit 已接通。请读取 agent.py，简短解释数据如何经过四个辅助函数，然后用一个编辑批次完成它们，保留核心 Loop 的 TODO。根据编辑返回的检查结果说明进度。'],['check','3 · 写出核心 Loop','请求、执行、回传、继续','请读取 agent.py，和我一起实现核心 Loop：请求模型、遍历工具、回传结果、继续循环。保留已提供的 lesson_io，网页事件和图片不需要我们编写。用 Edit 写入并依据自动检查结果解释。']];
  document.querySelector('.suggestions').replaceChildren(...prompts.map(([symbol,title,detail,prompt])=>{const button=el('button');button.type='button';button.append(icon(symbol),el('strong','',title),el('span','',detail));button.onclick=()=>{if(ui.current)newChat(true);$('prompt').value=prompt;updateHint();controls();$('prompt').focus();};return button;}));
  renderLearning();
}
setInterval(()=>{if(ui.boot?.learning&&!ui.current?.busy&&!document.hidden)refreshLearning();},3000);
const systemTheme = matchMedia('(prefers-color-scheme:dark)');
function theme(value){
  document.documentElement.dataset.theme=value==='system'?(systemTheme.matches?'dark':'light'):value;
  stored('comma-theme',value);
  $('theme-choice').value=value;
}
theme(['system','light','dark'].includes(stored('comma-theme'))?stored('comma-theme'):'system');
systemTheme.addEventListener('change',()=>{if(stored('comma-theme')==='system')theme('system');});
panels();
let savingSettings=false, loadingModels=false, addingModels=false, loadingSettings=false;
let savedConnection=null, catalog=null, selectedModels=new Set(), settingsLoad=0;
function keyState(configured){
  ui.boot.api_configured=configured;
  $('key-status').textContent=configured?'已配置':'未配置';
  $('key-status').classList.toggle('configured',configured);
  $('api-key').placeholder=configured?'已配置 · 输入新 Key 以替换':'输入接口提供的 API Key';
  $('key-help').textContent=configured?'留空保持现有 Key；将用于上方地址的请求。':'Key 保存在本机 .env；无需认证的本机接口可留空。';
}
function connectionDirty(){return !!$('api-key').value.trim()||!!savedConnection&&$('base-url').value.trim().replace(/\/+$/,'')!==savedConnection.base_url;}
function settingsControls(){
  const busy=savingSettings||loadingSettings||loadingModels||addingModels;
  $('save-settings').disabled=busy||!savedConnection||!connectionDirty();
  $('api-key').disabled=busy;$('base-url').disabled=busy;
  $('reveal-key').disabled=busy||!$('api-key').value;
  $('save-settings').textContent=savingSettings?'保存中…':'保存配置';
  $('fetch-models').disabled=busy||!savedConnection||connectionDirty();
  $('fetch-models').textContent=loadingModels?'正在拉取…':'拉取模型';
  $('add-models').disabled=busy||connectionDirty()||!selectedModels.size;
  $('add-models').textContent=addingModels?'添加中…':selectedModels.size?`添加选中 (${selectedModels.size})`:'添加选中';
}
function settingsStatus(text='',error=false){$('settings-status').textContent=text;$('settings-status').classList.toggle('error',error);}
function modelsStatus(text='',error=false){$('models-status').textContent=text;$('models-status').classList.toggle('error',error);}
function clearKeyInput(){
  $('api-key').value='';$('api-key').type='password';
  $('reveal-key').setAttribute('aria-label','显示输入的 Key');
  $('reveal-key').setAttribute('aria-pressed','false');
  settingsControls();
}
function syncModels(result){
  const current=$('model').value;
  ui.boot.models=result.models;ui.boot.default_model=result.default_model;
  const options=result.models.map(id=>{const option=el('option','',id);option.value=id;return option;});
  if(current&&!result.models.includes(current)){const option=el('option','',current+' · 历史模型');option.value=current;options.push(option);}
  $('model').replaceChildren(...options);$('model').value=current||result.default_model;
  $('added-models').replaceChildren(...result.models.map(id=>el('span','model-chip',id)));
  $('added-models-summary').textContent=`已添加 ${result.models.length} 个模型`;
}
function resetCatalog(){catalog=null;selectedModels.clear();$('model-search').value='';$('model-picker').hidden=true;modelsStatus('点击拉取模型，浏览当前接口可用的模型。');}
function loadSettings(result){
  if(!savedConnection||savedConnection.base_url!==result.base_url)resetCatalog();
  savedConnection=result;$('base-url').value=result.base_url;keyState(result.api_configured);syncModels(result);settingsControls();
}
function renderCatalog(){
  if(catalog===null)return;
  const query=$('model-search').value.trim().toLowerCase();
  const matches=catalog.filter(model=>(model.name+' '+model.id).toLowerCase().includes(query));
  const rows=matches.slice(0,100).map(model=>{
    const added=ui.boot.models.includes(model.id),row=el('label','model-result');
    const checkbox=el('input');checkbox.type='checkbox';checkbox.value=model.id;checkbox.checked=added||selectedModels.has(model.id);checkbox.disabled=added||addingModels||connectionDirty();checkbox.setAttribute('aria-label',model.id);
    checkbox.onchange=()=>{checkbox.checked?selectedModels.add(model.id):selectedModels.delete(model.id);settingsControls();};
    const text=el('span','model-result-text');text.append(el('strong','',model.name));if(model.name!==model.id)text.append(el('small','',model.id));row.append(checkbox,text);if(added)row.append(el('span','model-added','已添加'));return row;
  });
  if(!rows.length)rows.push(el('p','model-empty',catalog.length?'没有匹配的模型，试试其他关键词。':'接口尚未提供可用模型。'));
  $('model-results').replaceChildren(...rows);
  $('model-count').textContent=matches.length>100?`${matches.length} 个匹配 · 显示前 100 个，请继续搜索`:`${matches.length} 个模型`;
  settingsControls();
}
$('open-settings').onclick=async()=>{
  if(!ui.boot)return;
  const version=++settingsLoad;
  loadingSettings=true;clearKeyInput();settingsStatus();keyState(ui.boot.api_configured);
  $('settings-dialog').showModal();
  try{const result=await api('/api/settings');if(version===settingsLoad){loadSettings(result);renderCatalog();}}
  catch(error){if(version===settingsLoad)settingsStatus(error.message,true);}
  finally{if(version===settingsLoad){loadingSettings=false;settingsControls();}}
};
$('close-settings').onclick=()=>$('settings-dialog').close();
$('settings-dialog').addEventListener('close',()=>{++settingsLoad;loadingSettings=false;clearKeyInput();});
$('settings-dialog').addEventListener('click',event=>{
  const rect=$('settings-dialog').getBoundingClientRect();
  if(event.target===$('settings-dialog')&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))$('settings-dialog').close();
});
for(const id of ['api-key','base-url'])$(id).oninput=()=>{settingsStatus(connectionDirty()?'接口配置有修改，请先保存，再拉取模型。':'');settingsControls();renderCatalog();};
$('reveal-key').onclick=()=>{
  const show=$('api-key').type==='password';$('api-key').type=show?'text':'password';
  $('reveal-key').setAttribute('aria-label',show?'隐藏输入的 Key':'显示输入的 Key');
  $('reveal-key').setAttribute('aria-pressed',String(show));
};
$('theme-choice').onchange=()=>{theme($('theme-choice').value);settingsStatus('外观已保存');};
$('settings-form').onsubmit=async event=>{
  event.preventDefault();if($('save-settings').disabled)return;
  const data={base_url:$('base-url').value.trim()};if($('api-key').value.trim())data.api_key=$('api-key').value.trim();
  savingSettings=true;settingsControls();settingsStatus();
  try{
    const result=await api('/api/settings',data);
    resetCatalog();loadSettings(result);clearKeyInput();settingsStatus('配置已保存，从下一次运行开始生效');notice();
  }catch(error){settingsStatus(error.message,true);}
  finally{savingSettings=false;settingsControls();}
};
$('fetch-models').onclick=async()=>{
  if($('fetch-models').disabled)return;
  loadingModels=true;settingsControls();modelsStatus('正在连接模型接口…');
  try{
    const result=await api('/api/models',{});catalog=result.models;selectedModels.clear();$('model-picker').hidden=false;
    modelsStatus(catalog.length?`已从当前接口获取 ${catalog.length} 个模型。`:'接口返回了空列表，可以稍后重新拉取。');renderCatalog();
  }catch(error){resetCatalog();modelsStatus(error.message,true);}
  finally{loadingModels=false;settingsControls();}
};
$('model-search').oninput=renderCatalog;
$('model-search').onkeydown=event=>{if(event.key==='Enter')event.preventDefault();};
$('add-models').onclick=async()=>{
  if($('add-models').disabled)return;
  const selected=[...selectedModels];addingModels=true;settingsControls();renderCatalog();
  try{
    const result=await api('/api/settings/models',{models:selected});syncModels(result);selectedModels.clear();
    modelsStatus(`已添加 ${selected.length} 个模型，可在对话顶部的模型菜单中选择。`);renderCatalog();
  }catch(error){modelsStatus(error.message,true);}
  finally{addingModels=false;renderCatalog();}
};
$('toggle-trace').onclick=()=>{ui.traceOpen=!ui.traceOpen;panels();};$('close-trace').onclick=()=>{ui.traceOpen=false;panels();};$('open-sidebar').onclick=()=>{ui.sidebarOpen=true;panels();};$('close-sidebar').onclick=()=>{ui.sidebarOpen=false;panels();};$('scrim').onclick=()=>{ui.sidebarOpen=false;ui.traceOpen=false;panels();};$('close-image').onclick=()=>$('image-dialog').close();
$('search').oninput=renderSessions;$('composer').onsubmit=e=>{e.preventDefault();send();};$('check').onclick=()=>send(true);
$('stop').onclick=async()=>{if(!ui.current)return;ui.sending=true;controls();try{render(await api(`/api/sessions/${ui.current.id}/stop`,{}));await refreshSessions();}catch(e){notice(e.message);}finally{ui.sending=false;controls();}};
$('new-chat').onclick=()=>newChat();$('continue-new').onclick=()=>newChat(true);
$('prompt').oninput=()=>{const t=$('prompt');t.style.height='auto';t.style.height=Math.min(t.scrollHeight,160)+'px';controls();};$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();if(!$('send').disabled)send();}};
for(const id of ['model','perception'])$(id).onchange=changeSettings;
for(const b of document.querySelectorAll('[data-task]'))b.onclick=()=>chooseTask(b.dataset.task);
document.addEventListener('keydown',e=>{if($('settings-dialog').open)return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(ui.boot)newChat();}if(e.key==='Escape'&&!$('image-dialog').open){ui.sidebarOpen=false;if(innerWidth<=1024)ui.traceOpen=false;panels();}});
addEventListener('resize',panels);
setInterval(()=>{if(ui.boot&&ui.activeId&&!ui.current?.busy)refreshSessions().catch(()=>{$('connection').textContent='本机服务连接中断';});},2000);
(async()=>{try{ui.boot=await api('/api/bootstrap');learningWelcome();$('backend').textContent={1:'01 · Agent 循环',2:'02 · Computer Use'}[ui.boot.lesson];$('environment').textContent=`${ui.boot.shell.platform} · ${ui.boot.shell.name} · 本机`;for(const model of ui.boot.models){const option=el('option','',model);option.value=model;$('model').append(option);}applySettings({model:ui.boot.default_model,perception:'vision',task_id:'free'});await refreshSessions();const saved=stored('comma-session');if(saved&&ui.sessions.some(s=>s.id===saved))await openSession(saved);else newChat();if(!ui.boot.api_configured)notice('尚未配置 API Key，请点击左下角设置填写。');}catch(error){notice(`无法连接本机服务：${error.message}`);$('connection').textContent='服务未连接';}})();
