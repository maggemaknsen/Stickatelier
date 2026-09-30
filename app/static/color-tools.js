'use strict';
// Pure pixel helpers shared by the image picker and the display-only overlay.
const ColorTools={
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
