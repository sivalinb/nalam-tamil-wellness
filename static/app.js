'use strict';
const $ = id => document.getElementById(id);
const state = {data:null, auth:null, page:'today', care:'reports', recorder:null, stream:null, chunks:[], timer:null, audioUrl:null, toastTimer:null};
const names = {walk:'நடை',stretch:'அசைவு',mood:'மனசு',sleep:'தூக்கம்'};
const englishNames = {walk:'Walk',stretch:'Gentle movement',mood:'Mood',sleep:'Sleep'};
const icons = {walk:'walk',stretch:'stretch',mood:'mood',sleep:'moon'};

function el(tag, className='', text) {
  const node = document.createElement(tag);
  if(className) node.className = className;
  if(text !== undefined) node.textContent = text;
  return node;
}
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('class','icon');svg.setAttribute('aria-hidden','true');
  const use = document.createElementNS('http://www.w3.org/2000/svg','use');
  use.setAttribute('href','#i-'+name);svg.append(use);return svg;
}
function button(label, className, action, iconName) {
  const node = el('button',className);node.type='button';
  if(iconName) node.append(icon(iconName));node.append(el('span','',label));
  node.addEventListener('click',action);return node;
}
function toast(message,error=false) {
  clearTimeout(state.toastTimer);$('toast').textContent=message;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;
  state.toastTimer=setTimeout(()=>{$('toast').hidden=true;},error?11000:6500);
}
async function api(path,options={}) {
  const headers = {'X-Nalam-Request':'1',...(options.headers||{})};
  if(options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json';
  let response;
  try {response=await fetch('/api'+path,{...options,headers,credentials:'same-origin',cache:'no-store'});}
  catch (_) {throw new Error('இணையம் கிடைக்கவில்லை. கொஞ்ச நேரம் கழித்து முயற்சி செய்யலாம்.');}
  if(!response.ok) {
    let data={};try{data=await response.json();}catch(_){}
    if(response.status===401 && path!=='/auth/login' && path!=='/auth/caregiver') {
      state.auth={authenticated:false,caregiver:false};renderBase();
    }
    const detail=Array.isArray(data.detail)?data.detail.map(x=>x.msg).join(' · '):data.detail;
    throw new Error(detail||'இப்போது முடியவில்லை. மீண்டும் முயற்சி செய்யலாம்.');
  }
  if(response.headers.get('content-type')?.startsWith('audio/')) return response.blob();
  return response.json();
}
async function busy(node,action,message) {
  if(node?.disabled) return;
  if(node){node.disabled=true;node.setAttribute('aria-busy','true');}
  if(message) toast(message);
  try{return await action();}catch(error){toast(error.message,true);}
  finally{if(node){node.disabled=false;node.removeAttribute('aria-busy');}}
}
async function refresh() {
  state.auth=await api('/auth');
  if(state.auth.authenticated) state.data=await api('/state');
  else state.data=null;
  renderBase();
}
function renderBase() {
  const signed=state.auth?.authenticated;
  $('login-view').hidden=!!signed;
  $('consent-view').hidden=!signed||state.data?.consent||state.data?.review_mode||state.page==='caregiver';
  $('app-view').hidden=!signed||!state.data?.consent&&!state.data?.review_mode&&state.page!=='caregiver';
  $('caregiver-open').hidden=!signed;
  $('review-note').hidden=!signed||!state.data?.review_mode;
  $('load-sample').hidden=!state.data?.review_mode;
  if(!signed) return;
  renderToday();renderReports();renderFood();fillProfile();
  for(const page of ['today','reports','food','ask','caregiver']) $('page-'+page).hidden=state.page!==page;
  document.querySelectorAll('[data-page]').forEach(node=>{
    const active=node.dataset.page===state.page;node.classList.toggle('active',active);
    if(active)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');
  });
  $('privacy-consent').checked=state.data.consent;
  renderSources();
}
function navigate(page) {
  if(state.recorder?.state==='recording') stopRecording();
  state.page=page;renderBase();window.scrollTo({top:0,behavior:'instant'});
}
function renderToday() {
  const today=state.data.today;
  $('greeting-title').textContent='வணக்கம் '+today.name;
  const parts=today.date.split('-').map(Number);
  $('today-date').textContent=new Intl.DateTimeFormat('ta-IN',{weekday:'long',day:'numeric',month:'long'}).format(new Date(parts[0],parts[1]-1,parts[2]));
  $('progress-text').textContent=today.completed?today.completed+' பதிவு செய்தாச்சு':'';
  $('tasks').replaceChildren();
  for(const task of today.tasks) {
    const card=el('article','task-card'+(task.answer&&task.answer!=='later'?' complete':''));
    const top=el('div','task-top'),symbol=el('div','task-symbol');symbol.append(icon(icons[task.id]));top.append(symbol);
    const hear=button('','icon-button',()=>{
      if(state.data.profile.language==='bfq' && task.allowed) playPrompt(task.prompt_key);
      else speak(task.detail);
    },'volume');hear.setAttribute('aria-label',task.title+' கேட்கலாம்');top.append(hear);
    card.append(top,el('h2','',task.title),el('p','',task.detail));
    if(!task.allowed) card.append(el('span','secondary','குடும்பத்தினருடன் தொடங்கலாம்'));
    else {
      const choices=task.id==='mood'?[['good','நல்லா'],['okay','சுமார்'],['low','கவலை']]:task.id==='sleep'?[['good','நல்லா'],['okay','சுமார்'],['poor','குறைவு']]:[['done','செய்தாச்சு'],['later','பிறகு']];
      const options=el('div','task-options');
      for(const [answer,label] of choices) {
        const choice=button(label,'button outline'+(task.answer===answer?' chosen':''),()=>busy(choice,async()=>{
          const result=await api('/checkins',{method:'POST',body:JSON.stringify({kind:task.id,answer})});
          state.data.today=result.today;renderToday();toast(result.reply_tamil);
          playPrompt(answer==='later'?'later':'done');
        }));choice.setAttribute('aria-pressed',String(task.answer===answer));options.append(choice);
      }
      card.append(options);
    }
    $('tasks').append(card);
  }
  const ios=/iPhone|iPad|iPod/.test(navigator.userAgent);
  const installed=window.matchMedia('(display-mode: standalone)').matches||navigator.standalone;
  $('install-note').hidden=!!installed;
  if(!ios) $('install-note').textContent='நினைவூட்டலை குடும்பத்தினர் அமைத்துத் தரலாம்.';
}
function renderReports() {
  const list=$('reports-list');list.replaceChildren();
  if(!state.data.reports.length) {list.append(el('p','empty-state','அறிக்கை சேர்த்த பிறகு இங்கே கேட்கலாம்.'));return;}
  for(const report of state.data.reports) {
    const card=el('article','panel report-card'),heading=el('div','report-heading');
    heading.append(el('h2','',report.synthetic?'மாதிரி அறிக்கை':'இரத்தப் பரிசோதனை'),el('span','badge'+(!report.confirmed?' pending':''),report.report_date||'தேதி தெரியவில்லை'));
    card.append(heading);
    if(!report.confirmed) card.append(el('p','pending-message','குடும்பத்தினர் எண்களைச் சரிபார்க்க வேண்டும்.'));
    else {
      const hear=button('விளக்கத்தைக் கேட்கலாம்','button primary full',()=>busy(hear,async()=>{
        const result=await api('/reports/'+encodeURIComponent(report.id)+'/explain',{method:'POST'});
        $('report-answer').replaceChildren(answerCard(result.answer));$('answer-dialog').showModal();
        speak(result.answer.simple_tamil);
      },'விளக்கம் தயார் செய்கிறோம்…'),'volume');card.append(hear);
    }
    list.append(card);
  }
}
function renderFood() {
  $('food-tip').textContent=state.data.today.food_tip;$('meals').replaceChildren();
  for(const meal of state.data.today.meals) {const card=el('article','meal-card');card.append(el('h2','',meal.title),el('p','',meal.text));$('meals').append(card);}
}
function showAudio(src,label) {
  const audio=$('audio-player');audio.pause();
  if('speechSynthesis' in window)speechSynthesis.cancel();
  audio.hidden=false;
  if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl=null;}
  audio.src=src;$('audio-label').textContent=label;$('audio-dock').hidden=false;
  audio.play().catch(()=>{$('audio-label').textContent='கேட்க, கீழே உள்ள ▶ பொத்தானை அழுத்துங்க.';});
}
function playPrompt(key) {
  if(!state.auth?.authenticated)return;
  const language=state.data?.profile.language||'ta';
  if(state.data?.review_mode&&!state.data?.consent&&language==='ta'){nativeSpeak(state.data.prompts[key]);return;}
  showAudio('/api/prompts/'+encodeURIComponent(key)+'/audio?language='+language,'குரல் உதவி');
}
async function speak(text) {
  if(!text.trim())return;
  if(state.data?.review_mode&&!state.data?.consent){nativeSpeak(text);return;}
  try {
    toast('குரல் தயார் செய்கிறோம்…');
    const blob=await api('/speech',{method:'POST',body:JSON.stringify({text,language:'ta'})});
    const url=URL.createObjectURL(blob);showAudio(url,'குரல் உதவி');state.audioUrl=url;
  } catch(error){toast(error.message,true);}
}
function nativeSpeak(text) {
  if(!('speechSynthesis' in window)){toast('குரல் உதவிக்கு API இணைப்பை குடும்பத்தினர் அமைத்துத் தர வேண்டும்.',true);return;}
  const voice=speechSynthesis.getVoices().find(v=>/^ta[-_]/i.test(v.lang));
  if(!voice){toast('இந்த சாதனத்தில் தமிழ்க் குரல் இல்லை. குடும்பத்தினர் API இணைப்பை அமைத்த பிறகு கேட்கலாம்.',true);return;}
  speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text);utterance.lang='ta-IN';utterance.voice=voice;utterance.rate=1;
  $('audio-player').pause();$('audio-player').hidden=true;$('audio-dock').hidden=false;$('audio-label').textContent='சாதனத்தின் தமிழ்க் குரலில் மாதிரி விளக்கம்';
  utterance.onerror=()=>toast('இந்த சாதனத்தின் தமிழ்க் குரல் கிடைக்கவில்லை.',true);
  speechSynthesis.speak(utterance);toast('சாதனத்தின் தமிழ்க் குரலில் மாதிரி விளக்கம்.');
}
function answerCard(answer) {
  const card=el('article','panel answer-card'+(answer.urgency==='urgent'?' urgent':''));
  card.append(el('h2','',answer.urgency==='urgent'?'உடனே உதவி பெறுங்கள்':'எளிமையாகச் சொன்னால்'),el('p','answer-text',answer.simple_tamil));
  if(answer.next_step_tamil)card.append(el('p','next-step',answer.next_step_tamil));
  card.append(button('மீண்டும் கேட்கலாம்','button primary',()=>speak(answer.simple_tamil),'volume'));
  const details=el('details');details.lang='en';details.append(el('summary','','For your caregiver'),el('p','secondary',answer.english_summary));
  if(answer.clinician_questions?.length){const ul=el('ul');for(const q of answer.clinician_questions)ul.append(el('li','',q));details.append(el('h3','','Ask her clinician'),ul);}
  card.append(details);return card;
}
async function sendQuestion() {
  const message=$('question-input').value.trim();if(!message){toast('முதலில் உங்கள் கேள்வியைச் சொல்லுங்க.');return;}
  await busy($('ask-form').querySelector('[type=submit]'),async()=>{
    const result=await api('/chat',{method:'POST',body:JSON.stringify({message})});
    $('chat-answer').replaceChildren(answerCard(result.answer));$('chat-answer').hidden=false;
    $('chat-answer').scrollIntoView({behavior:'smooth',block:'nearest'});speak(result.answer.simple_tamil);
  },'உங்கள் கேள்வியைப் பார்க்கிறோம்…');
}
async function startRecording() {
  if(!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder==='undefined'){toast('குரல் பதிவுக்கு iPhone-ல் HTTPS முகவரியைத் திறக்க வேண்டும்.',true);return;}
  try {
    state.stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const types=['audio/mp4','audio/webm;codecs=opus','audio/webm'];
    const mime=types.find(type=>MediaRecorder.isTypeSupported(type));
    state.recorder=new MediaRecorder(state.stream,mime?{mimeType:mime}:{});state.chunks=[];
    state.recorder.ondataavailable=event=>{if(event.data.size)state.chunks.push(event.data);};
    state.recorder.onstop=async()=>{
      state.stream.getTracks().forEach(track=>track.stop());state.stream=null;
      clearTimeout(state.timer);$('record-button').classList.remove('recording');$('record-label').textContent='உங்கள் பேச்சைப் பார்க்கிறோம்…';
      const blob=new Blob(state.chunks,{type:state.recorder.mimeType});state.chunks=[];
      const form=new FormData();form.append('file',blob,'question.'+(blob.type.includes('mp4')?'mp4':'webm'));
      await busy($('record-button'),async()=>{
        const result=await api('/transcribe',{method:'POST',body:form});
        if(!result.text){toast('குரல் தெளிவாகக் கேட்கவில்லை. மீண்டும் சொல்லலாம்.',true);return;}
        $('question-input').value=result.text;$('question-label').textContent='இப்படித்தான் சொன்னீங்களா?';
        $('record-note').textContent='கேட்டுப் பார்த்து, சரி என்றால் கேட்கலாம்.';toast('நீங்கள் சொன்னதைக் கேட்டுப் பார்த்து உறுதி செய்யலாம்.');
      });$('record-label').textContent='மீண்டும் பேசலாம்';
    };
    state.recorder.start();$('record-button').classList.add('recording');$('record-label').textContent='கேட்கிறோம்…';$('record-note').textContent='முடிந்ததும் மீண்டும் அழுத்துங்க. 45 நொடிக்குள் சொல்லலாம்.';
    state.timer=setTimeout(stopRecording,45000);
  } catch(_){if(state.stream)state.stream.getTracks().forEach(t=>t.stop());toast('மைக்ரோஃபோன் அனுமதி கிடைக்கவில்லை. குடும்பத்தினர் உதவியுடன் முயற்சி செய்யலாம்.',true);}
}
function stopRecording(){if(state.recorder?.state==='recording')state.recorder.stop();}

async function openCaregiver() {
  if(state.auth?.caregiver){await showCaregiver();return;}
  $('caregiver-dialog').showModal();$('caregiver-pin').focus();
}
async function showCaregiver() {
  state.page='caregiver';state.care=state.data.consent?'reports':'privacy';renderBase();await switchCare(state.care);
}
async function switchCare(tab) {
  state.care=tab;
  for(const name of ['reports','routine','history','languages','privacy'])$('care-'+name).hidden=tab!==name;
  document.querySelectorAll('[data-care]').forEach(b=>b.classList.toggle('selected',b.dataset.care===tab));
  if(tab==='reports')renderCareReports();
  if(tab==='history')await renderHistory();
  if(tab==='languages')await renderBadaga();
}
function formField(label,value,type='text') {
  const wrap=el('label','',label),input=el('input');input.type=type;input.value=value??'';wrap.append(input);return {wrap,input};
}
function renderCareReports() {
  const list=$('care-report-list');list.replaceChildren();
  if(!state.data.reports.length){list.append(el('div','panel empty-state','No reports yet. Use அறிக்கை → படம் எடுக்கலாம் to photograph one.'));return;}
  for(const report of state.data.reports) {
    const card=el('article','panel stack');
    const title=el('div','report-heading');title.append(el('h2','',report.report_date||'Date not yet confirmed'),el('span','badge'+(!report.confirmed?' pending':''),report.confirmed?'Transcription confirmed':'Needs verification'));card.append(title);
    if(!report.confirmed) {
      const grid=el('div','report-review'),photo=el('div');const image=el('img','report-photo');image.src='/api/reports/'+encodeURIComponent(report.id)+'/image';image.alt='Private report photo to compare with the extracted numbers';photo.append(image);
      const enlarge=el('a','button outline full','Open photo at full size');enlarge.href=image.src;enlarge.target='_blank';enlarge.rel='noopener noreferrer';photo.append(enlarge);
      const form=el('form','stack'),date=formField('Report date (leave blank if unknown)',/^\d{4}-\d{2}-\d{2}$/.test(report.report_date)?report.report_date:'','date');form.append(date.wrap);
      if(report.uncertainties?.length)form.append(el('p','notice',report.uncertainties.join(' ')));
      const rows=[];
      for(const value of report.values) {
        const row=el('div','lab-row');const name=formField('Test name',value.name);row.append(name.wrap);
        const fields=el('div','form-grid'),number=formField('Value',value.value),unit=formField('Unit',value.unit);number.input.required=true;unit.input.required=true;fields.append(number.wrap,unit.wrap);row.append(fields);
        const range=formField('Printed reference range',value.reference_range),flag=formField('Printed flag',value.report_flag);row.append(range.wrap,flag.wrap,el('p','lab-source','Read from image: '+value.source_text));
        const retained=el('label','checkbox-label'),keep=el('input');keep.type='checkbox';keep.checked=!!value.value&&!!value.unit;retained.append(keep,el('span','','Include this readable result'));row.append(retained);form.append(row);
        rows.push({name:name.input,number:number.input,unit:unit.input,range:range.input,flag:flag.input,keep,source:value.source_text});
      }
      const verified=el('label','checkbox-label'),checkbox=el('input');checkbox.type='checkbox';checkbox.required=true;verified.append(checkbox,el('span','','I checked every included result and unit against the photo.'));form.append(verified);
      const submit=el('button','button primary','Confirm these readings');submit.type='submit';form.append(submit);
      form.addEventListener('submit',event=>{event.preventDefault();busy(submit,async()=>{
        const values=rows.filter(r=>r.keep.checked).map(r=>({name:r.name.value,value:r.number.value,unit:r.unit.value,reference_range:r.range.value,report_flag:r.flag.value,source_text:r.source}));
        if(!values.length)throw new Error('Keep at least one readable result.');
        await api('/reports/'+encodeURIComponent(report.id)+'/confirm',{method:'PUT',body:JSON.stringify({report_date:date.input.value,values})});await refresh();renderCareReports();toast('Confirmed. The photo was removed from the active record. Tamil explanation is ready to request.');
      });});grid.append(photo,form);card.append(grid);
    } else {
      const results=el('div','stack');for(const row of report.values)results.append(el('p','',row.name+': '+row.value+' '+row.unit));card.append(results);
      const explain=button('Create / view Tamil explanation','button primary',()=>busy(explain,async()=>{
        const result=await api('/reports/'+encodeURIComponent(report.id)+'/explain',{method:'POST'});$('report-answer').replaceChildren(answerCard(result.answer));$('answer-dialog').showModal();
      }));card.append(explain);
    }
    const del=button('Delete this report','button outline',()=>busy(del,async()=>{
      if(!window.confirm('Delete this report from Nalam? This cannot be undone.'))return;
      await api('/reports/'+encodeURIComponent(report.id),{method:'DELETE'});await refresh();renderCareReports();
    }));card.append(del);list.append(card);
  }
}
function fillProfile() {
  const form=$('profile-form'),profile=state.data.profile;
  for(const [key,value] of Object.entries(profile)) {
    const field=form.elements.namedItem(key);if(!field)continue;
    if(field.type==='checkbox')field.checked=value;else field.value=value;
  }
  const bfq=$('language-select').querySelector('[value=bfq]');bfq.disabled=!state.data.languages.bfq.ready;
  $('reminder-fields').replaceChildren();
  for(const id of ['walk','stretch','mood','sleep']) {
    const reminder=profile.reminders.find(r=>r.id===id)||{time:'09:00',enabled:false};
    const field=el('div','stack'),enabled=el('label','checkbox-label'),checkbox=el('input');checkbox.type='checkbox';checkbox.name='reminder-'+id+'-enabled';checkbox.checked=reminder.enabled;enabled.append(checkbox,el('span','',englishNames[id]));
    const time=formField('Time',reminder.time,'time');time.input.name='reminder-'+id+'-time';field.append(enabled,time.wrap);$('reminder-fields').append(field);
  }
}
async function saveProfile() {
  const form=$('profile-form'),p={...state.data.profile};
  for(const key of ['name','timezone','diet','mobility','allergies','conditions','clinician_instructions','quiet_start','quiet_end','language'])p[key]=form.elements.namedItem(key).value;
  for(const key of ['age','walk_minutes'])p[key]=Number(form.elements.namedItem(key).value);
  p.light_activity_ok=form.elements.namedItem('light_activity_ok').checked;
  p.reminders=['walk','stretch','mood','sleep'].map(id=>({id,time:form.elements.namedItem('reminder-'+id+'-time').value,enabled:form.elements.namedItem('reminder-'+id+'-enabled').checked}));
  await api('/profile',{method:'PUT',body:JSON.stringify(p)});await refresh();toast('Her routine has been saved.');
}
async function renderHistory() {
  try {
    const data=await api('/checkins'),list=$('history-list');list.replaceChildren();
    if(!data.checkins.length){list.append(el('p','empty-state','Check-ins will appear as she uses the daily prompts.'));return;}
    if(data.low_mood_days>=3)list.append(el('div','notice','She has marked low mood on several recent days. A gentle conversation and appropriate clinician support may help. Check-ins do not diagnose a condition.'));
    for(const row of data.checkins){const item=el('div','panel history-row');item.append(el('strong','',englishNames[row.kind]+' · '+row.answer),el('span','',row.local_date));list.append(item);}
  }catch(error){toast(error.message,true);}
}
async function renderBadaga() {
  try {
    const data=await api('/languages');state.data.languages=data.languages;
    const bfq=data.languages.bfq;$('badaga-progress').textContent=bfq.recorded_keys.length+' of '+bfq.required_keys.length+' reviewed recordings';
    const select=$('badaga-key');select.replaceChildren();
    for(const [key,text] of Object.entries(data.prompts)){const option=el('option','',key+(bfq.recorded_keys.includes(key)?' · recorded':''));option.value=key;option.dataset.source=text;select.append(option);}
    $('badaga-source').textContent=select.selectedOptions[0]?.dataset.source||'';
  }catch(error){toast(error.message,true);}
}
function renderSources() {
  $('source-links').replaceChildren(el('h3','','Educational sources'));
  for(const source of state.data.sources){const link=el('a','',source.title);link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';$('source-links').append(link);}
  const privacy=el('a','','OpenAI API data controls');privacy.href='https://developers.openai.com/api/docs/guides/your-data';privacy.target='_blank';privacy.rel='noopener noreferrer';$('source-links').append(privacy);
}
function base64Bytes(value) {const str=atob((value+'='.repeat((4-value.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(str,c=>c.charCodeAt(0));}
async function enableReminders() {
  const ios=/iPhone|iPad|iPod/.test(navigator.userAgent),installed=navigator.standalone||window.matchMedia('(display-mode: standalone)').matches;
  if(ios&&!installed){toast('Safari-ல் Share → Add to Home Screen செய்து, நலம் செயலியைத் திறக்கவும்.');return;}
  if(!window.isSecureContext||!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)) {toast('நினைவூட்டலுக்கு HTTPS முகவரியில் செயலியைத் திறக்க வேண்டும்.',true);return;}
  // Request permission directly within the tap, before asynchronous server requests.
  const permission=await Notification.requestPermission();
  if(permission!=='granted'){toast('நினைவூட்டல் அனுமதி கிடைக்கவில்லை. தினமும் செயலியைத் திறந்து கேட்கலாம்.');return;}
  const registration=await navigator.serviceWorker.ready,config=await api('/push/config');
  let subscription=await registration.pushManager.getSubscription();
  if(!subscription)subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64Bytes(config.public_key)});
  await api('/push/subscribe',{method:'POST',body:JSON.stringify(subscription.toJSON())});
  $('enable-reminders').textContent='நினைவூட்டல் தயார்';toast('நினைவூட்டல் தயார். வந்ததும் அழுத்தி, குரலைக் கேட்கலாம்.');
}

document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.page)));
document.querySelectorAll('[data-care]').forEach(b=>b.addEventListener('click',()=>switchCare(b.dataset.care)));
$('login-form').addEventListener('submit',event=>{event.preventDefault();busy(event.submitter,async()=>{await api('/auth/login',{method:'POST',body:JSON.stringify({code:$('family-code').value})});$('family-code').value='';await refresh();});});
$('caregiver-open').addEventListener('click',openCaregiver);$('consent-setup').addEventListener('click',openCaregiver);
$('dialog-close').addEventListener('click',()=>$('caregiver-dialog').close());
$('caregiver-login').addEventListener('submit',event=>{event.preventDefault();busy(event.submitter,async()=>{await api('/auth/caregiver',{method:'POST',body:JSON.stringify({code:$('caregiver-pin').value})});$('caregiver-pin').value='';$('caregiver-dialog').close();state.auth.caregiver=true;await showCaregiver();});});
$('return-mom').addEventListener('click',()=>busy($('return-mom'),async()=>{await api('/auth/lock',{method:'POST'});state.auth.caregiver=false;navigate('today');}));
$('hear-today').addEventListener('click',()=>state.data.profile.language==='bfq'?playPrompt('hello'):speak(state.data.today.voice_tamil));
$('hear-food').addEventListener('click',()=>{const text=[state.data.today.food_tip,...state.data.today.meals.map(m=>m.text)].join(' ');if(state.data.profile.language==='bfq'&&!state.data.profile.allergies&&!state.data.profile.conditions)playPrompt('food');else speak(text);});
$('food-question').addEventListener('click',()=>{navigate('ask');$('question-input').value='எனக்கு ஏற்ற சாப்பாடு என்ன?';});
$('record-button').addEventListener('click',()=>state.recorder?.state==='recording'?stopRecording():startRecording());
$('hear-question').addEventListener('click',()=>speak($('question-input').value));
$('ask-form').addEventListener('submit',event=>{event.preventDefault();sendQuestion();});
document.querySelectorAll('[data-question]').forEach(b=>b.addEventListener('click',()=>{$('question-input').value=b.dataset.question;sendQuestion();}));
$('report-upload').addEventListener('click',()=>$('report-file').click());
$('report-file').addEventListener('change',()=>{
  const file=$('report-file').files[0];if(!file)return;
  busy($('report-upload'),async()=>{
    if(file.size>12*1024*1024)throw new Error('படம் பெரியதாக இருக்கு. அறிக்கை மட்டும் தெரியும்படி வெட்டி முயற்சி செய்யலாம்.');
    const data=new FormData();data.append('file',file);await api('/reports',{method:'POST',body:data});
    await refresh();toast('அறிக்கை சேர்த்தாச்சு. குடும்பத்தினர் எண்களைச் சரிபார்க்க வேண்டும்.');playPrompt('report_pending');
  },'அறிக்கையைப் படிக்கிறோம்…').finally(()=>{$('report-file').value='';});
});
$('profile-form').addEventListener('submit',event=>{event.preventDefault();busy(event.submitter,saveProfile);});
$('save-consent').addEventListener('click',()=>busy($('save-consent'),async()=>{
  await api('/consent',{method:'POST',body:JSON.stringify({accepted:$('privacy-consent').checked})});await refresh();toast('Your privacy choice has been saved.');
}));
$('badaga-key').addEventListener('change',()=>{$('badaga-source').textContent=$('badaga-key').selectedOptions[0]?.dataset.source||'';});
$('badaga-form').addEventListener('submit',event=>{event.preventDefault();busy(event.submitter,async()=>{
  const form=new FormData();form.append('file',$('badaga-file').files[0]);
  await api('/languages/bfq/'+encodeURIComponent($('badaga-key').value)+'?reviewed=true',{method:'PUT',body:form});$('badaga-file').value='';$('badaga-reviewed').checked=false;await renderBadaga();toast('Reviewed recording saved.');
});});
$('enable-reminders').addEventListener('click',()=>busy($('enable-reminders'),enableReminders));
$('test-reminder').addEventListener('click',()=>busy($('test-reminder'),async()=>{const result=await api('/push/test',{method:'POST'});toast('Accepted by push service: '+result.delivered+' of '+result.attempted+'. Verify it on the subscribed device.');}));
$('load-sample').addEventListener('click',()=>busy($('load-sample'),async()=>{await api('/demo',{method:'POST'});await refresh();renderCareReports();toast('Fictional sample loaded. No AI report analysis was used.');}));
$('delete-data').addEventListener('click',()=>busy($('delete-data'),async()=>{
  if($('delete-confirm').value!=='DELETE')throw new Error('Type DELETE to confirm removal.');
  const registration=await navigator.serviceWorker?.getRegistration();const subscription=await registration?.pushManager?.getSubscription();if(subscription)await subscription.unsubscribe();
  await api('/data',{method:'DELETE'});state.page='today';await refresh();$('delete-confirm').value='';toast('Saved information has been removed.');
}));
$('logout').addEventListener('click',async()=>{const registration=await navigator.serviceWorker?.getRegistration();const subscription=await registration?.pushManager?.getSubscription();if(subscription){await api('/push/unsubscribe',{method:'POST',body:JSON.stringify(subscription.toJSON())});await subscription.unsubscribe();}await api('/auth/logout',{method:'POST'});$('audio-player').pause();$('audio-dock').hidden=true;state.page='today';await refresh();});
$('answer-close').addEventListener('click',()=>$('answer-dialog').close());
$('audio-close').addEventListener('click',()=>{$('audio-player').pause();if('speechSynthesis' in window)speechSynthesis.cancel();$('audio-dock').hidden=true;});
$('audio-player').addEventListener('error',()=>{toast('குரல் கிடைக்கவில்லை. மீண்டும் முயற்சி செய்யலாம்.',true);$('audio-label').textContent='குரல் கிடைக்கவில்லை';});
window.addEventListener('offline',()=>{$('offline-note').hidden=false;});window.addEventListener('online',()=>{$('offline-note').hidden=true;});
window.addEventListener('pagehide',()=>{stopRecording();if(state.stream)state.stream.getTracks().forEach(t=>t.stop());});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
if('speechSynthesis' in window)speechSynthesis.getVoices();
$('offline-note').hidden=navigator.onLine;
refresh().then(()=>{const reminder=new URLSearchParams(location.search).get('reminder');if(reminder&&names[reminder])toast('நினைவூட்டல் வந்திருக்கு. '+names[reminder]+' பகுதியைத் திறந்து கேட்கலாம்.');}).catch(error=>{toast(error.message,true);$('login-view').hidden=false;});
