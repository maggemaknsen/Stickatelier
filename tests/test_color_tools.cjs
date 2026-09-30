const test=require('node:test');
const assert=require('node:assert/strict');
const tools=require('../app/static/color-tools.js');

test('pixel positions follow resized images and ignore letterboxing',()=>{
 const bounds={left:100,top:50,width:300,height:300};
 assert.deepEqual(tools.point(250,200,bounds,600,300),{x:300,y:150});
 assert.deepEqual(tools.point(100,125,bounds,600,300),{x:0,y:0});
 assert.equal(tools.point(250,100,bounds,600,300),null);
 assert.equal(tools.point(400,200,bounds,600,300),null);
 assert.equal(tools.point(250,275,bounds,600,300),null);
 assert.equal(tools.point(0,0,bounds,0,0),null);
});
test('portrait sampling accounts for horizontal padding and last pixel',()=>{
 const bounds={left:0,top:0,width:300,height:300};
 assert.deepEqual(tools.point(150,150,bounds,100,200),{x:50,y:100});
 assert.equal(tools.point(50,150,bounds,100,200),null);
 assert.deepEqual(tools.point(224.9,299.9,bounds,100,200),{x:99,y:199});
});
test('transparent pixels are rejected instead of sampling hidden RGB',()=>{
 assert.equal(tools.hex(new Uint8ClampedArray([233,145,105,0])),null);
 assert.equal(tools.hex(new Uint8ClampedArray([233,145,105,255])),'#e99169');
 assert.equal(tools.hex(new Uint8ClampedArray([0,1,15,128])),'#00010f');
});
test('indicator targets exact visible colors and never changes source pixels',()=>{
 const pixels=new Uint8ClampedArray([233,145,105,255, 233,145,105,0, 233,145,104,255, 233,145,105,128, 96,32,160,255]);
 const saved=new Uint8ClampedArray(pixels);
 const marked=tools.mask(pixels,'#E99169','#00ff00');
 assert.deepEqual(Array.from(marked),[0,255,0,255, 0,0,0,0, 0,0,0,0, 0,255,0,255, 0,0,0,0]);
 assert.deepEqual(pixels,saved);
 const next=tools.mask(pixels,'#6020a0','#ff00c8');
 assert.deepEqual(Array.from(next.slice(16)),[255,0,200,255]);
 assert.ok(next.slice(0,16).every(value=>value===0));
});
