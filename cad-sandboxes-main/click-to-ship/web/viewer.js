import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { ThreeMFLoader } from 'three/addons/loaders/3MFLoader.js';
import { unzipSync, strFromU8 } from 'three/addons/libs/fflate.module.js';

function readStep(buffer) {
  return new Promise((resolve,reject) => {
    const worker = new Worker('/step-worker.js');
    const timeout = setTimeout(() => {worker.terminate();reject(new Error('Preview is taking too long. You can continue building the quote.'));},60000);
    worker.onmessage = ({data}) => {clearTimeout(timeout);worker.terminate();data.error?reject(new Error(data.error)):resolve(data.meshes);};
    worker.onerror = () => {clearTimeout(timeout);worker.terminate();reject(new Error('STEP preview could not be loaded. You can continue with the quote.'));};
    worker.postMessage(buffer,[buffer]);
  });
}

export async function mountViewer(container, file, onReady) {
  const began = performance.now();
  const theme = getComputedStyle(container);
  const color = (name, fallback) => theme.getPropertyValue(name).trim() || fallback;
  const extension = file.name.split('.').pop().toLowerCase();
  const buffer = await file.arrayBuffer();
  let object, unitNote = 'Preview in millimeters';
  if (extension === 'stl') {
    object = new THREE.Mesh(new STLLoader().parse(buffer));
    unitNote = 'STL coordinates interpreted as millimeters';
  } else if (extension === 'obj') {
    object = new OBJLoader().parse(new TextDecoder().decode(buffer));
    unitNote = 'OBJ coordinates interpreted as millimeters';
  } else if (extension === '3mf') {
    const files = unzipSync(new Uint8Array(buffer));
    const parser = new DOMParser();
    const relationships = parser.parseFromString(strFromU8(files['_rels/.rels']),'application/xml');
    const target = [...relationships.getElementsByTagName('Relationship')].find(e => /\.model$/i.test(e.getAttribute('Target')))?.getAttribute('Target')?.replace(/^\//,'');
    if (!target || !files[target]) throw new Error('Could not determine the 3MF model units. The quote can still continue.');
    const xml = parser.parseFromString(strFromU8(files[target]),'application/xml');
    const unit = xml.documentElement.getAttribute('unit') || 'millimeter';
    const factor = {micron:0.001,millimeter:1,centimeter:10,inch:25.4,foot:304.8,meter:1000}[unit];
    if (!factor) throw new Error('Unknown 3MF units: '+unit);
    object = new ThreeMFLoader().parse(buffer);
    object.scale.setScalar(factor);
    unitNote = `3MF units: ${unit} · dimensions shown in mm`;
  } else if (['step','stp'].includes(extension)) {
    object = new THREE.Group();
    for (const m of await readStep(buffer)) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position',new THREE.BufferAttribute(m.position,3));
      if(m.normal)geometry.setAttribute('normal',new THREE.BufferAttribute(m.normal,3));
      geometry.setIndex(new THREE.BufferAttribute(m.index,1));
      object.add(new THREE.Mesh(geometry));
    }
    unitNote = 'STEP geometry converted to millimeters';
  } else throw new Error('Preview is unavailable for this format. You can still continue.');

  let vertices=0;
  object.traverse(child=>{if(child.isMesh)vertices+=child.geometry.attributes.position?.count||0;});
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  if (!vertices || ![size.x,size.y,size.z].every(Number.isFinite) || size.length()===0) throw new Error('The model does not contain viewable geometry.');
  const dimensions = [size.x,size.y,size.z];
  const material = new THREE.MeshStandardMaterial({color:color("--scene-model", "#a9b3b0"),roughness:.55,metalness:.08,side:THREE.DoubleSide});
  const edgeMaterial = new THREE.LineBasicMaterial({color:color("--scene-edge", "#596961"),transparent:true,opacity:.33});
  object.traverse(child => {
    if(!child.isMesh)return;
    const old = Array.isArray(child.material)?child.material:[child.material];
    old.forEach(m=>m?.dispose());
    child.material=material;
    if(!child.geometry.attributes.normal)child.geometry.computeVertexNormals();
    if(vertices<150000)child.add(new THREE.LineSegments(new THREE.EdgesGeometry(child.geometry,35),edgeMaterial));
  });
  const offset = new THREE.Group(); offset.add(object); object.position.sub(center);
  const normalized = new THREE.Group(); normalized.add(offset);
  const scale = 2.3/Math.max(...dimensions); normalized.scale.setScalar(scale);
  normalized.rotation.x = -Math.PI/2;

  const scene = new THREE.Scene();scene.background=new THREE.Color(color("--scene-background", "#eaf0ed"));scene.add(normalized);
  scene.add(new THREE.HemisphereLight(0xffffff,0x88998e,2.6));
  const light=new THREE.DirectionalLight(0xffffff,3.3);light.position.set(3,5,4);scene.add(light);
  const rim=new THREE.DirectionalLight(0xe5f4ff,1.5);rim.position.set(-3,1,-3);scene.add(rim);
  const grid=new THREE.GridHelper(10,20,color("--scene-grid-major", "#bdccc3"),color("--scene-grid-minor", "#d4ded8"));grid.position.y=-size.z*scale/2-.025;scene.add(grid);
  const camera=new THREE.PerspectiveCamera(38,1,.01,100);camera.position.set(4,2.8,4);
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.domElement.setAttribute('aria-label','Interactive model preview. Drag to rotate, scroll to zoom.');
  renderer.domElement.tabIndex=0;container.replaceChildren(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.autoRotate=!matchMedia("(prefers-reduced-motion: reduce)").matches;controls.autoRotateSpeed=.65;controls.minDistance=1.2;controls.maxDistance=14;controls.target.set(0,0,0);
  const stopRotation=()=>{controls.autoRotate=false;};renderer.domElement.addEventListener('pointerdown',stopRotation);
  const resize=new ResizeObserver(()=>{const w=container.clientWidth,h=container.clientHeight;if(w&&h){renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}});resize.observe(container);
  renderer.setAnimationLoop(()=>{if(document.visibilityState==='visible'){controls.update();renderer.render(scene,camera);}});
  const reset=()=>{camera.position.set(4,2.8,4);controls.target.set(0,0,0);controls.update();};
  const wireframe=()=>{material.wireframe=!material.wireframe;return material.wireframe;};
  renderer.domElement.addEventListener('keydown',e=>{
    if(e.key==='r')reset();
    if(e.key==='+'||e.key==='='){camera.position.multiplyScalar(.9);e.preventDefault();}
    if(e.key==='-'){camera.position.multiplyScalar(1.1);e.preventDefault();}
  });
  onReady({dimensions_mm:dimensions,vertices,unitNote,ready_ms:Math.round(performance.now()-began),format:extension});
  return {reset,wireframe,dispose(){resize.disconnect();controls.dispose();renderer.setAnimationLoop(null);renderer.dispose();scene.traverse(o=>{o.geometry?.dispose();});material.dispose();edgeMaterial.dispose();container.replaceChildren();}};
}
