'use strict';
importScripts('/color-tools.js?v=hover-tools-6');
let pixels=null,width=0,height=0,generation=0,cached=null;
self.onmessage=event=>{
 const message=event.data;
 if(message.type==='image'){pixels=new Uint8ClampedArray(message.pixels);width=message.width;height=message.height;generation=message.generation;cached=null;return;}
 if(!pixels||message.generation!==generation||message.x<0||message.y<0||message.x>=width||message.y>=height)return;
 if(!cached||!cached.visited[message.y*width+message.x])cached=ColorTools.region(pixels,width,height,message.x,message.y);
 const runs=new Uint32Array(cached.runs);
 self.postMessage({generation,job:message.job,count:cached.count,runs:runs.buffer},[runs.buffer]);
};
