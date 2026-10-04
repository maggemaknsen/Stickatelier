'use strict';
// Pure pixel helpers shared by the image picker and the display-only overlay.
const ColorTools={
 region(pixels,width,height,x,y){
  const visited=new Uint8Array(width*height),runs=[];let count=0;
  const seed=(y*width+x)*4,transparent=pixels[seed+3]===0;
  const matches=i=>!visited[i]&&(transparent?pixels[i*4+3]===0:pixels[i*4+3]>0&&pixels[i*4]===pixels[seed]&&pixels[i*4+1]===pixels[seed+1]&&pixels[i*4+2]===pixels[seed+2]);
  const pending=[y*width+x];
  while(pending.length){
   const i=pending.pop();if(!matches(i))continue;
   const row=Math.floor(i/width),start=row*width;let left=i%width,right=left;
   while(left>0&&matches(start+left-1))left--;
   while(right+1<width&&matches(start+right+1))right++;
   visited.fill(1,start+left,start+right+1);runs.push(row,left,right);count+=right-left+1;
   for(const next of [row-1,row+1])if(next>=0&&next<height){let inside=false;for(let col=left;col<=right;col++){const match=matches(next*width+col);if(match&&!inside)pending.push(next*width+col);inside=match;}}
  }
  return {visited,runs,count};
 },
 point(x,y,rect,width,height){
  if(width<=0||height<=0||rect.width<=0||rect.height<=0)return null;
  const scale=Math.min(rect.width/width,rect.height/height),w=width*scale,h=height*scale;
  const u=(x-rect.left-(rect.width-w)/2)/w,v=(y-rect.top-(rect.height-h)/2)/h;
  return u>=0&&u<1&&v>=0&&v<1?{x:Math.floor(u*width),y:Math.floor(v*height)}:null;
 },
 hex(pixel){return pixel[3]===0?null:'#'+Array.from(pixel).slice(0,3).map(v=>v.toString(16).padStart(2,'0')).join('');},
 mask(pixels,hex,indicator){
  const target=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)),tint=[1,3,5].map(i=>parseInt(indicator.slice(i,i+2),16));
  const mask=new Uint8ClampedArray(pixels.length);
  for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>0&&target.every((v,c)=>pixels[i+c]===v)){mask.set(tint,i);mask[i+3]=255;}
  return mask;
 }
};
if(typeof module!=='undefined'&&module.exports)module.exports=ColorTools;
