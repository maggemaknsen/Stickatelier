'use strict';
const $=id=>document.getElementById(id);
const keys=['colors','short_side_mm','smooth','contrast','detail_mm','darken_mm','remove_bg','background','tolerance'];
const defaults={colors:6,short_side_mm:100,smooth:0,contrast:100,detail_mm:0,darken_mm:0,remove_bg:false,background:'#ffffff',tolerance:20};
let current=null, mode='logo', view='compare', requestNo=0, debounce, exporting=false,uploading=false, renderedSettings=null, previewController=null;
let paletteEdit=null, paletteBase=[], paletteColors=[], paletteHistory=[], mergeMode=false, mergeTarget=null, editingColor=null;
let fillEdits=[], filling=false, fillApplying=false, fillColorChosen=false;
let pickingBackground=false, locatedColor=null, locatePreviousView=null;
const zoomSteps=[.25,.5,.75,1,1.25,1.5,2,3,4,6,8];
let zoom=1;
function values(){const s={};for(const key of keys)s[key]=key==='remove_bg'?$(key).checked:key==='background'?$(key).value:Number($(key).value);s.palette_edit=paletteEdit;s.fill_edits=fillEdits;return s;}
function valid(){const w=Number($('short_side_mm').value);return Number.isFinite(w)&&w>=10;}
function sizeFeedback(){
 const accepted=valid(),field=$('short_side_mm');field.setAttribute('aria-invalid',String(!accepted));field.setCustomValidity(accepted?'':'Bitte eine kurze Seite von mindestens 10 mm eingeben.');$('sizeError').hidden=accepted;
 const shortSide=Number(field.value),longSide=current?shortSide*Math.max(current.width,current.height)/Math.min(current.width,current.height):shortSide;
 $('frameWarning').hidden=!accepted||(shortSide<=160&&longSide<=260);
 if(!accepted||!current){$('dimensions').textContent='–';return;}
 const scale=Number(field.value)/Math.min(current.width,current.height),width=Math.round(current.width*scale*10)/10,height=Math.round(current.height*scale*10)/10;
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
 $('exportButton').disabled=!current||!valid()||exporting||uploading||fillApplying||JSON.stringify(renderedSettings)!==JSON.stringify(values());
 const paletteReady=!!current&&valid()&&!uploading&&!fillApplying&&JSON.stringify(renderedSettings)===JSON.stringify(values());
 for(const b of $('palette').querySelectorAll('button'))b.disabled=!paletteReady;
 for(const b of $('palette').querySelectorAll('.swatch'))b.disabled=!paletteReady&&!(pickingBackground&&current&&!uploading);
 for(const b of $('palette').querySelectorAll('.locateColor'))b.disabled=!paletteReady||!$('processed').complete;
 $('pickBackground').disabled=!current||uploading||$('canvas').hidden||!$('original').complete||!$('processed').complete||!$('remove_bg').checked;
 $('mergeColors').disabled=!paletteReady||paletteColors.length<2;
 $('undoPalette').disabled=!paletteReady||!paletteHistory.length;
 $('resetPalette').disabled=!paletteReady||!paletteEdit;
 $('applyPaletteColor').disabled=!paletteReady;
 $('fillButton').disabled=!paletteReady||!$('processed').complete||!$('processed').naturalWidth;
 $('moreFillColors').disabled=!paletteReady;
 $('fillColor').disabled=!paletteReady;
 for(const b of $('fillPalette').querySelectorAll('button'))b.disabled=!paletteReady;
 const zoomReady=!!current&&!$('canvas').hidden&&$('processed').complete&&!!$('processed').naturalWidth;
 $('zoomOut').disabled=!zoomReady||zoom<=zoomSteps[0];
 $('zoomIn').disabled=!zoomReady||zoom>=zoomSteps[zoomSteps.length-1];
 $('zoomReset').disabled=!zoomReady;
 $('resetFills').disabled=!current||!fillEdits.length||fillApplying||uploading;
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,6500);}
async function authFetch(...args){const response=await fetch(...args);if(response.status===401){window.location.replace('/');throw new Error('Bitte erneut anmelden.');}return response;}
$('logoutButton').onclick=async()=>{try{await api('/auth/logout');window.location.replace('/');}catch(error){toast(error.message);}};
async function api(path,body={},signal){
 const response=await authFetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Atelier':'1'},body:JSON.stringify(body),signal});
 if(!response.ok){const error=await response.json();throw new Error(error.error||'Anfrage fehlgeschlagen.');}return response;
}
function invalidate(keepPalette=false,keepFills=false){if(keepFills!==true)clearFills(true);stopPicking();clearLocalization();if(keepPalette!==true)clearPaletteEdits(true);previewController?.abort();renderedSettings=null;requestNo++;$('busy').hidden=true;clearTimeout(debounce);labels();if(current&&$('auto').checked)debounce=setTimeout(preview,400);}
function snapshot(){return {edit:copyEdit(paletteEdit),fills:fillEdits.map(f=>({...f}))};}
function clearFills(notify=false){const changed=fillEdits.length>0;fillEdits=[];filling=false;if(changed&&notify)toast('Füllungen zurückgesetzt: Die Bildregler berechnen die Bereiche neu.');}
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
 renderFillColors();
}
function chooseFillColor(color){$('fillColor').value=color;fillColorChosen=true;renderFillColors();}
function renderFillColors(){
 if(!fillColorChosen&&paletteColors.length)$('fillColor').value=paletteColors[0].hex;
 const selected=$('fillColor').value.toLowerCase();
 $('fillSelection').textContent='Füllfarbe: '+selected.toUpperCase();
 $('fillSelectedChip').style.background=selected;
 $('fillPalette').replaceChildren();
 for(const c of paletteColors){
  const button=document.createElement('button');button.type='button';button.className='fillSwatch';button.style.background=c.hex;button.title=c.hex.toUpperCase();button.setAttribute('aria-label','Mit '+c.hex.toUpperCase()+' füllen');button.setAttribute('aria-pressed',String(c.hex===selected));button.classList.toggle('selected',c.hex===selected);button.onclick=()=>{chooseFillColor(c.hex);buttons();};$('fillPalette').append(button);
 }
 $('fillPaletteEmpty').hidden=paletteColors.length>0;
}
function changePaletteColor(source,target){
 if(source===target)return;
 paletteHistory.push(snapshot());
 const edit=copyEdit(paletteEdit)||{base:[...paletteBase],map:{}};
 // Recolor every original member of the selected visible color, including
 // colors merged or recolored in earlier steps. Do not cascade replacements.
 for(const base of edit.base)if((edit.map[base]||base)===source)edit.map[base]=target;
 paletteEdit=edit;fillEdits=fillEdits.map(f=>f.color===source?{...f,color:target}:f);mergeMode=false;mergeTarget=null;invalidate(true,true);preview();
}
function selectPaletteColor(color){
 if(pickingBackground){takeBackground(color);return;}if(filling){chooseFillColor(color);buttons();return;}
 if(mergeMode){if(!mergeTarget){mergeTarget=color;paletteHint();}else if(mergeTarget===color){mergeTarget=null;paletteHint();}else{const target=mergeTarget;changePaletteColor(color,target);toast(`${color.toUpperCase()} wurde mit ${target.toUpperCase()} zusammengefasst.`);}return;}
 editingColor=color;$('paletteDialogTitle').textContent='Farbe '+color.toUpperCase()+' ändern';$('paletteColor').value=color;$('paletteHex').value=color.toUpperCase();$('paletteColorError').hidden=true;$('paletteDialog').showModal();
}
$('mergeColors').onclick=()=>{filling=false;stopPicking();clearLocalization();mergeMode=!mergeMode;mergeTarget=null;paletteHint();};
$('undoPalette').onclick=()=>{if(!paletteHistory.length)return;const previous=paletteHistory.pop();paletteEdit=previous.edit;fillEdits=previous.fills;mergeMode=false;mergeTarget=null;invalidate(true,true);preview();};
$('resetPalette').onclick=()=>{clearPaletteEdits();invalidate(true);preview();};
for(const id of ['closePaletteDialog','cancelPaletteDialog'])$(id).onclick=()=>$('paletteDialog').close();
$('paletteColor').oninput=()=>{$('paletteHex').value=$('paletteColor').value.toUpperCase();$('paletteColorError').hidden=true;};
$('paletteHex').oninput=()=>{const validHex=/^#[0-9a-fA-F]{6}$/.test($('paletteHex').value);$('paletteColorError').hidden=validHex;if(validHex)$('paletteColor').value=$('paletteHex').value;};
$('applyPaletteColor').onclick=()=>{
 const hex=$('paletteHex').value;if(!/^#[0-9a-fA-F]{6}$/.test(hex)){$('paletteColorError').hidden=false;$('paletteHex').focus();return;}
 const source=editingColor;$('paletteDialog').close();if(source)changePaletteColor(source,hex.toLowerCase());
};
function applyZoom(reset=false){
 const viewport=$('canvas'),surface=$('zoomSurface'),image=$('processed');
 $('zoomLevel').value=Math.round(zoom*100)+' %';
 if(!current||viewport.hidden||!image.naturalWidth||!viewport.clientWidth||!viewport.clientHeight)return;
 const w=viewport.clientWidth,h=viewport.clientHeight;
 const centerX=((viewport.scrollLeft||0)+w/2)/(surface.offsetWidth||w),centerY=((viewport.scrollTop||0)+h/2)/(surface.offsetHeight||h);
 const fit=Math.min(Math.max(1,w-40)/image.naturalWidth,Math.max(1,h-40)/image.naturalHeight,1);
 const imageWidth=image.naturalWidth*fit*zoom,imageHeight=image.naturalHeight*fit*zoom;
 const surfaceWidth=Math.max(w,imageWidth+40),surfaceHeight=Math.max(h,imageHeight+40);
 surface.style.width=surfaceWidth+'px';surface.style.height=surfaceHeight+'px';
 $('imageStack').style.width=imageWidth+'px';$('imageStack').style.height=imageHeight+'px';
 viewport.scrollLeft=(reset?0.5:centerX)*surfaceWidth-w/2;
 viewport.scrollTop=(reset?0.5:centerY)*surfaceHeight-h/2;
}
function setZoom(value,reset=false){zoom=Math.max(zoomSteps[0],Math.min(zoomSteps[zoomSteps.length-1],value));applyZoom(reset);buttons();}
$('zoomIn').onclick=()=>setZoom(zoomSteps.find(step=>step>zoom)||zoom);
$('zoomOut').onclick=()=>setZoom([...zoomSteps].reverse().find(step=>step<zoom)||zoom);
$('zoomReset').onclick=()=>setZoom(1,true);
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>applyZoom()).observe($('canvas'));
else if(typeof window!=='undefined')window.addEventListener('resize',()=>applyZoom());
function applyView(){
 const p=Number($('compare').value);$('original').style.clipPath=view==='original'?'inset(0)':view==='result'?'inset(0 100% 0 0)':`inset(0 ${100-p}% 0 0)`;
 $('divider').style.left=p+'%';$('divider').hidden=view!=='compare';$('originalTag').hidden=view==='result';$('resultTag').hidden=view==='original';
 $('compare').disabled=!current||view!=='compare';
 for(const button of document.querySelectorAll('[data-view]')){button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));}
}
function imageToolState(){
 $('imageToolState').hidden=!pickingBackground&&!locatedColor&&!filling;
 $('fillButton').textContent=filling?'Füllen beenden':'Bereich füllen';$('fillButton').setAttribute('aria-pressed',String(filling));
 $('imageToolText').textContent=filling?'Füllwerkzeug aktiv: In der Ergebnisansicht auf einen Bereich klicken. Eine Palettenfarbe übernimmt die Füllfarbe. Esc beendet das Werkzeug.':pickingBackground?'Pipette aktiv: Im Bild oder auf eine Palettenfarbe klicken. Transparente Bereiche werden nicht aufgenommen.':locatedColor?`Farbe ${locatedColor.toUpperCase()} im vorbereiteten Bild markiert · Indikator ${$('indicatorColor').value.toUpperCase()}`:'';
 $('pickBackground').textContent=pickingBackground?'Pipette abbrechen':'Pipette: Farbe aufnehmen';$('pickBackground').setAttribute('aria-pressed',String(pickingBackground));$('imageStack').classList.toggle('picking',pickingBackground);$('imageStack').classList.toggle('filling',filling);$('clearLocate').hidden=!locatedColor;
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
 filling=false;stopPicking();mergeMode=false;mergeTarget=null;if(locatedColor===color){clearLocalization();return;}
 if(locatePreviousView===null)locatePreviousView=view;locatedColor=color;view='result';applyView();renderLocalization();$('stage').scrollIntoView({block:'center',behavior:'instant'});
}
function takeBackground(color){$('background').value=color;stopPicking();invalidate();toast('Hintergrundfarbe '+color.toUpperCase()+' aufgenommen.');}
$('pickBackground').onclick=()=>{filling=false;if(pickingBackground){stopPicking();return;}clearLocalization();mergeMode=false;mergeTarget=null;pickingBackground=true;imageToolState();$('stage').scrollIntoView({block:'center',behavior:'instant'});};
$('fillButton').onclick=()=>{const next=!filling;stopPicking();clearLocalization();mergeMode=false;mergeTarget=null;filling=next;if(next){view='result';applyView();}imageToolState();};
$('moreFillColors').onclick=()=>{const opening=$('extraFillColors').hidden;$('extraFillColors').hidden=!opening;$('moreFillColors').setAttribute('aria-expanded',String(opening));};
$('fillColor').oninput=()=>{fillColorChosen=true;renderFillColors();buttons();};
$('resetFills').onclick=()=>{paletteHistory.push(snapshot());clearFills();invalidate(true,true);preview();};
async function fillAt(e){
 if(fillApplying||!current||JSON.stringify(renderedSettings)!==JSON.stringify(values()))return;
 const image=$('processed'),point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),image.naturalWidth,image.naturalHeight);
 if(!point)return;if(fillEdits.length>=100){toast('Höchstens 100 Füllungen pro Motiv.');return;}
 const previous=snapshot(),next=[...fillEdits,{x:(point.x+.5)/image.naturalWidth,y:(point.y+.5)/image.naturalHeight,color:$('fillColor').value.toLowerCase()}];
 paletteEdit=paletteEdit||{base:[...paletteBase],map:{}};fillEdits=next;fillApplying=true;buttons();
 const applied=await preview();fillApplying=false;
 if(fillEdits===next){if(applied){paletteHistory.push(previous);}else{paletteEdit=previous.edit;fillEdits=previous.fills;await preview();}}
 buttons();
}
$('imageStack').onclick=e=>{
 if(filling){fillAt(e);return;}if(!pickingBackground)return;const result=$('processed'),bounds=result.getBoundingClientRect();
 const original=view==='original'||(view==='compare'&&e.clientX<bounds.left+bounds.width*Number($('compare').value)/100);
 const image=original?$('original'):result,point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),image.naturalWidth,image.naturalHeight);
 if(!point)return;
 try{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.imageSmoothingEnabled=false;ctx.drawImage(image,point.x,point.y,1,1,0,0,1,1);const color=ColorTools.hex(ctx.getImageData(0,0,1,1).data);if(!color){toast('Dieser Bildpunkt ist transparent. Bitte eine sichtbare Farbe auswählen.');return;}takeBackground(color);}catch{toast('Farbe konnte nicht aufgenommen werden. Bitte einen Paletteneintrag wählen.');}
};
for(const id of ['original','processed'])$(id).addEventListener('load',()=>{buttons();if(id==='processed'){applyZoom();renderLocalization();}});
$('indicatorColor').oninput=renderLocalization;
$('clearLocate').onclick=()=>clearLocalization();
$('stopImageTool').onclick=()=>{filling=false;stopPicking();clearLocalization();};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){filling=false;stopPicking();clearLocalization();}});
async function preview(){
 clearTimeout(debounce);if(!current||!valid())return;
 previewController?.abort();
 const controller=new AbortController();previewController=controller;
 const n=++requestNo, s=values(), id=current.id;
 $('busy').hidden=false;
 try{
  const result=await(await api('/api/preview',{id,settings:s},controller.signal)).json();
  if(n!==requestNo||current?.id!==id)return false;
  $('processed').src=result.image;$('canvas').hidden=false;$('empty').hidden=true;
  renderedSettings=s;stats(result.stats);applyView();return true;
 }catch(error){if(n===requestNo&&error.name!=='AbortError')toast(error.message);}finally{if(n===requestNo){$('busy').hidden=true;buttons();}if(previewController===controller)previewController=null;}
}
function stats(s){
 $('colorCount').textContent=s.colors;
 $('dimensions').textContent=`${s.width_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} × ${s.height_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} mm`;
 $('pixelSize').textContent=s.width_px+' × '+s.height_px+' px';
 paletteBase=s.base_palette;paletteColors=s.palette;$('paletteTools').hidden=false;$('paletteHint').hidden=false;renderPalette();
 $('notices').replaceChildren();for(const notice of s.notices){const p=document.createElement('p');p.textContent=notice;$('notices').append(p);}
}
function openProject(p){
 clearFills();stopPicking();clearLocalization();
 previewController?.abort();
 clearPaletteEdits();paletteBase=[];paletteColors=[];fillColorChosen=false;$('extraFillColors').hidden=true;$('moreFillColors').setAttribute('aria-expanded','false');renderFillColors();$('palette').replaceChildren();$('paletteTools').hidden=true;$('paletteHint').hidden=true;
 current=p;zoom=1;$('zoomLevel').value='100 %';$('canvas').scrollLeft=0;$('canvas').scrollTop=0;$('filename').textContent=p.name;$('original').src='/api/original?id='+p.id;
 sizeFeedback();
 $('backSource').hidden=!p.parent_id;
 $('processed').removeAttribute('src');$('canvas').hidden=true;$('empty').hidden=false;$('busy').hidden=true;
 requestNo++;renderedSettings=null;buttons();preview();
}
async function recent(){try{const result=await(await authFetch('/api/projects')).json();$('recent').replaceChildren();for(const p of result.slice(0,6)){const b=document.createElement('button');b.textContent=p.name;b.title=p.name;b.onclick=()=>{setValues(defaults);openProject(p);};$('recent').append(b);}}catch{}}
async function load(file){
 if(!file||uploading)return;if(file.size>20*1024*1024){toast('Bitte eine Datei bis 20 MB auswählen.');return;}
 uploading=true;buttons();$('busy').hidden=false;
 try{
  const headers={'X-Atelier':'1','X-Filename':encodeURIComponent(file.name)};
  const response=await authFetch('/api/upload',{method:'POST',headers,body:file});const result=await response.json();if(!response.ok)throw new Error(result.error);
  openProject(result);recent();
 }catch(error){toast(error.message);$('busy').hidden=true;}finally{uploading=false;buttons();$('file').value='';}
}
async function loadDemo(){if(uploading)return;try{setValues({...defaults,remove_bg:true,smooth:1});openProject(await(await api('/api/demo')).json());recent();}catch(error){toast(error.message);}}
for(const key of keys)$(key).addEventListener('input',invalidate);
$('compare').oninput=applyView;
$('auto').onchange=()=>{if($('auto').checked)preview();};
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{filling=false;clearLocalization(false);view=button.dataset.view;applyView();};
function chooseMode(next){
 mode=next;for(const b of document.querySelectorAll('[data-mode]')){b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));}
 $('modeHint').textContent=mode==='logo'?'Behutsame Vorgabe für Formen und Schrift. Alle Änderungen im Vergleich prüfen.':'Weniger Kleinstflächen und ruhigere Konturen. Wichtige Motivdetails im Vergleich prüfen.';
}
for(const button of document.querySelectorAll('[data-mode]'))button.onclick=()=>{
 chooseMode(button.dataset.mode);
 setValues({...defaults,short_side_mm:values().short_side_mm,colors:values().colors,...(mode==='illustration'?{smooth:1,detail_mm:0.3}: {})});invalidate();
};
for(const id of ['uploadButton','emptyUpload'])$(id).onclick=()=>$('file').click();
for(const id of ['demoButton','emptyDemo'])$(id).onclick=loadDemo;
$('file').onchange=e=>load(e.target.files[0]);
$('backSource').onclick=async()=>{if(!current?.parent_id||uploading)return;try{const response=await authFetch('/api/project?id='+current.parent_id);const p=await response.json();if(!response.ok)throw new Error(p.error);setValues(defaults);openProject(p);}catch(error){toast(error.message);}};
for(const ev of ['dragenter','dragover'])$('stage').addEventListener(ev,e=>{e.preventDefault();$('stage').classList.add('drag');});
$('stage').ondragleave=()=>$('stage').classList.remove('drag');
$('stage').ondrop=e=>{e.preventDefault();$('stage').classList.remove('drag');load(e.dataTransfer.files[0]);};
$('reset').onclick=()=>{setValues(defaults);invalidate();};
$('previewButton').onclick=preview;
$('exportButton').onclick=async()=>{
 if(!current||!valid()||exporting||fillApplying)return;
 exporting=true;buttons();const s=values(),id=current.id;
 try{
  const blob=await(await api('/api/export',{id,settings:s})).blob();
  const link=document.createElement('a'), url=URL.createObjectURL(blob);link.href=url;link.download='stickatelier-motiv.png';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  toast('Vorlage exportiert. Zielgröße anschließend in Creator 9 prüfen.');
 }catch(error){toast(error.message);}finally{exporting=false;buttons();}
};
labels();applyView();recent();
