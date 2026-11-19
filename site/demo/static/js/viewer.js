// 3D 视图：three.js 显示 STL。z 朝上；实体颜色、轮廓线、网格、尺寸线的颜色都从 tokens.css 读（脚本里不写颜色值）。
// 浅色是浅灰实体加墨色轮廓线；深色是半透明浅蓝实体加白色轮廓线。外形尺寸是叠在画布上的文字，每一帧按投影位置摆。
import * as THREE from "three";
import { OrbitControls } from "../vendor/three/OrbitControls.js";
import { STLLoader } from "../vendor/three/STLLoader.js";
import { h } from "./dom.js";
import { cssVar } from "./theme.js";
import { NO_WEBGL, STL_FAILED, dimSegments } from "./viewer-dims.js";

const VIEW_DIR = new THREE.Vector3(-0.85, -1.4, 0.95).normalize();
const EDGE_ANGLE = 30;

export function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGL2RenderingContext && c.getContext("webgl2")) || !!c.getContext("webgl");
  } catch {
    return false;
  }
}

const color = (name) => new THREE.Color(cssVar(name) || undefined);
const isDark = () => cssVar("color-scheme") === "dark" || getComputedStyle(document.documentElement).colorScheme === "dark";

export function createViewer(container, { onFallback } = {}) {
  const fallback = (why) => onFallback && onFallback(why);
  if (!webglAvailable()) {
    fallback(NO_WEBGL);
    return { ok: false, load: async () => false, setWireframe() {}, resetView() {}, setTheme() {}, dispose() {} };
  }
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    fallback(NO_WEBGL);
    return { ok: false, load: async () => false, setWireframe() {}, resetView() {}, setTheme() {}, dispose() {} };
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.className = "viewer-canvas";
  const labels = h("div", { class: "dim-labels", "aria-hidden": "true" });
  container.append(canvas, labels);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100000);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.1;
  const white = new THREE.Color().setScalar(1);   // 灯光是中性的白光，不是界面颜色
  scene.add(new THREE.HemisphereLight(white, white, 1.1));
  const key = new THREE.DirectionalLight(white, 1.4);
  key.position.set(-1.2, -2.0, 3.0);
  scene.add(key);

  const material = new THREE.MeshStandardMaterial({ metalness: 0.05, roughness: 0.75, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  const edgeMat = new THREE.LineBasicMaterial();
  const dimMat = new THREE.LineBasicMaterial();
  const model = new THREE.Group();
  scene.add(model);
  let grid = null;
  let dims = [];
  let box = null;
  let wire = false;
  let dirty = true;
  let raf = 0;

  function applyTheme() {
    const dark = isDark();
    material.color = color("--part");
    material.transparent = dark;
    material.opacity = dark ? 0.55 : 1;
    material.depthWrite = !dark;
    edgeMat.color = color("--part-edge");
    dimMat.color = color("--accent");
    if (grid) {
      grid.material.color = color("--line-soft");
    }
    dirty = true;
  }

  function clearModel() {
    for (const obj of [...model.children]) {
      model.remove(obj);
      if (obj.geometry) obj.geometry.dispose();
    }
    if (grid) {
      scene.remove(grid);
      grid.geometry.dispose();
      grid.material.dispose();
      grid = null;
    }
    labels.replaceChildren();
    dims = [];
  }

  function frame() {
    if (!box) return;
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(size.length() / 2, 1);
    const dist = (radius * 1.25) / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
    camera.near = dist / 100;
    camera.far = dist * 100;
    camera.position.copy(center).addScaledVector(VIEW_DIR, dist);
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
    dirty = true;
  }

  function addDims() {
    const b = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z];
    const pts = [];
    for (const s of dimSegments(b)) {
      pts.push(...s.from, ...s.to);
      for (const [a, c] of s.ext) pts.push(...a, ...c);
      const el = h("span", { class: "dim-label" }, s.text);
      labels.append(el);
      dims.push({ el, at: new THREE.Vector3(...s.label) });
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    model.add(new THREE.LineSegments(geo, dimMat));
    const step = Math.pow(10, Math.floor(Math.log10(Math.max(box.max.x - box.min.x, box.max.y - box.min.y, 1))));
    const span = Math.ceil((Math.max(box.max.x - box.min.x, box.max.y - box.min.y) * 1.6) / step) * step;
    grid = new THREE.GridHelper(span, Math.round(span / (step / 2)));
    grid.rotation.x = Math.PI / 2;
    grid.position.set((box.min.x + box.max.x) / 2, (box.min.y + box.max.y) / 2, box.min.z);
    grid.material.transparent = true;
    grid.material.opacity = 0.35;
    scene.add(grid);
  }

  function placeLabels() {
    const w = canvas.clientWidth;
    const hgt = canvas.clientHeight;
    for (const d of dims) {
      const p = d.at.clone().project(camera);
      const show = p.z < 1;
      d.el.style.setProperty("transform", `translate(${((p.x + 1) / 2) * w}px, ${((1 - p.y) / 2) * hgt}px) translate(-50%, -50%)`);
      d.el.style.setProperty("visibility", show ? "visible" : "hidden");
    }
  }

  function resize() {
    const w = container.clientWidth;
    const hgt = container.clientHeight;
    if (!w || !hgt) return;
    renderer.setSize(w, hgt, false);
    camera.aspect = w / hgt;
    camera.updateProjectionMatrix();
    dirty = true;
  }
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  controls.addEventListener("change", () => { dirty = true; });
  const loop = () => {
    raf = requestAnimationFrame(loop);
    // 相机的位置算坏了（出现过一次，原因没找到）：重新取景，免得画面一直空着
    if (box && !(Number.isFinite(camera.position.x) && Number.isFinite(camera.quaternion.x) && Number.isFinite(controls.target.x))) frame();
    const moved = controls.update();
    if (moved || dirty) {
      dirty = false;
      renderer.render(scene, camera);
      placeLabels();
    }
  };
  applyTheme();
  resize();
  loop();

  let loading = 0;
  return {
    ok: true,
    async load(url) {
      const ticket = ++loading;
      let geo;
      try {
        geo = await new STLLoader().loadAsync(url);
      } catch {
        if (ticket === loading) fallback(STL_FAILED);
        return false;
      }
      if (ticket !== loading) {
        geo.dispose();
        return false;
      }
      clearModel();
      geo.computeVertexNormals();
      geo.computeBoundingBox();
      box = geo.boundingBox.clone();
      model.add(new THREE.Mesh(geo, material));
      model.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, EDGE_ANGLE), edgeMat));
      addDims();
      applyTheme();
      material.wireframe = wire;
      frame();
      return true;
    },
    setWireframe(on) {
      wire = !!on;
      material.wireframe = wire;
      dirty = true;
    },
    resetView: frame,
    setTheme: applyTheme,
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      clearModel();
      material.dispose();
      edgeMat.dispose();
      dimMat.dispose();
      controls.dispose();
      renderer.dispose();
      canvas.remove();
      labels.remove();
    },
  };
}
