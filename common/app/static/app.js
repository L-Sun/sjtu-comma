'use strict';
const $ = id => document.getElementById(id);
const ui = {boot:null, current:null, sessions:[], source:null, activeId:null, traceOpen:innerWidth>1024, sidebarOpen:false, sending:false, messageKey:'', attachmentKey:'', stepRows:[]};
function el(tag, cls, text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function icon(name){const n=el('img');n.src=`/static/icons/${name}.svg`;n.alt='';return n;}
function notice(text=''){$('notice').textContent=text;$('notice').hidden=!text;}
function nearBottom(n){return n.scrollHeight-n.scrollTop-n.clientHeight<70;}
function stored(key,value){try{if(value===undefined)return localStorage.getItem(key);if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}catch{}return null;}
async function api(path, data){const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-Comma-Token':ui.boot.csrf_token},body:data===undefined?undefined:JSON.stringify(data)});const value=await response.json();if(!response.ok)throw new Error(value.error||`请求失败 (${response.status})`);return value;}
function settings(){return {model:$('model').value,perception:$('perception').value,task_id:$('task').value};}
function applySettings(value){if(!Array.from($('model').options).some(o=>o.value===value.model)){const option=el('option','',value.model.split('/').pop()+' · 历史模型');option.value=value.model;$('model').append(option);}$('model').value=value.model;$('perception').value=value.perception||'vision';$('task').value=value.task_id||'free';updateHint();}
function updateHint(){const task=ui.boot.tasks.find(t=>t.id===$('task').value);$('perception-label').hidden=ui.boot.lesson<3;$('task-hint').textContent=task?.id==='free'?'自由探索 · Enter 发送，Shift + Enter 换行':task?.title||'';$('task-hint').title=task?.note||'';}
function panels(){document.querySelector('.workspace').classList.toggle('trace-hidden',!ui.traceOpen);$('toggle-trace').classList.toggle('active',ui.traceOpen);$('toggle-trace').setAttribute('aria-expanded',String(ui.traceOpen));$('sidebar').classList.toggle('open',ui.sidebarOpen);$('scrim').hidden=!(ui.sidebarOpen||(ui.traceOpen&&innerWidth<=1024));}
function disconnect(){ui.source?.close();ui.source=null;}
function connect(id){disconnect();const source=new EventSource(`/api/sessions/${id}/events`);ui.source=source;source.addEventListener('snapshot',event=>{if(ui.current?.id!==id)return;const before=ui.current.busy;render(JSON.parse(event.data));$('connection').textContent='本机服务已连接';if(before!==ui.current.busy)refreshSessions();});source.onerror=()=>{$('connection').textContent='连接中断，正在重连…';};source.onopen=()=>{$('connection').textContent='本机服务已连接';};}
async function refreshSessions(){const result=await api('/api/sessions');ui.sessions=result.sessions;ui.activeId=result.active_id;renderSessions();controls();}
function renderSessions(){const search=$('search').value.toLowerCase();const matches=ui.sessions.filter(s=>s.title.toLowerCase().includes(search));const nodes=matches.map(s=>{const button=el('button','session'+(ui.current?.id===s.id?' active':'')+(s.busy?' running':''));button.type='button';button.title=s.title;button.setAttribute('aria-label',s.title);if(ui.current?.id===s.id)button.setAttribute('aria-current','true');button.append(icon('chat'));const body=el('span','session-content');body.append(el('span','session-title',s.title));const model=(s.settings.model||'').split('/').pop();body.append(el('small','',`${model} · ${s.busy?'执行中':s.readonly?'已保存':({error:'出错',cancelled:'已停止',timeout:'超时',ready:'未开始'}[s.status]||'会话')}`));button.append(body);button.onclick=()=>openSession(s.id);return button;});if(!nodes.length)nodes.push(el('div','section-label',search?'没有匹配的会话':'你的对话会保存在这里'));$('sessions').replaceChildren(...nodes);$('session-count').textContent=ui.sessions.length||'';}
async function openSession(id){try{notice();const snapshot=await api(`/api/sessions/${id}`);disconnect();ui.current=null;resetViews();applySettings(snapshot.settings);render(snapshot);stored('comma-session',id);ui.sidebarOpen=false;panels();renderSessions();if(!snapshot.readonly)connect(id);else $('connection').textContent='已保存的运行记录';}catch(error){notice(error.message);}}
function resetViews(){ui.messageKey='';ui.attachmentKey='';ui.stepRows=[];$('messages').replaceChildren();$('steps').replaceChildren();$('attachments').replaceChildren();}
function newChat(preserve=false){disconnect();ui.current=null;stored('comma-session',null);resetViews();notice();if(!preserve)applySettings({model:ui.boot.default_model,perception:'vision',task_id:'free'});if(!ui.boot.models.includes($('model').value))$('model').value=ui.boot.default_model;$('prompt').value='';$('prompt').style.height='';$('chat-title').textContent='新对话';$('welcome').hidden=false;$('trace-current').textContent='等待开始';$('trace-stats').textContent='工具调用与结果将在这里实时显示';$('trace-empty').hidden=false;$('connection').textContent='本机服务已连接';$('export').removeAttribute('href');$('export').classList.add('disabled');ui.sidebarOpen=false;panels();renderSessions();controls();$('prompt').focus();}
function controls(){const busy=!!ui.current?.busy, readonly=!!ui.current?.readonly, elsewhere=ui.activeId&&ui.activeId!==ui.current?.id;$('send').hidden=busy;$('stop').hidden=!busy;$('stop').disabled=ui.sending;$('send').disabled=readonly||ui.sending||elsewhere||!$('prompt').value.trim();$('check').disabled=busy||readonly||ui.sending||!!elsewhere;$('prompt').disabled=readonly||ui.sending;$('prompt').placeholder=elsewhere?'另一会话正在执行，请先等待完成…':'给模型一个任务…';$('readonly').hidden=!readonly;$('composer').hidden=readonly;for(const id of ['model','perception','task'])$(id).disabled=busy||ui.sending;$('status-dot').classList.toggle('busy',busy);}
function messageContent(node,text){const blocks=String(text).split(/```[^\n]*\n([\s\S]*?)```/g);blocks.forEach((part,index)=>{if(index%2){const pre=el('pre');pre.append(el('code','',part));node.append(pre);}else node.append(document.createTextNode(part));});}
function renderMessages(snapshot){const key=JSON.stringify([snapshot.messages,snapshot.busy]);if(key===ui.messageKey)return;ui.messageKey=key;const scroll=$('chat-scroll'),bottom=nearBottom(scroll);const fragment=document.createDocumentFragment();for(const message of snapshot.messages){const article=el('article',`message ${message.role}`);const label=el('div','message-label');if(message.role==='assistant')label.append(icon('agent'));label.append(document.createTextNode(message.role==='user'?'你':snapshot.settings.model.split('/').pop()));const body=el('div','message-content');messageContent(body,message.text);article.append(label,body);fragment.append(article);}if(snapshot.busy)fragment.append(el('div','pending-reply','正在执行，工具步骤会实时出现在右侧'));$('messages').replaceChildren(fragment);if(bottom)scroll.scrollTop=scroll.scrollHeight;}
function renderSteps(trace){const scroll=$('trace-scroll'),bottom=nearBottom(scroll);trace.steps.forEach((step,i)=>{let row=ui.stepRows[i];if(!row){row=el('li','step');const symbol=el('span','step-icon'),body=el('div','step-body');body.append(el('div','step-title'),el('div','step-detail'),el('div','step-meta'));row.append(symbol,body);$('steps').append(row);ui.stepRows.push(row);}const key=JSON.stringify(step);if(row.dataset.state===key)return;row.dataset.state=key;row.className=`step ${step.status}`;const symbol=step.status==='error'?'close':step.status==='done'?'check':({search_file:'search',read_file:'read',edit:'edit',bash:'command',get_window_state:'eye',click:'monitor'}[step.tool]||'think');row.firstChild.replaceChildren(icon(symbol));row.querySelector('.step-title').textContent=step.title;row.querySelector('.step-detail').textContent=step.detail;row.querySelector('.step-meta').textContent=[step.number?`#${step.number}`:'',step.repeat_of?`同 #${step.repeat_of} 参数 · 第 ${step.repeat_count} 次`:'',step.duration!=null?`${step.duration.toFixed(1)}s`:''].filter(Boolean).join(' · ');});$('trace-empty').hidden=trace.steps.length>0;if(bottom)scroll.scrollTop=scroll.scrollHeight;}
function renderAttachments(snapshot){const key=JSON.stringify([snapshot.images,snapshot.code_file,snapshot.run_id]);if(key===ui.attachmentKey)return;ui.attachmentKey=key;const nodes=snapshot.images.map((image,i)=>{const b=el('button');b.type='button';b.setAttribute('aria-label',`查看截图 ${i+1}`);const img=el('img');img.src=image.url;img.alt=`观察截图 ${i+1}`;img.loading='lazy';b.append(img);b.onclick=()=>{$('full-image').src=image.url;$('image-dialog').showModal();};return b;});if(snapshot.code_file){const a=el('a','', '查看本轮代码文件 ↗');a.href=`/api/runs/${snapshot.run_id}/files/${snapshot.code_file}`;a.target='_blank';a.rel='noopener';nodes.push(a);}$('attachments').replaceChildren(...nodes);}
function render(snapshot){ui.current=snapshot;ui.activeId=snapshot.active_id;$('chat-title').textContent=snapshot.title;$('welcome').hidden=snapshot.messages.length>0;renderMessages(snapshot);renderSteps(snapshot.trace);renderAttachments(snapshot);$('trace-current').textContent=snapshot.trace.current;$('trace-stats').textContent=`${snapshot.trace.calls} 次调用 · ${snapshot.trace.errors} 次错误 · ${snapshot.trace.tokens.toLocaleString()} tokens`;if(snapshot.run_id){$('export').href=`/api/runs/${snapshot.run_id}/export`;$('export').classList.remove('disabled');}controls();}
async function send(llmOnly=false){const text=llmOnly?'请只回复：LLM 接口已连接。':$('prompt').value.trim();if(!text||ui.sending||ui.current?.busy)return;ui.sending=true;notice();controls();try{if(!ui.current){ui.current=await api('/api/sessions',settings());stored('comma-session',ui.current.id);}const snapshot=await api(`/api/sessions/${ui.current.id}/messages`,{text,llm_only:llmOnly});render(snapshot);if(!llmOnly){$('prompt').value='';$('prompt').style.height='';}connect(snapshot.id);await refreshSessions();$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;}catch(error){notice(error.message);}finally{ui.sending=false;controls();}}
function chooseTask(id){if(id==='shell'){newChat(true);$('task').value='free';$('prompt').value='请使用 bash 工具输出 COMMA_SHELL_OK，并告诉我当前工作目录。';}else{const task=ui.boot.tasks.find(t=>t.id===id);if(ui.current)newChat(true);$('task').value=id;$('prompt').value=task.prompt;}updateHint();controls();$('prompt').focus();}
function changeSettings(event){const value=settings();if(!ui.boot.models.includes(value.model))value.model=ui.boot.default_model;if(ui.current)newChat(true);applySettings(value);if(event.target.id==='task'){chooseTask(value.task_id);}updateHint();controls();}
const systemTheme = matchMedia('(prefers-color-scheme:dark)');
function theme(value){
  document.documentElement.dataset.theme=value==='system'?(systemTheme.matches?'dark':'light'):value;
  stored('comma-theme',value);
  $('theme-choice').value=value;
}
theme(['system','light','dark'].includes(stored('comma-theme'))?stored('comma-theme'):'system');
systemTheme.addEventListener('change',()=>{if(stored('comma-theme')==='system')theme('system');});
panels();
let savingSettings=false;
function keyState(configured){
  ui.boot.api_configured=configured;
  $('key-status').textContent=configured?'已配置':'未配置';
  $('key-status').classList.toggle('configured',configured);
  $('api-key').placeholder=configured?'已配置 · 输入新 Key 以替换':'sk-or-v1-…';
  $('key-help').textContent=configured?'留空保持现有 Key；新 Key 保存在本机 .env。':'保存在本机 .env，保存后新任务立即生效。';
}
function settingsControls(){
  $('save-settings').disabled=savingSettings||!$('api-key').value.trim();
  $('api-key').disabled=savingSettings;
  $('reveal-key').disabled=savingSettings||!$('api-key').value;
  $('save-settings').textContent=savingSettings?'保存中…':'保存 Key';
}
function settingsStatus(text='',error=false){$('settings-status').textContent=text;$('settings-status').classList.toggle('error',error);}
function clearKeyInput(){
  $('api-key').value='';$('api-key').type='password';
  $('reveal-key').setAttribute('aria-label','显示输入的 Key');
  $('reveal-key').setAttribute('aria-pressed','false');
  settingsControls();
}
$('open-settings').onclick=async()=>{
  if(!ui.boot)return;
  clearKeyInput();settingsStatus();keyState(ui.boot.api_configured);
  $('settings-dialog').showModal();
  try{keyState((await api('/api/settings')).api_configured);}
  catch(error){settingsStatus(error.message,true);}
};
$('close-settings').onclick=()=>$('settings-dialog').close();
$('settings-dialog').addEventListener('close',clearKeyInput);
$('settings-dialog').addEventListener('click',event=>{
  const rect=$('settings-dialog').getBoundingClientRect();
  if(event.target===$('settings-dialog')&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))$('settings-dialog').close();
});
$('api-key').oninput=()=>{settingsStatus();settingsControls();};
$('reveal-key').onclick=()=>{
  const show=$('api-key').type==='password';$('api-key').type=show?'text':'password';
  $('reveal-key').setAttribute('aria-label',show?'隐藏输入的 Key':'显示输入的 Key');
  $('reveal-key').setAttribute('aria-pressed',String(show));
};
$('theme-choice').onchange=()=>{theme($('theme-choice').value);settingsStatus('外观已保存');};
$('settings-form').onsubmit=async event=>{
  event.preventDefault();if(savingSettings||!$('api-key').value.trim())return;
  savingSettings=true;settingsControls();settingsStatus();
  try{
    const result=await api('/api/settings',{api_key:$('api-key').value.trim()});
    keyState(result.api_configured);clearKeyInput();settingsStatus('Key 已保存，新任务立即生效');notice();
  }catch(error){settingsStatus(error.message,true);}
  finally{savingSettings=false;settingsControls();}
};
$('toggle-trace').onclick=()=>{ui.traceOpen=!ui.traceOpen;panels();};$('close-trace').onclick=()=>{ui.traceOpen=false;panels();};$('open-sidebar').onclick=()=>{ui.sidebarOpen=true;panels();};$('close-sidebar').onclick=()=>{ui.sidebarOpen=false;panels();};$('scrim').onclick=()=>{ui.sidebarOpen=false;ui.traceOpen=false;panels();};$('close-image').onclick=()=>$('image-dialog').close();
$('search').oninput=renderSessions;$('composer').onsubmit=e=>{e.preventDefault();send();};$('check').onclick=()=>send(true);
$('stop').onclick=async()=>{if(!ui.current)return;ui.sending=true;controls();try{render(await api(`/api/sessions/${ui.current.id}/stop`,{}));await refreshSessions();}catch(e){notice(e.message);}finally{ui.sending=false;controls();}};
$('new-chat').onclick=()=>newChat();$('continue-new').onclick=()=>newChat(true);
$('prompt').oninput=()=>{const t=$('prompt');t.style.height='auto';t.style.height=Math.min(t.scrollHeight,160)+'px';controls();};$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();if(!$('send').disabled)send();}};
for(const id of ['model','task','perception'])$(id).onchange=changeSettings;
for(const b of document.querySelectorAll('[data-task]'))b.onclick=()=>chooseTask(b.dataset.task);
document.addEventListener('keydown',e=>{if($('settings-dialog').open)return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(ui.boot)newChat();}if(e.key==='Escape'&&!$('image-dialog').open){ui.sidebarOpen=false;if(innerWidth<=1024)ui.traceOpen=false;panels();}});
addEventListener('resize',panels);
setInterval(()=>{if(ui.boot&&ui.activeId&&!ui.current?.busy)refreshSessions().catch(()=>{$('connection').textContent='本机服务连接中断';});},2000);
(async()=>{try{ui.boot=await api('/api/bootstrap');$('backend').textContent=(ui.boot.demo?'演示 · ':'')+{1:'01 · LLM 接口',2:'02 · Agent 循环',3:'03 · Computer Use'}[ui.boot.lesson];$('environment').textContent=`${ui.boot.shell.platform} · ${ui.boot.shell.name} · 本机`;for(const card of document.querySelectorAll('[data-task]')){if(ui.boot.lesson===1&&card.dataset.task!=='format')card.hidden=true;}for(const model of ui.boot.models){const option=el('option','',model.split('/').pop());option.value=model;$('model').append(option);}for(const task of ui.boot.tasks){const option=el('option','',task.title);option.value=task.id;$('task').append(option);}applySettings({model:ui.boot.default_model,perception:'vision',task_id:'free'});await refreshSessions();const saved=stored('comma-session');if(saved&&ui.sessions.some(s=>s.id===saved))await openSession(saved);else newChat();if(!ui.boot.api_configured&&!ui.boot.demo)notice('尚未配置 API Key，请点击左下角设置填写。');}catch(error){notice(`无法连接本机服务：${error.message}`);$('connection').textContent='服务未连接';}})();
