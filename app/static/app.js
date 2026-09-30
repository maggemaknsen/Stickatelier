'use strict';
const $=id=>document.getElementById(id);
const keys=['colors','long_side_mm','smooth','contrast','detail_mm','darken_mm','remove_bg','background','tolerance'];
const defaults={colors:6,long_side_mm:100,smooth:0,contrast:100,detail_mm:0,darken_mm:0,remove_bg:false,background:'#ffffff',tolerance:20};
let current=null, mode='logo', view='compare', requestNo=0, debounce, suggestion=null, exporting=false, aiRunning=false,uploading=false, renderedSettings=null, previewController=null;
let paletteEdit=null, paletteBase=[], paletteColors=[], paletteHistory=[], mergeMode=false, mergeTarget=null, editingColor=null;
let analysisApproved=false, analysisPreviewRunning=false, analysisSequence=0, handoffWorking=false, handoffContext=null;
let pickingBackground=false, locatedColor=null, locatePreviousView=null;
function values(){const s={};for(const key of keys)s[key]=key==='remove_bg'?$(key).checked:key==='background'?$(key).value:Number($(key).value);s.palette_edit=paletteEdit;return s;}
function valid(){const w=Number($('long_side_mm').value);return Number.isFinite(w)&&w>=10&&w<=260;}
function sizeFeedback(){
 const accepted=valid(),field=$('long_side_mm');field.setAttribute('aria-invalid',String(!accepted));field.setCustomValidity(accepted?'':'Bitte eine lange Seite von 10 bis 260 mm eingeben.');$('sizeError').hidden=accepted;
 if(!accepted||!current){$('dimensions').textContent='–';return;}
 const scale=Number(field.value)/Math.max(current.width,current.height),width=Math.round(current.width*scale*10)/10,height=Math.round(current.height*scale*10)/10;
 $('dimensions').textContent=`${width.toLocaleString('de-DE')} × ${height.toLocaleString('de-DE')} mm`;
}
function setValues(s){for(const key of keys)if(key in s){if(key==='remove_bg')$(key).checked=s[key];else $(key).value=s[key];}labels();}
function labels(){
 sizeFeedback();
 $('colorsOut').value=$('colors').value;
 $('smoothOut').value=['Aus','Leicht','Mittel','Stark'][Number($('smooth').value)];
 $('contrastOut').value=$('contrast').value+' %';
 for(const k of ['detail_mm','darken_mm'])$(k+'Out').value=Number($(k).value)===0?'Aus':Number($(k).value).toLocaleString('de-DE',{maximumFractionDigits:2})+' mm';
 $('toleranceOut').value=$('tolerance').value;$('bgOptions').hidden=!$('remove_bg').checked;
 buttons();
}
function buttons(){
 $('previewButton').disabled=!current||!valid()||uploading;
 $('exportButton').disabled=!current||!valid()||exporting||uploading||JSON.stringify(renderedSettings)!==JSON.stringify(values());
 $('aiButton').disabled=!current||!valid()||!$('model').value||$('model').disabled||aiRunning||uploading;
 const paletteReady=!!current&&valid()&&!uploading&&JSON.stringify(renderedSettings)===JSON.stringify(values());
 for(const b of $('palette').querySelectorAll('button'))b.disabled=!paletteReady;
 for(const b of $('palette').querySelectorAll('.swatch'))b.disabled=!paletteReady&&!(pickingBackground&&current&&!uploading);
 for(const b of $('palette').querySelectorAll('.locateColor'))b.disabled=!paletteReady||!$('processed').complete;
 $('pickBackground').disabled=!current||uploading||$('canvas').hidden||!$('original').complete||!$('processed').complete||!$('remove_bg').checked;
 $('mergeColors').disabled=!paletteReady||paletteColors.length<2;
 $('undoPalette').disabled=!paletteReady||!paletteHistory.length;
 $('resetPalette').disabled=!paletteReady||!paletteEdit;
 $('applyPaletteColor').disabled=!paletteReady;
 $('previewAI').disabled=!suggestion||analysisPreviewRunning||uploading;
 $('applyAI').disabled=!suggestion||!analysisApproved||analysisPreviewRunning||uploading;
 $('prepareEdit').disabled=!current||!valid()||uploading||handoffWorking||!$('editGoal').value.trim();
 $('prepareGenerate').disabled=!valid()||uploading||handoffWorking||!$('generateGoal').value.trim();
 $('importAI').disabled=!handoffContext||uploading||handoffWorking;
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,6500);}
async function authFetch(...args){const response=await fetch(...args);if(response.status===401){window.location.replace('/');throw new Error('Bitte erneut anmelden.');}return response;}
$('logoutButton').onclick=async()=>{try{await api('/auth/logout');window.location.replace('/');}catch(error){toast(error.message);}};
async function api(path,body={},signal){
 const response=await authFetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Atelier':'1'},body:JSON.stringify(body),signal});
 if(!response.ok){const error=await response.json();throw new Error(error.error||'Anfrage fehlgeschlagen.');}return response;
}
function invalidate(keepPalette=false){stopPicking();clearLocalization();if(keepPalette!==true)clearPaletteEdits(true);previewController?.abort();renderedSettings=null;clearAnalysis();requestNo++;$('busy').hidden=true;clearTimeout(debounce);labels();if(current&&$('auto').checked)debounce=setTimeout(preview,400);}
function clearAnalysis(){suggestion=null;analysisApproved=false;analysisSequence++;$('aiResult').hidden=true;$('analysisPreview').hidden=true;}
function copyEdit(edit){return edit?{base:[...edit.base],map:{...edit.map}}:null;}
function clearPaletteEdits(notify=false){
 const changed=!!paletteEdit;paletteEdit=null;paletteHistory=[];mergeMode=false;mergeTarget=null;editingColor=null;$('paletteDialog').close();paletteHint();
 if(changed&&notify)toast('Farbänderungen zurückgesetzt: Die Bildregler berechnen die Palette neu.');
}
function paletteHint(){
 $('mergeColors').textContent=mergeMode?'Zusammenfassen abbrechen':'Farben zusammenfassen';$('mergeColors').setAttribute('aria-pressed',String(mergeMode));
 $('paletteHint').textContent=pickingBackground?'Pipette aktiv: Eine Palettenfarbe als Hintergrundfarbe auswählen.':mergeMode?(mergeTarget?`Zielfarbe ${mergeTarget.toUpperCase()} gewählt. Jetzt die Farbe anklicken, die sie übernehmen soll.`:'Zuerst die Zielfarbe anklicken, dann die Farbe, die sie übernehmen soll.'):'Farbe anklicken, um sie zu ändern. Mit „Lokalisieren“ ihre Flächen im Bild markieren. Bildregler setzen manuelle Farbänderungen zurück.';
 for(const b of $('palette').querySelectorAll('.swatch')){const selected=mergeMode&&b.dataset.color===mergeTarget;b.classList.toggle('mergeTarget',selected);b.setAttribute('aria-pressed',String(selected));}
}
function renderPalette(){
 $('palette').replaceChildren();for(const c of paletteColors){
  const node=document.createElement('button');node.type='button';node.className='swatch';node.dataset.color=c.hex;node.title='Farbe '+c.hex.toUpperCase()+' ändern';node.setAttribute('aria-label','Farbe '+c.hex.toUpperCase()+', '+c.share.toLocaleString('de-DE')+' Prozent');
  const chip=document.createElement('i');chip.style.background=c.hex;const txt=document.createElement('div');const hex=document.createElement('strong');hex.textContent=c.hex.toUpperCase();const share=document.createElement('span');share.textContent=c.share.toLocaleString('de-DE')+' %';txt.append(hex,share);node.append(chip,txt);node.onclick=()=>selectPaletteColor(c.hex);
  const card=document.createElement('div');card.className='swatchCard';const locate=document.createElement('button');locate.type='button';locate.className='locateColor quiet';locate.dataset.locate=c.hex;locate.textContent='Lokalisieren';locate.setAttribute('aria-label','Farbe '+c.hex.toUpperCase()+' lokalisieren');locate.setAttribute('aria-pressed',String(locatedColor===c.hex));locate.onclick=()=>locateColor(c.hex);card.append(node,locate);$('palette').append(card);
 }paletteHint();
}
function changePaletteColor(source,target){
 if(source===target)return;
 paletteHistory.push(copyEdit(paletteEdit));
 const edit=copyEdit(paletteEdit)||{base:[...paletteBase],map:{}};
 // Recolor every original member of the selected visible color, including
 // colors merged or recolored in earlier steps. Do not cascade replacements.
 for(const base of edit.base)if((edit.map[base]||base)===source)edit.map[base]=target;
 paletteEdit=edit;mergeMode=false;mergeTarget=null;invalidate(true);preview();
}
function selectPaletteColor(color){
 if(pickingBackground){takeBackground(color);return;}
 if(mergeMode){if(!mergeTarget){mergeTarget=color;paletteHint();}else if(mergeTarget===color){mergeTarget=null;paletteHint();}else{const target=mergeTarget;changePaletteColor(color,target);toast(`${color.toUpperCase()} wurde mit ${target.toUpperCase()} zusammengefasst.`);}return;}
 editingColor=color;$('paletteDialogTitle').textContent='Farbe '+color.toUpperCase()+' ändern';$('paletteColor').value=color;$('paletteHex').value=color.toUpperCase();$('paletteColorError').hidden=true;$('paletteDialog').showModal();
}
$('mergeColors').onclick=()=>{stopPicking();clearLocalization();mergeMode=!mergeMode;mergeTarget=null;paletteHint();};
$('undoPalette').onclick=()=>{if(!paletteHistory.length)return;paletteEdit=paletteHistory.pop();mergeMode=false;mergeTarget=null;invalidate(true);preview();};
$('resetPalette').onclick=()=>{clearPaletteEdits();invalidate(true);preview();};
for(const id of ['closePaletteDialog','cancelPaletteDialog'])$(id).onclick=()=>$('paletteDialog').close();
$('paletteColor').oninput=()=>{$('paletteHex').value=$('paletteColor').value.toUpperCase();$('paletteColorError').hidden=true;};
$('paletteHex').oninput=()=>{const validHex=/^#[0-9a-fA-F]{6}$/.test($('paletteHex').value);$('paletteColorError').hidden=validHex;if(validHex)$('paletteColor').value=$('paletteHex').value;};
$('applyPaletteColor').onclick=()=>{
 const hex=$('paletteHex').value;if(!/^#[0-9a-fA-F]{6}$/.test(hex)){$('paletteColorError').hidden=false;$('paletteHex').focus();return;}
 const source=editingColor;$('paletteDialog').close();if(source)changePaletteColor(source,hex.toLowerCase());
};
function applyView(){
 const p=Number($('compare').value);$('original').style.clipPath=view==='original'?'inset(0)':view==='result'?'inset(0 100% 0 0)':`inset(0 ${100-p}% 0 0)`;
 $('divider').style.left=p+'%';$('divider').hidden=view!=='compare';$('originalTag').hidden=view==='result';$('resultTag').hidden=view==='original';
 $('compare').disabled=!current||view!=='compare';
 for(const button of document.querySelectorAll('[data-view]')){button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));}
}
function imageToolState(){
 $('imageToolState').hidden=!pickingBackground&&!locatedColor;
 $('imageToolText').textContent=pickingBackground?'Pipette aktiv: Im Bild oder auf eine Palettenfarbe klicken. Transparente Bereiche werden nicht aufgenommen.':locatedColor?`Farbe ${locatedColor.toUpperCase()} im vorbereiteten Bild markiert · Indikator ${$('indicatorColor').value.toUpperCase()}`:'';
 $('pickBackground').textContent=pickingBackground?'Pipette abbrechen':'Pipette: Farbe aufnehmen';$('pickBackground').setAttribute('aria-pressed',String(pickingBackground));$('imageStack').classList.toggle('picking',pickingBackground);$('clearLocate').hidden=!locatedColor;
 for(const b of $('palette').querySelectorAll('.locateColor')){b.classList.toggle('active',b.dataset.locate===locatedColor);b.setAttribute('aria-pressed',String(b.dataset.locate===locatedColor));}
 paletteHint();
 buttons();
}
function stopPicking(){pickingBackground=false;imageToolState();}
function clearLocalization(restore=true){
 const previous=locatePreviousView;locatedColor=null;locatePreviousView=null;$('colorOverlay').hidden=true;
 if(restore&&previous!==null){view=previous;applyView();}imageToolState();
}
function renderLocalization(){
 if(!locatedColor)return;const image=$('processed');if(!image.complete||!image.naturalWidth)return;
 try{const canvas=$('colorOverlay');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);const data=ctx.getImageData(0,0,canvas.width,canvas.height);data.data.set(ColorTools.mask(data.data,locatedColor,$('indicatorColor').value));ctx.putImageData(data,0,0);canvas.hidden=false;imageToolState();}catch{clearLocalization();toast('Die Farbe konnte nicht markiert werden. Vorschau erneut laden.');}
}
function locateColor(color){
 stopPicking();mergeMode=false;mergeTarget=null;if(locatedColor===color){clearLocalization();return;}
 if(locatePreviousView===null)locatePreviousView=view;locatedColor=color;view='result';applyView();renderLocalization();$('stage').scrollIntoView({block:'center',behavior:'instant'});
}
function takeBackground(color){$('background').value=color;stopPicking();invalidate();toast('Hintergrundfarbe '+color.toUpperCase()+' aufgenommen.');}
$('pickBackground').onclick=()=>{if(pickingBackground){stopPicking();return;}clearLocalization();mergeMode=false;mergeTarget=null;pickingBackground=true;imageToolState();$('stage').scrollIntoView({block:'center',behavior:'instant'});};
$('imageStack').onclick=e=>{
 if(!pickingBackground)return;const result=$('processed'),bounds=result.getBoundingClientRect();
 const original=view==='original'||(view==='compare'&&e.clientX<bounds.left+bounds.width*Number($('compare').value)/100);
 const image=original?$('original'):result,point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),image.naturalWidth,image.naturalHeight);
 if(!point)return;
 try{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.imageSmoothingEnabled=false;ctx.drawImage(image,point.x,point.y,1,1,0,0,1,1);const color=ColorTools.hex(ctx.getImageData(0,0,1,1).data);if(!color){toast('Dieser Bildpunkt ist transparent. Bitte eine sichtbare Farbe auswählen.');return;}takeBackground(color);}catch{toast('Farbe konnte nicht aufgenommen werden. Bitte einen Paletteneintrag wählen.');}
};
for(const id of ['original','processed'])$(id).addEventListener('load',()=>{buttons();if(id==='processed')renderLocalization();});
$('indicatorColor').oninput=renderLocalization;
$('clearLocate').onclick=()=>clearLocalization();
$('stopImageTool').onclick=()=>{stopPicking();clearLocalization();};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){stopPicking();clearLocalization();}});
async function preview(){
 clearTimeout(debounce);if(!current||!valid())return;
 previewController?.abort();
 const controller=new AbortController();previewController=controller;
 const n=++requestNo, s=values(), id=current.id;
 $('busy').hidden=false;
 try{
  const result=await(await api('/api/preview',{id,settings:s},controller.signal)).json();
  if(n!==requestNo||current?.id!==id)return;
  $('processed').src=result.image;$('canvas').hidden=false;$('empty').hidden=true;
  renderedSettings=s;stats(result.stats);applyView();
 }catch(error){if(n===requestNo&&error.name!=='AbortError')toast(error.message);}finally{if(n===requestNo){$('busy').hidden=true;buttons();}if(previewController===controller)previewController=null;}
}
function stats(s){
 $('colorCount').textContent=s.colors+' / '+s.settings.colors;
 $('dimensions').textContent=`${s.width_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} × ${s.height_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} mm`;
 $('pixelSize').textContent=s.width_px+' × '+s.height_px+' px';
 paletteBase=s.base_palette;paletteColors=s.palette;$('paletteTools').hidden=false;$('paletteHint').hidden=false;renderPalette();
 $('notices').replaceChildren();for(const notice of s.notices){const p=document.createElement('p');p.textContent=notice;$('notices').append(p);}
}
function openProject(p){
 stopPicking();clearLocalization();
 previewController?.abort();
 clearPaletteEdits();paletteBase=[];paletteColors=[];$('palette').replaceChildren();$('paletteTools').hidden=true;$('paletteHint').hidden=true;
 current=p;$('filename').textContent=p.name;$('original').src='/api/original?id='+p.id;
 sizeFeedback();
 $('backSource').hidden=!p.parent_id;
 $('processed').removeAttribute('src');$('canvas').hidden=true;$('empty').hidden=false;$('busy').hidden=true;
 clearAnalysis();requestNo++;renderedSettings=null;buttons();preview();
}
async function recent(){try{const result=await(await authFetch('/api/projects')).json();$('recent').replaceChildren();for(const p of result.slice(0,6)){const b=document.createElement('button');b.textContent=p.name;b.title=p.name;b.onclick=()=>{setValues(defaults);openProject(p);};$('recent').append(b);}}catch{}}
async function load(file, imported=false){
 if(!file||uploading)return;if(file.size>20*1024*1024){toast('Bitte eine Datei bis 20 MB auswählen.');return;}
 const context=imported?handoffContext:null;if(imported&&!context){toast('Zuerst einen Bildauftrag vorbereiten.');return;}
 uploading=true;buttons();$('busy').hidden=false;
 try{
  const headers={'X-Atelier':'1','X-Filename':encodeURIComponent(imported?'ChatGPT · '+file.name:file.name)};
  if(context){headers['X-Atelier-Kind']='chatgpt-'+context.action;if(context.source_id)headers['X-Atelier-Source']=context.source_id;}
  const response=await authFetch('/api/upload',{method:'POST',headers,body:file});const result=await response.json();if(!response.ok)throw new Error(result.error);
  if(context){setValues({...defaults,colors:context.settings.colors,long_side_mm:context.settings.long_side_mm});chooseMode(context.mode);handoffContext=null;$('handoffResult').hidden=true;$('handoffImage').removeAttribute('src');}
  openProject(result);recent();if(imported)toast('Neue Variante geladen. Farben und Konturen vor dem Export prüfen.');
 }catch(error){toast(error.message);$('busy').hidden=true;}finally{uploading=false;buttons();$('file').value='';$('aiFile').value='';}
}
async function loadDemo(){if(uploading)return;try{setValues({...defaults,remove_bg:true,smooth:1});openProject(await(await api('/api/demo')).json());recent();}catch(error){toast(error.message);}}
for(const key of keys)$(key).addEventListener('input',invalidate);
$('compare').oninput=applyView;
$('auto').onchange=()=>{if($('auto').checked)preview();};
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{clearLocalization(false);view=button.dataset.view;applyView();};
function chooseMode(next){
 mode=next;for(const b of document.querySelectorAll('[data-mode]')){b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));}
 $('modeHint').textContent=mode==='logo'?'Behutsame Vorgabe für Formen und Schrift. Alle Änderungen im Vergleich prüfen.':'Weniger Kleinstflächen und ruhigere Konturen. Wichtige Motivdetails im Vergleich prüfen.';
}
for(const button of document.querySelectorAll('[data-mode]'))button.onclick=()=>{
 chooseMode(button.dataset.mode);
 setValues({...defaults,long_side_mm:values().long_side_mm,colors:values().colors,...(mode==='illustration'?{smooth:1,detail_mm:0.3}: {})});invalidate();
};
for(const id of ['uploadButton','emptyUpload'])$(id).onclick=()=>$('file').click();
for(const id of ['demoButton','emptyDemo'])$(id).onclick=loadDemo;
$('file').onchange=e=>load(e.target.files[0]);
$('aiFile').onchange=e=>load(e.target.files[0],true);
$('importAI').onclick=()=>$('aiFile').click();
$('backSource').onclick=async()=>{if(!current?.parent_id||uploading)return;try{const response=await authFetch('/api/project?id='+current.parent_id);const p=await response.json();if(!response.ok)throw new Error(p.error);setValues(defaults);openProject(p);}catch(error){toast(error.message);}};
for(const ev of ['dragenter','dragover'])$('stage').addEventListener(ev,e=>{e.preventDefault();$('stage').classList.add('drag');});
$('stage').ondragleave=()=>$('stage').classList.remove('drag');
$('stage').ondrop=e=>{e.preventDefault();$('stage').classList.remove('drag');load(e.dataTransfer.files[0]);};
$('reset').onclick=()=>{setValues(defaults);invalidate();};
$('previewButton').onclick=preview;
$('exportButton').onclick=async()=>{
 if(!current||!valid()||exporting)return;
 exporting=true;buttons();const s=values(),id=current.id;
 try{
  const blob=await(await api('/api/export',{id,settings:s})).blob();
  const link=document.createElement('a'), url=URL.createObjectURL(blob);link.href=url;link.download='stickatelier-creator9.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  toast('Vorlage exportiert. Zielgröße anschließend in Creator 9 prüfen.');
 }catch(error){toast(error.message);}finally{exporting=false;buttons();}
};
async function account(){
 try{
  const s=await(await authFetch('/api/ai/status')).json();
  $('accountButton').textContent=s.connected?'ChatGPT verbunden':'ChatGPT verbinden';
  $('accountState').textContent=s.connected?`${s.email||'Konto verbunden'} · ${s.plan_enabled?'Tarifnutzung freigegeben':'Tarifnutzung noch nicht freigegeben'}`:'Noch nicht verbunden.';
  $('disconnect').hidden=!s.connected;$('connect').hidden=s.connected&&s.plan_enabled;
  if(s.connected&&s.plan_enabled){
   const response=await authFetch('/api/ai/models'),models=await response.json();if(!response.ok)throw new Error(models.error);
   $('model').replaceChildren();for(const m of models){const opt=document.createElement('option');opt.value=m.id;opt.textContent=m.name;$('model').append(opt);}$('model').disabled=!models.length;
  }else{$('model').replaceChildren(new Option('ChatGPT zuerst verbinden',''));$('model').disabled=true;}
 }catch(error){$('model').disabled=true;toast(error.message);}finally{buttons();}
}
$('accountButton').onclick=()=>{$('accountDialog').showModal();account();};
$('closeDialog').onclick=()=>$('accountDialog').close();
$('refreshAccount').onclick=account;
$('connect').onclick=async()=>{
 const tab=window.open('about:blank','_blank');
 try{const result=await(await api('/api/ai/connect')).json();if(tab){tab.opener=null;tab.location=result.url;}else{toast('Bitte Pop-ups für die Anmeldung erlauben.');}}catch(error){tab?.close();toast(error.message);}
};
$('disconnect').onclick=async()=>{try{const r=await(await api('/api/ai/disconnect')).json();toast(r.message);account();}catch(error){toast(error.message);}};
$('aiButton').onclick=async()=>{
 if(!current||aiRunning)return;clearAnalysis();aiRunning=true;buttons();$('aiButton').textContent='Motiv wird analysiert …';
 const id=current.id,s=values(),sequence=analysisSequence;
 try{
  const r=await(await api('/api/ai/suggest',{id,settings:s,mode,model:$('model').value,goal:$('goal').value})).json();if(current?.id!==id)return;
  if(sequence!==analysisSequence||JSON.stringify(s)!==JSON.stringify(values())){toast('Einstellungen wurden inzwischen geändert. Analyse erneut anfordern.');return;}
  suggestion=r;$('aiExplanation').textContent=r.explanation;$('aiWarnings').replaceChildren();for(const text of r.warnings){const li=document.createElement('li');li.textContent=text;$('aiWarnings').append(li);}
  $('analysisFindings').replaceChildren();for(const f of r.findings){const card=document.createElement('div');card.className='finding '+f.severity;const title=document.createElement('strong');title.textContent=f.title;const text=document.createElement('p');text.textContent=f.detail;const level=document.createElement('span');level.textContent={low:'Hinweis',medium:'Prüfen',high:'Besonders prüfen'}[f.severity];card.append(level,title,text);$('analysisFindings').append(card);}
  const names={colors:'Max. Farben',smooth:'Glättung',contrast:'Kontrast',detail_mm:'Kleine Farbflächen',darken_mm:'Dunkle Details',remove_bg:'Hintergrund entfernen',background:'Hintergrundfarbe',tolerance:'Farbtoleranz'};
  $('analysisChanges').replaceChildren();for(const [key,name] of Object.entries(names))if(s[key]!==r.settings[key]){const line=document.createElement('p');const format=v=>typeof v==='boolean'?(v?'An':'Aus'):String(v);line.textContent=`${name}: ${format(s[key])} → ${format(r.settings[key])}`;$('analysisChanges').append(line);}
  if(!$('analysisChanges').childElementCount)$('analysisChanges').textContent='Die KI empfiehlt, die aktuellen Bildregler beizubehalten.';
  if(paletteEdit){const p=document.createElement('p');p.textContent='Beim Übernehmen werden manuelle Farbzuordnungen zurückgesetzt.';$('analysisChanges').append(p);}
  $('editFromAnalysis').hidden=!r.edit_prompt;$('aiResult').hidden=false;
 }catch(error){toast(error.message);}finally{aiRunning=false;$('aiButton').textContent='Motiv analysieren';buttons();}
};
$('previewAI').onclick=async()=>{
 if(!suggestion||analysisPreviewRunning)return;const proposed=suggestion,id=current.id;analysisApproved=false;analysisPreviewRunning=true;buttons();$('previewAI').textContent='Vorschlag wird vorbereitet …';
 try{const r=await(await api('/api/preview',{id,settings:proposed.settings})).json();if(suggestion!==proposed||current?.id!==id)return;$('analysisImage').src=r.image;$('analysisPreview').hidden=false;analysisApproved=true;}catch(error){if(suggestion===proposed)toast(error.message);}finally{analysisPreviewRunning=false;$('previewAI').textContent='Reglervorschlag ansehen';buttons();}
};
$('applyAI').onclick=()=>{if(!suggestion||!analysisApproved)return;setValues(suggestion.settings);invalidate();preview();toast('Reglervorschlag übernommen. Formen und Schrift im Vergleich prüfen.');};
function aiTab(next){for(const b of document.querySelectorAll('[data-ai-tab]')){b.classList.toggle('active',b.dataset.aiTab===next);b.setAttribute('aria-pressed',String(b.dataset.aiTab===next));}for(const id of ['analysis','edit','generate'])$(id+'Panel').hidden=id!==next;}
for(const b of document.querySelectorAll('[data-ai-tab]'))b.onclick=()=>aiTab(b.dataset.aiTab);
$('openAI').onclick=()=>$('aiWorkbench').scrollIntoView({block:'start'});
$('editFromAnalysis').onclick=()=>{if(!suggestion)return;$('editGoal').value=suggestion.edit_prompt;aiTab('edit');buttons();};
for(const id of ['editGoal','generateGoal'])$(id).oninput=buttons;
async function prepareHandoff(action){
 if(handoffWorking||!valid()||(action==='edit'&&!current))return;handoffWorking=true;buttons();
 const s=values(),sourceName=current?.name||'',selectedStyle=action==='edit'?mode:$('motifStyle').value,selectedMode=action==='edit'?mode:(selectedStyle==='logo'?'logo':'illustration');
 try{
  const r=await(await api('/api/ai/handoff',{action,id:current?.id,settings:s,goal:$(action==='edit'?'editGoal':'generateGoal').value,image_source:$('editSource').value,style:selectedStyle,preserve_text:$('preserveText').checked,transparent:$(action==='edit'?'editTransparent':'generateTransparent').checked})).json();
  handoffContext={...r,mode:selectedMode};
  $('handoffPrompt').value=r.prompt;$('handoffTitle').textContent=action==='edit'?'Bildbearbeitung für ChatGPT vorbereitet':'Neues Motiv für ChatGPT vorbereitet';$('handoffSource').textContent=(action==='edit'?'Ausgangsvorlage: '+sourceName+' · ':'')+s.colors+' Farben · '+s.long_side_mm+' mm lange Seite';
  $('handoffImage').hidden=!r.image;$('downloadHandoff').hidden=!r.image;if(r.image)$('handoffImage').src=r.image;else $('handoffImage').removeAttribute('src');$('handoffResult').hidden=false;
  toast('Auftrag vorbereitet. Jetzt Anweisung kopieren und in ChatGPT verwenden.');
 }catch(error){toast(error.message);}finally{handoffWorking=false;buttons();}
}
$('prepareEdit').onclick=()=>prepareHandoff('edit');$('prepareGenerate').onclick=()=>prepareHandoff('generate');
$('copyHandoff').onclick=async()=>{try{await navigator.clipboard.writeText($('handoffPrompt').value);toast('Anweisung kopiert. In ChatGPT einfügen.');}catch{$('handoffPrompt').focus();$('handoffPrompt').select();toast('Bitte die markierte Anweisung mit Strg+C kopieren.');}};
$('downloadHandoff').onclick=()=>{if(!handoffContext?.image)return;const bytes=Uint8Array.from(atob(handoffContext.image.split(',')[1]),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'image/png'}));const link=document.createElement('a');link.href=url;link.download='stickatelier-chatgpt-referenz.png';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('Referenzbild bereit. Dieses Bild in ChatGPT an die Anweisung anhängen.');};
labels();applyView();recent();account();
