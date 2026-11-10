import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// Smoke-test the actual browser inline JS without downloading any library holdings.
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(x=>x[1]);
const js=scripts.find(x=>x.includes("const DATA = ["));
assert.ok(js,'App inline script is present');
new vm.Script(js,{filename:'index.html'});
assert.match(html,/data-tab="available"/);
assert.match(html,/data-tab="discover"/);
assert.match(html,/data-tab="history"/);
assert.match(html,/id="refreshDiscover"/);
assert.match(html,/id="progressSummary"/);
assert.doesNotMatch(html,/data-tab="queue"/);
assert.doesNotMatch(html,/查現在可借/);

const handlers=new Map();
const elements=new Map();
function element(id){
  if(!elements.has(id)){
    elements.set(id,{
      id,innerHTML:'',textContent:'',value:'',hidden:false,disabled:false,
      classList:{toggle(){},add(){},remove(){}},
      addEventListener(event,fn){handlers.set(id+':'+event,fn)},
      scrollIntoView(){},click(){}
    });
  }
  return elements.get(id);
}
const storage=new Map();
const context=vm.createContext({
  console,Date,URL,Math,parseInt,JSON,
  localStorage:{
    getItem(k){return storage.get(k)??null},
    setItem(k,v){storage.set(k,v)}
  },
  document:{
    getElementById:element,
    querySelectorAll(){return []},
    addEventListener(){}
  },
  fetch:async()=>({ok:false,status:404}),
  alert(){throw Error('Unexpected alert during test')},
});
vm.runInContext(js,context,{filename:'index.html'});
assert.match(element('cards').innerHTML,/bookcard/,'Default list shows real known books');
assert.match(element('resultCount').textContent,/非即時館藏/);
assert.match(element('progressSummary').textContent,/已挖掘 0 本/);

vm.runInContext("state.tab='discover';render()",context);
const first=element('cards').innerHTML;
assert.match(first,/推薦你看看這本/);
assert.equal(element('refreshDiscover').hidden,false);
assert.ok(handlers.has('refreshDiscover:click'));
handlers.get('refreshDiscover:click')();
const next=element('cards').innerHTML;
assert.notEqual(first,next,'Try another set changes the suggested books');

vm.runInContext("state.tab='history';render()",context);
assert.match(element('cards').innerHTML,/尚未建立查詢紀錄/);
vm.runInContext("progress['9789865664817']='wish';state.tab='saved';render()",context);
assert.match(element('cards').innerHTML,/米爺爺學認字/);
assert.match(element('progressSummary').textContent,/想讀 1 本/);
assert.equal(element('refreshDiscover').hidden,true);

console.log('PASS: V3 frontend syntax, daily discover, refresh, saved list, history, and no-live-claims smoke tests');