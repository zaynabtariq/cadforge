import * as THREE from 'three';
import { STLExporter } from 'three/addons/exporters/STLExporter.js';
import { mountViewer } from './viewer.js';

// A local, authored sample for the theme study; no CAD agent or provider calls.
function roundedPlate(width, height, radius, holes) {
  const s = new THREE.Shape();
  s.moveTo(radius, 0); s.lineTo(width-radius,0); s.quadraticCurveTo(width,0,width,radius);
  s.lineTo(width,height-radius); s.quadraticCurveTo(width,height,width-radius,height);
  s.lineTo(radius,height); s.quadraticCurveTo(0,height,0,height-radius);
  s.lineTo(0,radius); s.quadraticCurveTo(0,0,radius,0);
  for(const [x,y,r] of holes){const hole=new THREE.Path();hole.absarc(x,y,r,0,Math.PI*2,true);s.holes.push(hole);}
  return new THREE.ExtrudeGeometry(s,{depth:4,bevelEnabled:false,curveSegments:32});
}
const sample = new THREE.Group();
sample.add(new THREE.Mesh(roundedPlate(60,45,5,[[10,12,2.5],[50,12,2.5],[10,33,2.5],[50,33,2.5]])));
const upright=new THREE.Mesh(roundedPlate(60,40,5,[[17,24,4],[43,24,4]]));
upright.rotation.x=Math.PI/2;upright.position.y=45;sample.add(upright);sample.updateMatrixWorld(true);
const bytes=new STLExporter().parse(sample,{binary:true});
let view, wire=false;
const controls=[...document.querySelectorAll('.tool-button')];controls.forEach(b=>b.disabled=true);
try {
  view=await mountViewer(document.getElementById('study-viewer'),new File([bytes],'desk-bracket.stl'),info=>{
    document.getElementById('study-dimensions').textContent=info.dimensions_mm.map(n=>Math.round(n)).join(' × ')+' mm';
  });
  controls.forEach(b=>b.disabled=false);
} catch(error) {document.getElementById('study-viewer').textContent='Sample preview unavailable: '+error.message;}
function setWire(next){if(!view||next===wire)return;wire=view.wireframe();document.getElementById('study-wire').setAttribute('aria-pressed',String(wire));document.getElementById('study-solid').setAttribute('aria-pressed',String(!wire));}
document.getElementById('study-wire').onclick=()=>setWire(true);
document.getElementById('study-solid').onclick=()=>setWire(false);
document.getElementById('study-reset').onclick=()=>view?.reset();
function stage(next){
  if(!['landing','build','quote'].includes(next))next='landing';
  document.body.dataset.stage=next;
  document.querySelectorAll('[data-show]').forEach(e=>e.hidden=!e.dataset.show.split(' ').includes(next));
  document.querySelectorAll('[data-stage-button]').forEach(e=>{if(e.dataset.stageButton===next)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');});
  document.getElementById('inspector-title').textContent=next==='quote'?'Prepare your quote':'Build with your agent';
  document.getElementById('stage-caption').textContent={landing:'01 / START WITH POSSIBILITY',build:'02 / SHAPE IT TOGETHER',quote:'03 / BRING IT INTO THE WORLD'}[next];
  history.replaceState(null,'','#'+next);
}
document.querySelectorAll('[data-stage-button],[data-go]').forEach(e=>e.onclick=()=>stage(e.dataset.stageButton||e.dataset.go));
stage(location.hash.slice(1));
sample.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});
window.addEventListener('pagehide',()=>view?.dispose());
