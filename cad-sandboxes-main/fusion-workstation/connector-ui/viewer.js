import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {STLLoader} from './vendor/STLLoader.js';
const $=id=>document.getElementById(id),host=$('viewport');
const theme=getComputedStyle(document.documentElement),color=name=>theme.getPropertyValue(name).trim();
const initial=new URLSearchParams(location.search).get('workstation');$('target').value=['primary','fresh'].includes(initial)?initial:'fresh';
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label','Model preview. Drag to orbit, scroll to zoom, F to fit.');host.append(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(color('--scene-background'));
const camera=new THREE.PerspectiveCamera(38,1,.01,10000);camera.up.set(0,0,1);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.09;
scene.add(new THREE.HemisphereLight(0xffffff,0x888888,2.6));
const key=new THREE.DirectionalLight(0xffffff,3.3);key.castShadow=true;key.shadow.mapSize.set(1024,1024);key.shadow.normalBias=.04;scene.add(key);scene.add(key.target);
const rim=new THREE.DirectionalLight(0xffffff,1.5);scene.add(rim);
const material=new THREE.MeshStandardMaterial({color:color('--scene-model'),metalness:.08,roughness:.55,side:THREE.DoubleSide});
const highlightMaterial=material.clone();highlightMaterial.color.set('#4b8ce8');highlightMaterial.emissive.set('#163862');highlightMaterial.emissiveIntensity=.25;
const edgeMaterial=new THREE.LineBasicMaterial({color:color('--scene-edge'),transparent:true,opacity:.25});
const shadowMaterial=new THREE.ShadowMaterial({opacity:.12});
const loader=new STLLoader();let mesh,grid,ground,edges,bounds,frame=null,generation=0,polling=false,needsFit=true;
let assetAbort=null,parts=[],hoveredPart=null,focusedPart=null,selectedPart=null,highlightedPart=null,orbiting=false;
const partRows=new Map(),raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
function highlight(){
 const id=hoveredPart??focusedPart??selectedPart;highlightedPart=id;
 if(mesh)for(const group of mesh.geometry.groups)group.materialIndex=group.partId===id?1:0;
 for(const [partId,row] of partRows){row.classList.toggle('is-highlighted',partId===id);row.setAttribute('aria-pressed',String(partId===selectedPart));}
 if(window.viewerState)window.viewerState.highlightedPart=id;
}
function resetParts(){parts=[];hoveredPart=focusedPart=selectedPart=highlightedPart=null;partRows.clear();$('parts-list').replaceChildren();$('parts-panel').classList.add('hidden');}
function showParts(next){
 const hadFocus=document.activeElement?.dataset.partId,scrollTop=$('parts-list').scrollTop;
 parts=next.geometry.parts||[];
 // Old single-body frames remain useful until a new mapped capture arrives.
 if(!parts.length&&next.state.body_instance_count===1){const body=next.state.root_bodies?.[0]||next.state.occurrences?.find(o=>o.bodies.length)?.bodies[0];if(body)parts=[{id:'single-body',name:body.name,visible:true,path:'',triangle_start:0,triangle_count:next.geometry.triangles}];}
 const valid=id=>parts.some(p=>p.id===id&&p.triangle_count>0)?id:null;
 hoveredPart=null;focusedPart=valid(focusedPart);selectedPart=valid(selectedPart);
 partRows.clear();const fragment=document.createDocumentFragment();
 mesh?.geometry.clearGroups();
 for(const part of parts){
  const li=document.createElement('li'),row=document.createElement('button'),label=document.createElement('span'),name=document.createElement('span');
  row.type='button';row.className='part-row';row.dataset.partId=part.id;row.disabled=!part.triangle_count;row.title=[part.name,part.path].filter(Boolean).join(' · ');
  label.className='part-label';name.className='part-name';name.textContent=part.name||'Unnamed part';label.append(name);
  if(part.path){const path=document.createElement('span');path.className='part-path';path.textContent=part.path;label.append(path);}
  row.append(label);
  if(!part.visible){const hidden=document.createElement('span');hidden.className='part-hidden';hidden.textContent='Hidden';row.append(hidden);}
  row.onpointerenter=()=>{if(!row.disabled){hoveredPart=part.id;highlight();}};
  row.onpointerleave=()=>{hoveredPart=null;highlight();};
  row.onfocus=()=>{focusedPart=part.id;highlight();};row.onblur=()=>{focusedPart=null;highlight();};
  row.onclick=()=>{selectedPart=selectedPart===part.id?null:part.id;highlight();};
  li.append(row);fragment.append(li);partRows.set(part.id,row);
  if(mesh&&part.triangle_count){mesh.geometry.addGroup(part.triangle_start*3,part.triangle_count*3,0);mesh.geometry.groups.at(-1).partId=part.id;}
 }
 if(mesh&&!parts.length)mesh.geometry.addGroup(0,mesh.geometry.attributes.position.count,0);
 $('parts-list').replaceChildren(fragment);$('parts-list').scrollTop=scrollTop;$('parts-count').textContent=parts.length;$('parts-panel').classList.toggle('hidden',!parts.length);
 if(hadFocus&&partRows.has(hadFocus))partRows.get(hadFocus).focus({preventScroll:true});
 highlight();
}
controls.addEventListener('start',()=>{orbiting=true;hoveredPart=null;highlight();});
controls.addEventListener('end',()=>{orbiting=false;});
renderer.domElement.addEventListener('pointermove',event=>{
 if(orbiting||event.buttons||!mesh)return;
 const rect=renderer.domElement.getBoundingClientRect();pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
 raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObject(mesh,false)[0];
 const part=hit&&parts.find(p=>hit.faceIndex>=p.triangle_start&&hit.faceIndex<p.triangle_start+p.triangle_count);
 const id=part?.id??null;if(id!==hoveredPart){hoveredPart=id;highlight();}
});
renderer.domElement.addEventListener('pointerleave',()=>{hoveredPart=null;highlight();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){hoveredPart=focusedPart=selectedPart=null;document.activeElement?.blur();highlight();}});
function resize(){const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(host);resize();
const lastRotation=new THREE.Quaternion(),axisRotation=new THREE.Quaternion();
const axes=[['x',new THREE.Vector3(1,0,0)],['y',new THREE.Vector3(0,1,0)],['z',new THREE.Vector3(0,0,1)]];
function updateAxes(){if(lastRotation.equals(camera.quaternion))return;lastRotation.copy(camera.quaternion);axisRotation.copy(camera.quaternion).invert();for(const [name,vector] of axes){const point=vector.clone().applyQuaternion(axisRotation),group=document.querySelector(`[data-axis=${name}]`),line=group.querySelector('line'),label=group.querySelector('text');line.setAttribute('x2',24+point.x*15);line.setAttribute('y2',24-point.y*15);label.setAttribute('x',24+point.x*20);label.setAttribute('y',27-point.y*20);}}
renderer.setAnimationLoop(()=>{if(document.visibilityState==='visible'){controls.update();updateAxes();renderer.render(scene,camera)}});
function clearGeometry(){resetParts();if(mesh){scene.remove(mesh);mesh.geometry.dispose();edges?.geometry.dispose();mesh=null;edges=null}for(const item of [grid,ground])if(item){scene.remove(item);item.geometry.dispose();if(item===grid)item.material.dispose()}grid=ground=null;bounds=null;}
function fitModel(direction){if(!bounds)return;const center=bounds.getCenter(new THREE.Vector3()),radius=Math.max(bounds.getSize(new THREE.Vector3()).length()/2,.01);const vfov=THREE.MathUtils.degToRad(camera.fov),hfov=2*Math.atan(Math.tan(vfov/2)*camera.aspect),distance=radius/Math.sin(Math.min(vfov,hfov)/2)*(host.clientWidth<500?1.4:1.08);
 const ray=direction||camera.position.clone().sub(controls.target).normalize();if(ray.lengthSq()<.01)ray.set(1,-1,.9);controls.target.copy(center);camera.position.copy(center).add(ray.normalize().multiplyScalar(distance));camera.near=Math.max(radius/1000,.001);camera.far=radius*200;camera.updateProjectionMatrix();controls.minDistance=radius*.3;controls.maxDistance=radius*40;controls.update();}
function stageGeometry(geometry){clearGeometry();geometry.computeBoundingBox();bounds=geometry.boundingBox;mesh=new THREE.Mesh(geometry,[material,highlightMaterial]);mesh.castShadow=true;scene.add(mesh);
 if(geometry.attributes.position.count<450000){edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry,35),edgeMaterial);edges.visible=!material.wireframe;mesh.add(edges)}
 const size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3()),span=Math.max(size.x,size.y,size.z,.1);
 grid=new THREE.GridHelper(span*5,25,color('--scene-grid-major'),color('--scene-grid-minor'));grid.rotation.x=Math.PI/2;grid.position.set(center.x,center.y,bounds.min.z-.035);grid.material.transparent=true;grid.material.opacity=.5;grid.visible=$('grid').getAttribute('aria-pressed')==='true';scene.add(grid);
 ground=new THREE.Mesh(new THREE.PlaneGeometry(span*8,span*8),shadowMaterial);ground.position.set(center.x,center.y,bounds.min.z-.03);ground.receiveShadow=true;scene.add(ground);
 key.position.copy(center).add(new THREE.Vector3(span*.8,-span,span*2));key.target.position.copy(center);key.shadow.camera.left=-span*1.5;key.shadow.camera.right=span*1.5;key.shadow.camera.top=span*1.5;key.shadow.camera.bottom=-span*1.5;key.shadow.camera.near=.1;key.shadow.camera.far=span*8;key.shadow.camera.updateProjectionMatrix();rim.position.copy(center).add(new THREE.Vector3(-span,span,span));
 $('dimensions').textContent=[size.x,size.y,size.z].map(n=>Number(n.toFixed(2))).join(' × ')+' mm';
 if(needsFit){fitModel(new THREE.Vector3(1,-1,.9));needsFit=false;}
}
function api(path,target=$('target').value){return 'v1/workstations/'+target+'/'+path}
function error(message){$('viewer-stage').dataset.error='true';$('status').textContent=message;}
function describe(next){if(!next.geometry.triangles)$('dimensions').textContent='Millimeters';const n=next.state.body_instance_count;$('status').textContent=`${n} ${n===1?'body':'bodies'} · ${next.geometry.triangles.toLocaleString()} triangles`;$('revision-label').textContent=`Step ${next.version}`;
 const bodies=next.state.root_bodies||[];const name=bodies.length===1?(bodies[0].name||bodies[0].body_name):null;
 $('model-name').textContent=name||next.geometry.document||'Untitled model';$('viewer-stage').dataset.error='false';$('empty-state').classList.toggle('hidden',next.geometry.triangles>0);
 window.viewerState={version:next.version,triangles:next.geometry.triangles,workstation:$('target').value,dimensions:bounds?.getSize(new THREE.Vector3()).toArray(),wireframe:material.wireframe,partCount:next.geometry.parts?.length||0,highlightedPart:null};showParts(next);}
async function show(next,expected){
 if(!next||expected!==generation)return;
 if(frame?.connector_epoch===next.connector_epoch&&next.version<=frame.version)return;
 if(frame?.document_key!==next.document_key){needsFit=true;resetParts();}
 if(!mesh||frame?.geometry.sha256!==next.geometry.sha256){
  assetAbort?.abort();const abort=new AbortController();assetAbort=abort;
  const response=await fetch(next.asset_url,{signal:abort.signal});if(!response.ok)throw Error('Snapshot expired. Capture again.');
  const bytes=await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');if(hash!==next.geometry.sha256)throw Error('Snapshot integrity check failed.');
  if(expected!==generation)return;
  if(frame?.connector_epoch===next.connector_epoch&&next.version<=frame.version)return;
  const geometry=loader.parse(bytes);if(next.geometry.triangles){stageGeometry(geometry);}else{geometry.dispose();clearGeometry();}
 }
 if(expected!==generation)return;frame=next;describe(next);
}
async function poll(){if(polling)return;polling=true;const expected=generation;
 try{const response=await fetch(api('scene'));const data=await response.json();if(expected!==generation)return;if(data.error)throw Error(data.error.message);await show(data.scene,expected);}
 catch(e){if(expected===generation&&e.name!=='AbortError')error(e.message)}finally{polling=false;}}
$('target').onchange=()=>{generation++;assetAbort?.abort();frame=null;needsFit=true;clearGeometry();$('model-name').textContent='Untitled model';$('dimensions').textContent='Millimeters';$('status').textContent='Waiting for a model';$('revision-label').textContent='No snapshot yet';$('empty-state').classList.remove('hidden');$('viewer-stage').dataset.error='false';window.viewerState=null;
 const url=new URL(location.href);url.searchParams.set('workstation',$('target').value);history.replaceState(null,'',url);poll();};
$('fit').onclick=()=>fitModel();$('iso').onclick=()=>fitModel(new THREE.Vector3(1,-1,.9));$('top').onclick=()=>fitModel(new THREE.Vector3(0,-.0001,1));
$('grid').onclick=()=>{const visible=$('grid').getAttribute('aria-pressed')!=='true';$('grid').setAttribute('aria-pressed',String(visible));if(grid)grid.visible=visible;};
$('wireframe').onclick=()=>{material.wireframe=!material.wireframe;highlightMaterial.wireframe=material.wireframe;$('wireframe').setAttribute('aria-pressed',String(material.wireframe));if(edges)edges.visible=!material.wireframe;if(window.viewerState)window.viewerState.wireframe=material.wireframe;};
renderer.domElement.addEventListener('keydown',e=>{if(e.key.toLowerCase()==='f'){e.preventDefault();fitModel();}});
poll();setInterval(poll,1500);
