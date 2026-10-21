const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8');
const zoomFunction=source.slice(source.indexOf('function applyZoom('),source.indexOf('function setZoom('));

function fixture(){
 let writes=0;
 const style=()=>new Proxy({}, {set(target,key,value){writes++;target[key]=value;return true;}});
 const nodes={canvas:{hidden:false,clientWidth:1068,clientHeight:350,scrollLeft:0,scrollTop:0,style:style()},
  zoomSurface:{offsetWidth:1085,offsetHeight:366,style:style()},
  imageStack:{style:style()},processed:{naturalWidth:640,naturalHeight:1000},zoomLevel:{}};
 const context=vm.createContext({current:{id:'test'},zoom:1,zoomLayoutKey:'',$:id=>nodes[id],
  getComputedStyle:()=>({width:'1085.25px',height:'366.4px'})});
 vm.runInContext(zoomFunction,context);
 return {context,nodes,writes:()=>writes};
}

test('fit size uses allocated box rather than scrollbar-dependent client size',()=>{
 const {context,nodes}=fixture();context.applyZoom();
 assert.equal(nodes.canvas.style.overflow,'hidden');
 assert.equal(nodes.zoomSurface.style.width,'1085px');
 assert.equal(nodes.zoomSurface.style.height,'366px');
 assert.equal(Number.parseFloat(nodes.imageStack.style.height),326);
});

test('repeat layout notifications preserve scroll and avoid layout writes',()=>{
 const {context,nodes,writes}=fixture();context.zoom=3;context.applyZoom();
 nodes.canvas.scrollLeft=87;nodes.canvas.scrollTop=123;
 const firstWrites=writes();
 for(let i=0;i<100;i++){
  nodes.canvas.clientWidth=i%2?1085:1068;nodes.canvas.clientHeight=i%2?366:350;context.applyZoom();
 }
 assert.equal(writes(),firstWrites);assert.equal(nodes.canvas.scrollLeft,87);assert.equal(nodes.canvas.scrollTop,123);
});

test('zoom and reset still update size and overflow mode',()=>{
 const {context,nodes}=fixture();context.applyZoom();context.zoom=2;context.applyZoom();
 assert.equal(nodes.canvas.style.overflow,'auto');
 assert.equal(Number.parseFloat(nodes.imageStack.style.height),652);
 context.zoom=1;context.applyZoom(true);
 assert.equal(nodes.canvas.style.overflow,'hidden');assert.equal(Number.parseFloat(nodes.imageStack.style.height),326);
});

test('resize observation is attached to stage rather than scrollable canvas',()=>{
 assert.match(source,/ResizeObserver\([^\n]+\.observe\(\$\('stage'\)\)/);
 assert.doesNotMatch(source,/ResizeObserver\([^\n]+\.observe\(\$\('canvas'\)\)/);
});
