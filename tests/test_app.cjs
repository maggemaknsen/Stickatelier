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
    classList:{add(){},remove(){},toggle(){}}, style:{}, dataset:{},
    setAttribute(){},setCustomValidity(){},removeAttribute(){},addEventListener(){},
    querySelectorAll(){return [];},replaceChildren(){},append(){},close(){}});
  for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
    const element = node();
    element.value = /\bvalue="([^"]*)"/.exec(match[0])?.[1] || '';
    element.checked = /\bchecked\b/.test(match[0]);
    nodes.set(match[1], element);
  }
  const requested = [];
  const project = {id:'a'.repeat(32),name:'Testmotiv',width:160,height:80};
  const context = vm.createContext({
    document:{
      getElementById(id){assert.ok(nodes.has(id), `Missing element: ${id}`); return nodes.get(id);},
      querySelectorAll(){return [];}, addEventListener(){}, createElement:node,
    },
    fetch:async (url, options) => {
      requested.push(url);
      const data = url === '/api/projects' ? [] : url === '/api/demo' ? project : {
        image:'data:image/png;base64,',
        stats:{colors:1,settings:JSON.parse(options.body).settings,width_mm:100,height_mm:50,
          width_px:160,height_px:80,base_palette:['#ffffff'],palette:[],notices:[]},
      };
      return {status:200,ok:true,json:async()=>data};
    },
    AbortController, setTimeout, clearTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(directory, 'app.js'), 'utf8'), context);
  assert.equal(nodes.get('exportButton').disabled, true);
  await context.loadDemo();
  await context.preview();
  assert.equal(nodes.get('filename').textContent, 'Testmotiv');
  assert.equal(nodes.get('exportButton').disabled, false);
  assert.ok(requested.includes('/api/preview'));
  assert.ok(requested.every(url => !url.startsWith('/api/ai/')));
  for (const id of ['aiWorkbench', 'openAI', 'accountButton', 'accountDialog']) {
    assert.equal(nodes.has(id), false);
  }
});
