'use strict';
const $=id=>document.getElementById(id);
const keys=['colors','color_space','short_side_mm','smooth','contrast','detail_mm','darken_mm','remove_bg','background','tolerance'];
const defaults={colors:6,color_space:'rgb',short_side_mm:100,smooth:0,contrast:100,detail_mm:0,darken_mm:0,remove_bg:false,background:'#ffffff',tolerance:20};
let current=null, mode='logo', view='compare', requestNo=0, debounce, exporting=false,uploading=false, renderedSettings=null, previewController=null;
let paletteEdit=null, paletteBase=[], paletteColors=[], paletteHistory=[], mergeMode=false, mergeTarget=null, editingColor=null;
let fillEdits=[], filling=false, fillApplying=false, fillColorChosen=false;
let fillQueue=[], fillQueueRunning=false, previewPixels=null;
let activeManualType=null;
let pendingBrushes=[], renderedImageEdits=[], editRevision=0;
const brushMask=document.createElement('canvas');
const hoverSample=document.createElement('canvas');
let hoverPointer=null,hoverPixels=null,hoverWorker=null,hoverGeneration=0,hoverJob=0,hoverTimer=null,hoverRegion=null,hoverRequest=null;
let hoverUnavailable=false,hoverPaintedRegion=null,hoverPaintedColor='';
let painting=false, stroke=null;
let pickingBackground=false, locatedColor=null, locatePreviousView=null;
const zoomSteps=[.25,.5,.75,1,1.25,1.5,2,3,4,6,8];
let zoom=1;
function values(){const s={};for(const key of keys)s[key]=key==='remove_bg'?$(key).checked:['background','color_space'].includes(key)?$(key).value:Number($(key).value);s.palette_edit=paletteEdit;s.fill_edits=fillEdits;return s;}
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
 if(fillQueueRunning||fillApplying)clearFillHover();
 const fillingPending=fillQueueRunning&&(activeManualType==='fill'||fillQueue.some(item=>item.edit.type!=='brush'));
 $('fillProgress').hidden=!fillingPending;
 $('previewButton').disabled=!current||!valid()||uploading||fillApplying||fillQueueRunning||!!stroke;
 $('exportButton').disabled=!current||!valid()||exporting||uploading||fillApplying||fillQueueRunning||!!stroke||JSON.stringify(renderedSettings)!==JSON.stringify(values());
 const paletteReady=!!current&&valid()&&!uploading&&!fillApplying&&!fillQueueRunning&&!stroke&&JSON.stringify(renderedSettings)===JSON.stringify(values());
 for(const b of $('palette').querySelectorAll('button'))b.disabled=!paletteReady;
 for(const b of $('palette').querySelectorAll('.swatch'))b.disabled=!paletteReady&&!(pickingBackground&&current&&!uploading);
 for(const b of $('palette').querySelectorAll('.locateColor'))b.disabled=!paletteReady||!$('processed').complete;
 $('pickBackground').disabled=!current||uploading||$('canvas').hidden||!$('original').complete||!$('processed').complete||!$('remove_bg').checked;
 $('mergeColors').disabled=!paletteReady||paletteColors.length<2;
 $('undoPalette').disabled=!paletteReady||!paletteHistory.length;
 $('resetPalette').disabled=!paletteReady||!paletteEdit;
 $('applyPaletteColor').disabled=!paletteReady;
 $('fillButton').disabled=uploading||(!filling&&(!paletteReady||!$('processed').complete||!$('processed').naturalWidth));
 $('brushButton').disabled=uploading||(!painting&&(!paletteReady||!$('processed').complete||!$('processed').naturalWidth));
 $('undoTools').disabled=!paletteReady||!paletteHistory.length;
 $('brushSize').disabled=!!stroke;
 $('resetBrush').disabled=!paletteReady||!fillEdits.some(f=>f.type==='brush');
 const fillColorsReady=paletteReady||((filling||painting)&&!!current&&!uploading&&!stroke);
 $('moreFillColors').disabled=!fillColorsReady;
 $('fillColor').disabled=!fillColorsReady;
 for(const b of $('fillPalette').querySelectorAll('button'))b.disabled=!fillColorsReady;
 const zoomReady=!!current&&!$('canvas').hidden&&$('processed').complete&&!!$('processed').naturalWidth;
 $('zoomOut').disabled=!zoomReady||zoom<=zoomSteps[0];
 $('zoomIn').disabled=!zoomReady||zoom>=zoomSteps[zoomSteps.length-1];
 $('zoomReset').disabled=!zoomReady;
 $('resetFills').disabled=!paletteReady||!fillEdits.some(f=>f.type!=='brush');
 if(hoverPointer&&!fillQueueRunning&&!fillApplying)updateMouseInfo(hoverPointer);
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,6500);}
async function authFetch(...args){const response=await fetch(...args);if(response.status===401){window.location.replace('/');throw new Error('Bitte erneut anmelden.');}return response;}
$('logoutButton').onclick=async()=>{try{await api('/auth/logout');window.location.replace('/');}catch(error){toast(error.message);}};
async function api(path,body={},signal){
 const response=await authFetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Atelier':'1'},body:JSON.stringify(body),signal});
 if(!response.ok){const error=await response.json();throw new Error(error.error||'Anfrage fehlgeschlagen.');}return response;
}
function invalidate(keepPalette=false,keepFills=false){cancelStroke();if(keepFills!==true)clearFills(true);stopPicking();clearLocalization();if(keepPalette!==true)clearPaletteEdits(true);previewController?.abort();renderedSettings=null;requestNo++;$('busy').hidden=true;clearTimeout(debounce);labels();if(current&&$('auto').checked)debounce=setTimeout(preview,400);}
function snapshot(){return {edit:copyEdit(paletteEdit),fills:fillEdits.map(f=>f.type==='brush'?{...f,points:f.points.map(p=>[...p])}:{...f})};}
function clearFills(notify=false){const changed=fillEdits.length>0;editRevision++;fillQueue=[];pendingBrushes=[];renderedImageEdits=[];fillEdits=[];filling=false;stopBrush();if(changed&&notify)toast('Füllungen und Pinselstriche zurückgesetzt: Die Bildregler berechnen das Motiv neu.');}
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
 $('fillSelection').textContent='Korrekturfarbe: '+selected.toUpperCase();
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
 paletteEdit=edit;fillEdits=fillEdits.map(f=>f.color===source?{...f,color:target}:f);mergeMode=false;mergeTarget=null;invalidate(true,true);preview({silent:true});
}
function selectPaletteColor(color){
 if(pickingBackground){takeBackground(color);return;}if(filling||painting){chooseFillColor(color);buttons();return;}
 if(mergeMode){if(!mergeTarget){mergeTarget=color;paletteHint();}else if(mergeTarget===color){mergeTarget=null;paletteHint();}else{const target=mergeTarget;changePaletteColor(color,target);toast(`${color.toUpperCase()} wurde mit ${target.toUpperCase()} zusammengefasst.`);}return;}
 editingColor=color;$('paletteDialogTitle').textContent='Farbe '+color.toUpperCase()+' ändern';$('paletteColor').value=color;$('paletteHex').value=color.toUpperCase();$('paletteColorError').hidden=true;$('paletteDialog').showModal();
}
$('mergeColors').onclick=()=>{filling=false;stopBrush();stopPicking();clearLocalization();mergeMode=!mergeMode;mergeTarget=null;paletteHint();};
function undoEdit(){if(!paletteHistory.length||fillApplying||stroke)return;const previous=paletteHistory.pop();paletteEdit=previous.edit;fillEdits=previous.fills;mergeMode=false;mergeTarget=null;invalidate(true,true);preview({silent:true});}
$('undoPalette').onclick=undoEdit;
$('undoTools').onclick=undoEdit;
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
 clearFillHover();
 const p=Number($('compare').value);$('original').style.clipPath=view==='original'?'inset(0)':view==='result'?'inset(0 100% 0 0)':`inset(0 ${100-p}% 0 0)`;
 $('divider').style.left=p+'%';$('divider').hidden=view!=='compare';$('originalTag').hidden=view==='result';$('resultTag').hidden=view==='original';
 $('compare').disabled=!current||view!=='compare';
 for(const button of document.querySelectorAll('[data-view]')){button.classList.toggle('active',button.dataset.view===view);button.setAttribute('aria-pressed',String(button.dataset.view===view));}
 if(hoverPointer)updateMouseInfo(hoverPointer);
}
function imageToolState(){
 if(!filling)clearFillHover();
 $('imageToolState').hidden=!pickingBackground&&!locatedColor&&!filling&&!painting;
 $('brushButton').textContent=painting?'Pinsel beenden':'Korrekturpinsel';$('brushButton').setAttribute('aria-pressed',String(painting));
 $('fillButton').textContent=filling?'Füllen beenden':'Bereich füllen';$('fillButton').setAttribute('aria-pressed',String(filling));
 $('imageToolText').textContent=painting?'Korrekturpinsel aktiv: Mit gedrückter Maustaste malen. Esc beendet den Pinsel.':filling?'Füllwerkzeug aktiv: In der Ergebnisansicht auf einen Bereich klicken. Eine Palettenfarbe übernimmt die Füllfarbe. Esc beendet das Werkzeug.':pickingBackground?'Pipette aktiv: Im Bild oder auf eine Palettenfarbe klicken. Transparente Bereiche werden nicht aufgenommen.':locatedColor?`Farbe ${locatedColor.toUpperCase()} im vorbereiteten Bild markiert · Indikator ${$('indicatorColor').value.toUpperCase()}`:'';
 $('pickBackground').textContent=pickingBackground?'Pipette abbrechen':'Pipette: Farbe aufnehmen';$('pickBackground').setAttribute('aria-pressed',String(pickingBackground));$('imageStack').classList.toggle('picking',pickingBackground);$('imageStack').classList.toggle('filling',filling);$('clearLocate').hidden=!locatedColor;
 for(const b of $('palette').querySelectorAll('.locateColor')){b.classList.toggle('active',b.dataset.locate===locatedColor);b.setAttribute('aria-pressed',String(b.dataset.locate===locatedColor));}
 $('imageStack').classList.toggle('painting',painting);
 $('stage').classList.toggle('manualEditing',painting||filling||fillApplying);
 if(painting||filling||fillApplying)$('busy').hidden=true;
 paletteHint();
 buttons();
}
function stopPicking(){pickingBackground=false;imageToolState();}
function clearFillHover(){
 clearTimeout(hoverTimer);hoverJob++;hoverRequest=null;hoverRegion=null;$('fillHover').hidden=true;$('fillHoverText').textContent='';
}
function resetMouseInfo(){hoverPointer=null;clearFillHover();$('mouseColor').hidden=true;}
function hoverPixel(image,point){
 hoverSample.width=hoverSample.height=1;
 const ctx=hoverSample.getContext('2d',{willReadFrequently:true});ctx.imageSmoothingEnabled=false;ctx.drawImage(image,point.x,point.y,1,1,0,0,1,1);
 return ctx.getImageData(0,0,1,1).data;
}
function refreshHoverImage(){hoverPixels=null;hoverGeneration++;clearFillHover();if(hoverPointer)updateMouseInfo(hoverPointer);}
function ensureHoverPixels(){
 if(hoverUnavailable)return false;
 if(hoverPixels)return true;
 const image=$('processed');if(!image.complete||!image.naturalWidth||typeof Worker==='undefined')return false;
 const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
 const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
 hoverPixels={width:canvas.width,height:canvas.height,data:ctx.getImageData(0,0,canvas.width,canvas.height).data};
 if(!hoverWorker){
  hoverWorker=new Worker('/fill-preview-worker.js?v=hover-tools-6');
  hoverWorker.onmessage=event=>{
   const data=event.data;if(data.generation!==hoverGeneration||data.job!==hoverJob||!filling||fillQueueRunning||fillApplying||!hoverPointer)return;
   const runs=new Uint32Array(data.runs),rows=new Map();
   for(let i=0;i<runs.length;i+=3){if(!rows.has(runs[i]))rows.set(runs[i],[]);rows.get(runs[i]).push([runs[i+1],runs[i+2]]);}
   hoverRegion={runs,rows,count:data.count};paintFillHover();
  };
  hoverWorker.onerror=()=>{hoverWorker.terminate();hoverWorker=null;hoverPixels=null;hoverUnavailable=true;clearFillHover();$('fillHoverText').textContent='Füllvorschau nicht verfügbar.';};
 }
 const copy=hoverPixels.data.slice();hoverWorker.postMessage({type:'image',width:hoverPixels.width,height:hoverPixels.height,generation:hoverGeneration,pixels:copy.buffer},[copy.buffer]);
 return true;
}
function paintFillHover(){
 if(!hoverRegion||!hoverPixels||!filling)return;
 if(hoverPaintedRegion===hoverRegion&&hoverPaintedColor===$('fillColor').value&&!$('fillHover').hidden)return;
 const canvas=$('fillHover');canvas.width=hoverPixels.width;canvas.height=hoverPixels.height;
 const ctx=canvas.getContext('2d');ctx.fillStyle=$('fillColor').value;ctx.globalAlpha=.5;
 const runs=hoverRegion.runs;for(let i=0;i<runs.length;i+=3)ctx.fillRect(runs[i+1],runs[i],runs[i+2]-runs[i+1]+1,1);
 canvas.hidden=false;$('fillHoverText').textContent='Füllvorschau · '+hoverRegion.count.toLocaleString('de-DE')+' Pixel';
 hoverPaintedRegion=hoverRegion;hoverPaintedColor=$('fillColor').value;
}
function updateMouseInfo(e){
 if(!current||$('canvas').hidden)return resetMouseInfo();
 hoverPointer={clientX:e.clientX,clientY:e.clientY};
 const result=$('processed'),bounds=result.getBoundingClientRect();
 const isOriginal=view==='original'||(view==='compare'&&e.clientX<bounds.left+bounds.width*Number($('compare').value)/100);
 const image=isOriginal?$('original'):result;
 if(!image.complete||!image.naturalWidth){clearFillHover();return;}
 const point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),image.naturalWidth,image.naturalHeight);
 if(!point)return resetMouseInfo();
 try{
  let pixel=hoverPixel(image,point),source=isOriginal?'Original':'Ergebnis';
  if(!isOriginal&&!$('brushPreview').hidden){const overlay=$('brushPreview').getContext('2d').getImageData(point.x,point.y,1,1).data;if(overlay[3]){const a=overlay[3]/255;pixel=new Uint8ClampedArray([0,1,2].map(i=>overlay[i]*a+pixel[i]*(1-a)).concat([255]));source='Pinselvorschau';}}
  const hex=ColorTools.hex(pixel),paletteIndex=!isOriginal&&hex?paletteColors.findIndex(c=>c.hex===hex):-1;
  $('mouseColor').hidden=false;$('mouseColorChip').style.background=hex||'transparent';
  $('mouseColorText').textContent=hex?`${hex.toUpperCase()} · RGB ${pixel[0]}, ${pixel[1]}, ${pixel[2]} · ${source}${paletteIndex>=0?' · Palette '+(paletteIndex+1):''}`:'Transparent · '+source;
  if(!filling||isOriginal||fillQueueRunning||fillApplying){clearFillHover();return;}
  if(hex===$('fillColor').value.toLowerCase()){clearFillHover();$('fillHoverText').textContent='Diese Fläche hat bereits die gewählte Farbe.';return;}
  if(!ensureHoverPixels())return;
  if(hoverRegion?.rows.get(point.y)?.some(([left,right])=>point.x>=left&&point.x<=right)){paintFillHover();return;}
  if(hoverRequest?.generation===hoverGeneration&&hoverRequest.x===point.x&&hoverRequest.y===point.y)return;
  clearFillHover();hoverRequest={generation:hoverGeneration,x:point.x,y:point.y};
  const job=hoverJob;
  hoverTimer=setTimeout(()=>{hoverWorker?.postMessage({type:'region',generation:hoverGeneration,job,x:point.x,y:point.y});},70);
 }catch{clearFillHover();$('mouseColor').hidden=true;}
}
$('imageStack').addEventListener('pointermove',updateMouseInfo);
$('imageStack').addEventListener('pointerleave',resetMouseInfo);
function clearLocalization(restore=true){
 const previous=locatePreviousView;locatedColor=null;locatePreviousView=null;$('colorOverlay').hidden=true;
 if(restore&&previous!==null){view=previous;applyView();}imageToolState();
}
function renderLocalization(){
 if(!locatedColor)return;const image=$('processed');if(!image.complete||!image.naturalWidth)return;
 try{const canvas=$('colorOverlay');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);const data=ctx.getImageData(0,0,canvas.width,canvas.height);data.data.set(ColorTools.mask(data.data,locatedColor,$('indicatorColor').value));ctx.putImageData(data,0,0);canvas.hidden=false;imageToolState();}catch{clearLocalization();toast('Die Farbe konnte nicht markiert werden. Vorschau erneut laden.');}
}
function locateColor(color){
 filling=false;stopBrush();stopPicking();mergeMode=false;mergeTarget=null;if(locatedColor===color){clearLocalization();return;}
 if(locatePreviousView===null)locatePreviousView=view;locatedColor=color;view='result';applyView();renderLocalization();$('stage').scrollIntoView({block:'center',behavior:'instant'});
}
function takeBackground(color){$('background').value=color;stopPicking();invalidate();toast('Hintergrundfarbe '+color.toUpperCase()+' aufgenommen.');}
$('pickBackground').onclick=()=>{filling=false;stopBrush();if(pickingBackground){stopPicking();return;}clearLocalization();mergeMode=false;mergeTarget=null;pickingBackground=true;imageToolState();$('stage').scrollIntoView({block:'center',behavior:'instant'});};
$('fillButton').onclick=()=>{const next=!filling;stopBrush();stopPicking();clearLocalization();mergeMode=false;mergeTarget=null;filling=next;if(next){view='result';applyView();}imageToolState();};
$('moreFillColors').onclick=()=>{const opening=$('extraFillColors').hidden;$('extraFillColors').hidden=!opening;$('moreFillColors').setAttribute('aria-expanded',String(opening));};
$('fillColor').oninput=()=>{fillColorChosen=true;renderFillColors();buttons();};
function cancelStroke(){
 if(stroke&&$('imageStack').hasPointerCapture?.(stroke.pointerId))$('imageStack').releasePointerCapture(stroke.pointerId);
 stroke=null;drawBrushPreview();$('brushCursor').hidden=true;
}
function stopBrush(){painting=false;cancelStroke();$('imageStack').classList.remove('painting');}
function brushPoint(e){
 const image=$('processed'),width=previewPixels?.width||image.naturalWidth,height=previewPixels?.height||image.naturalHeight;
 const point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),width,height);
 return point?[(point.x+.5)/width,(point.y+.5)/height]:null;
}
function showBrushCursor(e){
 const point=brushPoint(e),image=$('processed'),rect=image.getBoundingClientRect(),cursor=$('brushCursor');
 cursor.hidden=!painting||!point;
 if(cursor.hidden)return;
 const width=previewPixels?.width||image.naturalWidth,height=previewPixels?.height||image.naturalHeight;
 const diameter=Number($('brushSize').value)/100*Math.min(width,height)*rect.width/width;
 cursor.style.width=diameter+'px';cursor.style.height=diameter+'px';cursor.style.left=point[0]*100+'%';cursor.style.top=point[1]*100+'%';
}
function updateBrushMask(){
 const image=$('processed');if(!image.complete||!image.naturalWidth)return;
 brushMask.width=image.naturalWidth;brushMask.height=image.naturalHeight;brushMask.getContext('2d').drawImage(image,0,0);
}
function drawBrushPreview(){
 const edits=stroke?[...pendingBrushes,stroke]:pendingBrushes,canvas=$('brushPreview');
 if(!edits.length||!brushMask.width||!previewPixels){canvas.hidden=true;return;}
 canvas.width=previewPixels.width;canvas.height=previewPixels.height;
 const ctx=canvas.getContext('2d');ctx.lineCap=ctx.lineJoin='round';
 for(const edit of edits){
  const points=edit.points,diameter=edit.size*Math.min(canvas.width,canvas.height);
  ctx.strokeStyle=ctx.fillStyle=edit.color;ctx.lineWidth=diameter;
  ctx.beginPath();ctx.moveTo(points[0][0]*canvas.width,points[0][1]*canvas.height);
  for(const [x,y] of points.slice(1))ctx.lineTo(x*canvas.width,y*canvas.height);
  ctx.stroke();ctx.beginPath();ctx.arc(points[0][0]*canvas.width,points[0][1]*canvas.height,diameter/2,0,Math.PI*2);ctx.fill();
 }
 ctx.globalCompositeOperation='destination-in';ctx.drawImage(brushMask,0,0);canvas.hidden=false;
}
function usedBrushPoints(){return [...fillEdits,...fillQueue.map(item=>item.edit)].reduce((sum,f)=>sum+(f.type==='brush'?f.points.length:0),0);}
function appendBrushPoint(e){
 const used=usedBrushPoints();
 const point=brushPoint(e);if(!point||!stroke||stroke.points.length>=Math.min(2000,20000-used))return;
 const last=stroke.points.at(-1),width=previewPixels.width,height=previewPixels.height;
 if(last&&Math.hypot((point[0]-last[0])*width,(point[1]-last[1])*height)<Math.max(.5,stroke.size*Math.min(width,height)/8))return;
 stroke.points.push(point);drawBrushPreview();
}
$('brushButton').onclick=()=>{const next=!painting;stopBrush();filling=false;stopPicking();clearLocalization();mergeMode=false;mergeTarget=null;painting=next;if(next){updateBrushMask();view='result';applyView();}imageToolState();};
$('brushSize').oninput=()=>{$('brushSizeOut').value=Number($('brushSize').value).toLocaleString('de-DE')+' %';$('brushCursor').hidden=true;};
$('resetBrush').onclick=()=>{paletteHistory.push(snapshot());stopBrush();fillEdits=fillEdits.filter(f=>f.type!=='brush');invalidate(true,true);preview({silent:true});};
$('editPanel').addEventListener('toggle',()=>{if(!$('editPanel').open){filling=false;stopBrush();imageToolState();}});
$('imageStack').addEventListener('pointerdown',e=>{
 if(!painting||stroke||e.button!==0||uploading||exporting||$('canvas').hidden)return;
 const point=brushPoint(e);if(!point)return;
 if(fillEdits.length+fillQueue.length>=100){toast('Höchstens 100 Füllungen und Pinselstriche pro Motiv.');return;}
 if(usedBrushPoints()>=20000){toast('Zu viele Pinselpunkte. Bitte einige Striche zurücknehmen.');return;}
 e.preventDefault();stroke={type:'brush',points:[point],size:Number($('brushSize').value)/100,color:$('fillColor').value.toLowerCase(),pointerId:e.pointerId};
 $('imageStack').setPointerCapture(e.pointerId);drawBrushPreview();showBrushCursor(e);buttons();
});
$('imageStack').addEventListener('pointermove',e=>{if(!painting)return;showBrushCursor(e);if(stroke?.pointerId===e.pointerId){e.preventDefault();appendBrushPoint(e);}});
$('imageStack').addEventListener('pointerleave',()=>{$('brushCursor').hidden=true;});
$('imageStack').addEventListener('pointercancel',()=>{cancelStroke();buttons();});
$('imageStack').addEventListener('pointerup',async e=>{
 if(!stroke||stroke.pointerId!==e.pointerId)return;
 appendBrushPoint(e);const {pointerId,...edit}=stroke;stroke=null;
 if($('imageStack').hasPointerCapture(pointerId))$('imageStack').releasePointerCapture(pointerId);
 showBrushCursor(e);
 await queueManualEdit(edit);buttons();
});
$('resetFills').onclick=()=>{paletteHistory.push(snapshot());fillEdits=fillEdits.filter(f=>f.type==='brush');invalidate(true,true);preview({silent:true});};
async function fillAt(e){
 if(!filling||!current||uploading||exporting||$('canvas').hidden)return;
 if(!fillQueueRunning&&JSON.stringify(renderedSettings)!==JSON.stringify(values()))return;
 const image=$('processed'),width=previewPixels?.width||image.naturalWidth,height=previewPixels?.height||image.naturalHeight;
 const point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),width,height);
 if(!point)return;
 if(fillEdits.length+fillQueue.length>=100){toast('Höchstens 100 Füllungen und Pinselstriche pro Motiv.');return;}
 return queueManualEdit({x:(point.x+.5)/width,y:(point.y+.5)/height,color:$('fillColor').value.toLowerCase()});
}
async function queueManualEdit(edit){
 if(fillEdits.length+fillQueue.length>=100){toast('Höchstens 100 Füllungen und Pinselstriche pro Motiv.');return;}
 if(edit.type==='brush'){pendingBrushes.push(edit);drawBrushPreview();}
 fillQueue.push({id:current.id,revision:editRevision,edit});
 if(fillQueueRunning)return;
 fillQueueRunning=true;buttons();
 try{
  while(fillQueue.length){
   const next=fillQueue.shift();if(next.id!==current?.id||next.revision!==editRevision)continue;
   activeManualType=next.edit.type||'fill';buttons();
   const applied=await applyManualEdit(next.edit);
   if(!applied&&next.id===current?.id&&next.revision===editRevision){fillQueue=[];pendingBrushes=[];drawBrushPreview();break;}
  }
 }finally{activeManualType=null;fillQueueRunning=false;buttons();}
}
async function applyManualEdit(edit){
 if(fillApplying||fillEdits.length>=100){toast('Höchstens 100 Füllungen und Pinselstriche pro Motiv.');return;}
 const previous=snapshot(),next=[...fillEdits,edit];
 paletteEdit=paletteEdit||{base:[...paletteBase],map:{}};fillEdits=next;fillApplying=true;buttons();
 const applied=await preview({silent:true});fillApplying=false;
 if(fillEdits===next){if(applied){paletteHistory.push(previous);}else{paletteEdit=previous.edit;fillEdits=previous.fills;await preview({silent:true});}}
 buttons();
 return applied===true&&fillEdits===next;
}
$('imageStack').onclick=e=>{
 if(painting)return;
 if(filling){fillAt(e);return;}if(!pickingBackground)return;const result=$('processed'),bounds=result.getBoundingClientRect();
 const original=view==='original'||(view==='compare'&&e.clientX<bounds.left+bounds.width*Number($('compare').value)/100);
 const image=original?$('original'):result,point=ColorTools.point(e.clientX,e.clientY,image.getBoundingClientRect(),image.naturalWidth,image.naturalHeight);
 if(!point)return;
 try{const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.imageSmoothingEnabled=false;ctx.drawImage(image,point.x,point.y,1,1,0,0,1,1);const color=ColorTools.hex(ctx.getImageData(0,0,1,1).data);if(!color){toast('Dieser Bildpunkt ist transparent. Bitte eine sichtbare Farbe auswählen.');return;}takeBackground(color);}catch{toast('Farbe konnte nicht aufgenommen werden. Bitte einen Paletteneintrag wählen.');}
};
for(const id of ['original','processed'])$(id).addEventListener('load',()=>{if(id==='processed'){updateBrushMask();pendingBrushes=pendingBrushes.filter(edit=>!renderedImageEdits.includes(edit));drawBrushPreview();refreshHoverImage();applyZoom();renderLocalization();}buttons();});
$('indicatorColor').oninput=renderLocalization;
$('clearLocate').onclick=()=>clearLocalization();
$('stopImageTool').onclick=()=>{filling=false;stopBrush();stopPicking();clearLocalization();};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){filling=false;stopBrush();stopPicking();clearLocalization();}});
async function preview(options={}){
 clearTimeout(debounce);if(!current||!valid())return;
 previewController?.abort();
 const controller=new AbortController();previewController=controller;
 const n=++requestNo, s=values(), id=current.id;
 $('busy').hidden=options.silent===true||painting||filling||fillApplying;
 try{
  const result=await(await api('/api/preview',{id,settings:s},controller.signal)).json();
  if(n!==requestNo||current?.id!==id)return false;
  if(typeof Image!=='undefined'){const decoded=new Image();decoded.src=result.image;await decoded.decode();}
  if(n!==requestNo||current?.id!==id)return false;
  renderedImageEdits=s.fill_edits;
  $('processed').src=result.image;$('canvas').hidden=false;$('empty').hidden=true;
  renderedSettings=s;stats(result.stats);applyView();return true;
 }catch(error){if(n===requestNo&&error.name!=='AbortError')toast(error.message);}finally{if(n===requestNo){$('busy').hidden=true;buttons();}if(previewController===controller)previewController=null;}
}
function stats(s){
 previewPixels={width:s.width_px,height:s.height_px};
 $('colorCount').textContent=s.colors;
 $('dimensions').textContent=`${s.width_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} × ${s.height_mm.toLocaleString('de-DE',{maximumFractionDigits:1})} mm`;
 $('pixelSize').textContent=s.width_px+' × '+s.height_px+' px';
 paletteBase=s.base_palette;paletteColors=s.palette;$('paletteTools').hidden=false;$('paletteHint').hidden=false;renderPalette();
 $('notices').replaceChildren();for(const notice of s.notices){const p=document.createElement('p');p.textContent=notice;$('notices').append(p);}
}
function openProject(p){
 resetMouseInfo();hoverPixels=null;hoverGeneration++;
 previewPixels=null;
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
for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>{filling=false;stopBrush();clearLocalization(false);view=button.dataset.view;applyView();};
function chooseMode(next){
 mode=next;for(const b of document.querySelectorAll('[data-mode]')){b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-pressed',String(b.dataset.mode===mode));}
 $('modeHint').textContent=mode==='logo'?'Behutsame Vorgabe für Formen und Schrift. Alle Änderungen im Vergleich prüfen.':'Weniger Kleinstflächen und ruhigere Konturen. Wichtige Motivdetails im Vergleich prüfen.';
}
for(const button of document.querySelectorAll('[data-mode]'))button.onclick=()=>{
 chooseMode(button.dataset.mode);
 setValues({...defaults,short_side_mm:values().short_side_mm,colors:values().colors,color_space:values().color_space,...(mode==='illustration'?{smooth:1,detail_mm:0.3}: {})});invalidate();
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
 if(!current||!valid()||exporting||fillApplying||fillQueueRunning||stroke)return;
 exporting=true;buttons();const s=values(),id=current.id;
 try{
  const blob=await(await api('/api/export',{id,settings:s})).blob();
  const link=document.createElement('a'), url=URL.createObjectURL(blob);link.href=url;link.download='stickatelier-motiv.png';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  toast('Vorlage exportiert. Zielgröße anschließend in Creator 9 prüfen.');
 }catch(error){toast(error.message);}finally{exporting=false;buttons();}
};
labels();applyView();recent();
