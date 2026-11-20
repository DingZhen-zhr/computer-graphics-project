// 三维舞台：一个或几个零件放在柔和的影棚光里，可以转到任意角度（包括底下）、平移、缩放。
// 坐标和建模一样 Z 朝上；矩阵按行 16 个数（motion.json 的格式）。颜色从 tokens.css 读，脚本里不写颜色值。
import * as THREE from "three";
import { OrbitControls } from "../../vendor/three/OrbitControls.js";
import { STLLoader } from "../../vendor/three/STLLoader.js";
import { cssVar } from "../theme.js";
import { materialFor, safeView } from "./logic.js";

export const STL_FAILED = "三维模型没有加载出来，先用截图代替。";
export const NO_WEBGL = "这台电脑现在显示不了三维画面，先用截图代替。";
const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const col = (name) => new THREE.Color(cssVar(name) || undefined);
const isDark = () => getComputedStyle(document.documentElement).colorScheme === "dark";

export function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

function matrix4(m) {
  const out = new THREE.Matrix4();
  out.set(...m);
  return out;
}

export function createScene(container, { onFallback = () => {} } = {}) {
  if (!webglAvailable()) {
    onFallback(NO_WEBGL);
    return null;
  }
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.localClippingEnabled = true;
  container.append(renderer.domElement);

  const scene = new THREE.Scene();
  const persp = new THREE.PerspectiveCamera(26, 1, 0.1, 100000);
  const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100000);
  for (const c of [persp, ortho]) c.up.set(0, 0, 1);
  let camera = persp;
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.screenSpacePanning = true;   // 不限制上下角度：可以转到底下看

  const hemi = new THREE.HemisphereLight();
  hemi.position.set(0, 0, 1);
  const key = new THREE.DirectionalLight();
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  const rim = new THREE.DirectionalLight();
  const under = new THREE.DirectionalLight(undefined, 0.6);   // 从底下看时也有光
  scene.add(hemi, key, rim, under, key.target);
  const shadowMat = new THREE.ShadowMaterial({ opacity: 0.2 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), shadowMat);
  ground.receiveShadow = true;
  let grid = null;
  scene.add(ground);
  const root = new THREE.Group();
  scene.add(root);

  const loader = new STLLoader();
  const geoCache = new Map();
  const parts = new Map();   // id → {group, mesh, edges, mat, rest}
  const edgeMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.28 });
  const listeners = new Set();
  let box = new THREE.Box3();
  let fly = null;
  let shift = 0;
  let shiftTo = 0;
  let clip = null;
  let key0 = "";

  function applyTheme() {
    hemi.color = col("--sky");
    hemi.groundColor = col("--ground");
    hemi.intensity = isDark() ? 0.9 : 2.0;
    key.color = col("--sky");
    key.intensity = isDark() ? 3.0 : 2.4;
    rim.color = col("--rim");
    rim.intensity = isDark() ? 4.0 : 1.0;
    edgeMat.color = col("--edge");
    shadowMat.opacity = isDark() ? 0.55 : 0.18;
    if (grid) grid.material.color = col("--edge");
    for (const p of parts.values()) paint(p);
  }

  function paint(p) {
    const m = materialFor(p.finish, p.color, isDark() ? "dark" : "light");
    p.mat.color = new THREE.Color(m.color || cssVar("--mute"));
    if (m.lift) p.mat.color.lerp(new THREE.Color(1, 1, 1), m.lift);
    p.mat.roughness = m.roughness;
    p.mat.metalness = m.metalness;
  }

  async function geometry(url) {
    if (!geoCache.has(url)) {
      geoCache.set(url, loader.loadAsync(url).then((g) => { g.computeVertexNormals(); return g; }));
    }
    return geoCache.get(url);
  }

  function frame() {
    box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 1);
    const dist = (radius * 2.1) / Math.sin(THREE.MathUtils.degToRad(persp.fov / 2));
    persp.near = dist / 100;
    persp.far = dist * 100;
    const dir = new THREE.Vector3(1, -1.2, 0.9).normalize();
    persp.position.copy(center).addScaledVector(dir, dist);
    ortho.position.copy(persp.position);
    controls.target.copy(center);
    const span = Math.max(size.x, size.y) * 4 + 100;
    ground.scale.set(span, span, 1);
    ground.position.set(center.x, center.y, box.min.z - 0.3);
    if (grid) { scene.remove(grid); grid.geometry.dispose(); }
    grid = new THREE.GridHelper(span / 2, 40);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, box.min.z - 0.25);
    grid.material.transparent = true;
    grid.material.opacity = isDark() ? 0.1 : 0.08;
    grid.material.color = col("--edge");
    scene.add(grid);
    key.position.copy(center).add(new THREE.Vector3(radius * 1.2, -radius * 1.6, radius * 2.4));
    key.target.position.copy(center);
    Object.assign(key.shadow.camera, { left: -radius * 2, right: radius * 2, top: radius * 2, bottom: -radius * 2, far: radius * 8 });
    key.shadow.camera.updateProjectionMatrix();
    rim.position.copy(center).add(new THREE.Vector3(-radius * 2, radius * 2, radius));
    under.position.copy(center).add(new THREE.Vector3(0, 0, -radius * 3));
    resize();
    controls.update();
  }

  async function showParts(list) {
    const ticket = Symbol("load");
    showParts.ticket = ticket;
    let loaded;
    try {
      loaded = await Promise.all(list.map(async (p) => ({ ...p, geo: await geometry(p.url) })));
    } catch {
      if (showParts.ticket === ticket) onFallback(STL_FAILED);
      return false;
    }
    if (showParts.ticket !== ticket) return false;
    for (const p of parts.values()) root.remove(p.group);
    parts.clear();
    for (const p of loaded) {
      const mat = new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, transparent: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      const mesh = new THREE.Mesh(p.geo, mat);
      mesh.castShadow = true;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(p.geo, 25), edgeMat);
      const group = new THREE.Group();
      group.add(mesh, edges);
      group.matrixAutoUpdate = false;
      const entry = { id: p.id, group, mesh, edges, mat, rest: p.matrix || null, color: p.color, finish: p.finish || "matte" };
      setMatrix(entry, p.matrix);
      paint(entry);
      parts.set(p.id, entry);
      root.add(group);
    }
    applyClip();
    const sig = list.map((p) => p.id).join(",");
    if (sig !== key0) { key0 = sig; frame(); }
    return true;
  }

  function setMatrix(entry, m) {
    entry.group.matrix.copy(m ? matrix4(m) : new THREE.Matrix4());
    entry.group.matrixWorldNeedsUpdate = true;
  }

  function applyClip() {
    for (const p of parts.values()) p.mat.clippingPlanes = clip ? [clip] : [];
    edgeMat.clippingPlanes = clip ? [clip] : [];
  }

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    persp.aspect = w / h;
    const d = persp.position.distanceTo(controls.target) * Math.tan(THREE.MathUtils.degToRad(persp.fov / 2));
    Object.assign(ortho, { left: -d * persp.aspect, right: d * persp.aspect, top: d, bottom: -d, near: persp.near, far: persp.far });
    for (const c of [persp, ortho]) c.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(container);

  function flyTo(dir) {
    const v = safeView(dir);
    const d = camera.position.distanceTo(controls.target);
    const to = controls.target.clone().add(new THREE.Vector3(...v.dir).multiplyScalar(d));
    if (reduced()) { camera.position.copy(to); controls.update(); return; }
    fly = { from: camera.position.clone(), to, t0: performance.now() };
  }

  renderer.setAnimationLoop((now) => {
    if (fly) {
      const k = Math.min(1, (now - fly.t0) / 450);
      camera.position.lerpVectors(fly.from, fly.to, 1 - (1 - k) ** 3);
      if (k === 1) fly = null;
    }
    shift += (shiftTo - shift) * (reduced() ? 1 : 0.15);
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w && h) camera.setViewOffset(w, h, 0, shift, w, h);
    const below = !box.isEmpty() && camera.position.z < box.min.z;   // 转到底下时，地面和网格自动隐藏
    ground.visible = !below;
    if (grid) grid.visible = !below;
    controls.update();
    renderer.render(scene, camera);
    for (const fn of listeners) fn(camera);
  });
  applyTheme();
  resize();

  return {
    camera: () => camera,
    renderer,
    root,
    box: () => box.clone(),
    showParts,
    setPoses(poses) { for (const [id, m] of Object.entries(poses || {})) if (parts.has(id)) setMatrix(parts.get(id), m); },
    resetPoses() { for (const p of parts.values()) setMatrix(p, p.rest); },
    setOpacity(map) {
      for (const p of parts.values()) {
        const o = map[p.id] ?? 1;
        p.mat.opacity = o;
        p.mat.depthWrite = o > 0.5;
        p.edges.visible = o > 0.15;
      }
    },
    setTint(ids, name) { for (const p of parts.values()) { if (ids.includes(p.id)) p.mat.color = col(name); else paint(p); } },
    partSize(id) {
      const p = parts.get(id);
      if (!p) return null;
      p.mesh.geometry.computeBoundingBox();
      const s = p.mesh.geometry.boundingBox.getSize(new THREE.Vector3());
      return [s.x, s.y, s.z];
    },
    partCenter(id) {
      const p = parts.get(id);
      if (!p) return null;
      const b = new THREE.Box3().setFromObject(p.group);
      return b.isEmpty() ? null : b.getCenter(new THREE.Vector3());
    },
    flyTo,
    setOrtho(on) {
      const next = on ? ortho : persp;
      next.position.copy(camera.position);
      next.quaternion.copy(camera.quaternion);
      camera = next;
      controls.object = camera;
      resize();
    },
    setSection(axis, t) {
      if (!axis) { clip = null; applyClip(); return; }
      const i = "xyz".indexOf(axis);
      const n = [0, 0, 0];
      n[i] = -1;
      const at = box.min.getComponent(i) + (box.max.getComponent(i) - box.min.getComponent(i)) * t;
      clip = new THREE.Plane(new THREE.Vector3(...n), at);
      applyClip();
    },
    setShift(px) { shiftTo = px; },
    setTheme: applyTheme,
    onFrame(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    dispose() { renderer.setAnimationLoop(null); ro.disconnect(); controls.dispose(); renderer.dispose(); renderer.domElement.remove(); },
  };
}
