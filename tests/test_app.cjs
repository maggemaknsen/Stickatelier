const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('app starts against its HTML and loads a motif without workshop calls', async () => {
  const directory = path.join(__dirname, '../app/static');
  const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
  const nodes = new Map();
  const node = () => ({value:'', checked:false, hidden:false, disabled:false, complete:true,
    naturalWidth:160,naturalHeight:80,getBoundingClientRect(){return {left:0,top:0,width:160,height:80};},
    classList:{add(){},remove(){},toggle(){}}, style:{}, dataset:{},
    setAttribute(){},setCustomValidity(){},removeAttribute(){},addEventListener(){},
    querySelectorAll(){return [];},replaceChildren(){},append(){},close(){},click(){},remove(){}});
  for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
    const element = node();
    element.value = /\bvalue="([^"]*)"/.exec(match[0])?.[1] || '';
    element.checked = /\bchecked\b/.test(match[0]);
    nodes.set(match[1], element);
  }
  const requested = [];
  const bodies = [];
  const downloads = [];
  let rejectPreview=false;
  const project = {id:'a'.repeat(32),name:'Testmotiv',width:160,height:80};
  const context = vm.createContext({
    document:{
      getElementById(id){assert.ok(nodes.has(id), `Missing element: ${id}`); return nodes.get(id);},
      querySelectorAll(){return [];}, addEventListener(){}, body:{append(){}},
      createElement(tag){const element=node();if(tag==='a')downloads.push(element);return element;},
    },
    fetch:async (url, options) => {
      requested.push(url);
      if(options?.body)bodies.push({url,data:JSON.parse(options.body)});
      if(rejectPreview&&url==='/api/preview'){
        rejectPreview=false;
        return {status:400,ok:false,json:async()=>({error:'Farbgrenze überschritten'})};
      }
      const data = url === '/api/projects' ? [] : url === '/api/demo' ? project : {
        image:'data:image/png;base64,',
        stats:{colors:1,settings:JSON.parse(options.body).settings,width_mm:100,height_mm:50,
          width_px:160,height_px:80,base_palette:['#ffffff'],palette:[],notices:[]},
      };
      return {status:200,ok:true,json:async()=>data,blob:async()=>Buffer.from('PNG')};
    },
    AbortController, setTimeout(){return 0;}, clearTimeout(){},
    ColorTools:require('../app/static/color-tools.js'),
    URL:{createObjectURL(){return 'blob:test';},revokeObjectURL(){}},
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'app.js'), 'utf8'), context);
  assert.equal(nodes.get('exportButton').disabled, true);
  await context.loadDemo();
  await context.preview();
  assert.equal(nodes.get('filename').textContent, 'Testmotiv');
  assert.equal(nodes.get('exportButton').disabled, false);
  nodes.get('short_side_mm').value='130';
  context.labels();
  assert.equal(nodes.get('dimensions').textContent,'260 × 130 mm');
  assert.equal(nodes.get('frameWarning').hidden,true);
  nodes.get('short_side_mm').value='160';
  context.labels();
  assert.equal(nodes.get('dimensions').textContent,'320 × 160 mm');
  assert.equal(nodes.get('frameWarning').hidden,false);
  nodes.get('short_side_mm').value='180';
  context.labels();
  assert.equal(context.valid(),true);
  assert.equal(nodes.get('frameWarning').hidden,false);
  await context.preview();
  assert.equal(nodes.get('exportButton').disabled,false);
  nodes.get('fillButton').onclick();
  await context.fillAt({clientX:20,clientY:30});
  const fillRequest=bodies.filter(item=>item.url==='/api/preview').at(-1);
  assert.equal(fillRequest.data.settings.fill_edits.length,1);
  assert.equal(fillRequest.data.settings.fill_edits[0].color,'#e87436');
  assert.equal(nodes.get('undoPalette').disabled,false);
  nodes.get('undoPalette').onclick();
  await context.preview();
  assert.equal(bodies.filter(item=>item.url==='/api/preview').at(-1).data.settings.fill_edits.length,0);
  rejectPreview=true;
  await context.fillAt({clientX:20,clientY:30});
  assert.equal(bodies.filter(item=>item.url==='/api/preview').at(-1).data.settings.fill_edits.length,0);
  assert.equal(nodes.get('exportButton').disabled,false);
  await nodes.get('exportButton').onclick();
  assert.equal(downloads.at(-1).download,'stickatelier-motiv.png');
  assert.ok(requested.includes('/api/preview'));
  assert.ok(requested.every(url => !url.startsWith('/api/ai/')));
  for (const id of ['aiWorkbench', 'openAI', 'accountButton', 'accountDialog']) {
    assert.equal(nodes.has(id), false);
  }
});
