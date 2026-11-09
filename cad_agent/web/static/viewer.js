// 01 模型：three.js 显示 STL。z 轴朝上（CAD 习惯），相机从前左上方看（零件正面朝 -y）。
// 任何一步失败（没有 WebGL、没有 STL、加载出错）都退回显示截图，界面不会空着。

import * as THREE from "three";
import { OrbitControls } from "./vendor/three/OrbitControls.js";
import { STLLoader } from "./vendor/three/STLLoader.js";

const VIEW_DIR = new THREE.Vector3(-0.9, -1.45, 0.95).normalize();

export class Viewer {
  constructor(container, { onInfo } = {}) {
    this.container = container;
    this.onInfo = onInfo || (() => {});
    this.url = null;
    this.wire = false;
    this.ok = false;
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
    } catch (e) {
      console.warn("WebGL 不可用，改用截图", e);
      return;
    }
    this.ok = true;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.canvas = this.renderer.domElement;
    this.canvas.classList.add("hidden");
    container.prepend(this.canvas);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100000);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xcfd0d6, 1.15));
    const key = new THREE.DirectionalLight(0xffffff, 1.7);
    key.position.set(-1.2, -2.0, 3.0);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 0.55);
    rim.position.set(2.0, 1.5, 1.0);
    this.scene.add(rim);

    this.material = new THREE.MeshStandardMaterial({ color: 0xdadce2, metalness: 0.12, roughness: 0.48, flatShading: false });
    this.edgeMaterial = new THREE.LineBasicMaterial({ color: 0x1d1d1f, transparent: true, opacity: 0.42 });
    this.group = new THREE.Group();
    this.scene.add(this.group);

    new ResizeObserver(() => this._resize()).observe(container);
    this._resize();
    const loop = () => {
      this._raf = requestAnimationFrame(loop);
      if (this.controls.update() || this._dirty) {
        this._dirty = false;
        this.renderer.render(this.scene, this.camera);
      }
    };
    this.controls.addEventListener("change", () => { this._dirty = true; });
    loop();
  }

  _resize() {
    if (!this.ok) return;
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.render();
  }

  _disposeGroup() {
    for (const child of [...this.group.children]) {
      child.geometry?.dispose();
      this.group.remove(child);
    }
  }

  async load(url) {
    if (!this.ok) throw new Error("WebGL 不可用");
    if (url === this.url && this.group.children.length) return this.info;
    const geometry = await new Promise((resolve, reject) => new STLLoader().load(url, resolve, undefined, reject));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    this._disposeGroup();
    const mesh = new THREE.Mesh(geometry, this.material);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), this.edgeMaterial);
    this.group.add(mesh, edges);

    const box = geometry.boundingBox;
    const size = new THREE.Vector3();
    box.getSize(size);
    const span = Math.max(size.x, size.y, size.z) || 1;
    const grid = new THREE.GridHelper(Math.ceil(span * 2.4 / 10) * 10, 24, 0xc7c7cc, 0xe2e2e6);
    grid.rotation.x = Math.PI / 2;  // GridHelper 默认在 xz 平面，转到 xy 平面（z=0 是桌面）
    grid.position.set((box.min.x + box.max.x) / 2, (box.min.y + box.max.y) / 2, box.min.z - 0.01);
    grid.material.transparent = true;
    grid.material.opacity = 0.9;
    this.group.add(grid);

    this.url = url;
    this.box = box.clone();
    this.info = { size: [size.x, size.y, size.z] };
    this.setWire(this.wire);
    this.fit();
    this.canvas.classList.remove("hidden");
    this.onInfo(this.info);
    return this.info;
  }

  fit() {
    if (!this.ok || !this.box) return;
    const center = new THREE.Vector3();
    this.box.getCenter(center);
    const radius = this.box.getSize(new THREE.Vector3()).length() / 2 || 1;
    const fov = (this.camera.fov * Math.PI) / 180;
    const dist = (radius / Math.sin(fov / 2)) * 1.08;
    this.camera.near = dist / 100;
    this.camera.far = dist * 100;
    this.camera.position.copy(center).addScaledVector(VIEW_DIR, dist);
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
    this.controls.update();
    this.render();
  }

  // 直接画一帧：不依赖动画循环（页面在后台时浏览器会暂停 requestAnimationFrame）
  render() {
    if (!this.ok) return;
    this._dirty = false;
    this.renderer.render(this.scene, this.camera);
  }

  setWire(on) {
    this.wire = on;
    if (!this.ok) return;
    this.material.wireframe = on;
    this.edgeMaterial.opacity = on ? 0.15 : 0.42;
    this.render();
  }

  hide() {
    this.canvas?.classList.add("hidden");
  }

  show() {
    if (this.group?.children.length) {
      this.canvas.classList.remove("hidden");
      this._resize();
    }
  }
}

// ------------------------------------------------------------------ 缩略图
// 版本卡片和对话里的小图也用同一套灯光和材质画，和上面的 3D 视图风格一致；
// SCA 自带的截图是黑底的，只在没有 STL 或 WebGL 不可用时才用。

const thumbCache = new Map();
let thumbKit = null;

function kit() {
  if (thumbKit) return thumbKit;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(2);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0xcfd0d6, 1.15));
  const key = new THREE.DirectionalLight(0xffffff, 1.7);
  key.position.set(-1.2, -2.0, 3.0);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.55);
  rim.position.set(2.0, 1.5, 1.0);
  scene.add(rim);
  const camera = new THREE.PerspectiveCamera(30, 4 / 3, 0.1, 100000);
  camera.up.set(0, 0, 1);
  const material = new THREE.MeshStandardMaterial({ color: 0xdadce2, metalness: 0.12, roughness: 0.48 });
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x1d1d1f, transparent: true, opacity: 0.5 });
  thumbKit = { renderer, scene, camera, material, edgeMaterial };
  return thumbKit;
}

export function thumbnail(url, width = 480, height = 360) {
  if (thumbCache.has(url)) return thumbCache.get(url);
  const job = new Promise((resolve, reject) => new STLLoader().load(url, resolve, undefined, reject)).then((geometry) => {
    const { renderer, scene, camera, material, edgeMaterial } = kit();
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    const mesh = new THREE.Mesh(geometry, material);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), edgeMaterial);
    scene.add(mesh, edges);
    const box = geometry.boundingBox;
    const center = box.getCenter(new THREE.Vector3());
    const radius = box.getSize(new THREE.Vector3()).length() / 2 || 1;
    const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 0.95;
    camera.aspect = width / height;
    camera.near = dist / 100;
    camera.far = dist * 100;
    camera.position.copy(center).addScaledVector(VIEW_DIR, dist);
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    renderer.render(scene, camera);
    const data = renderer.domElement.toDataURL("image/png");
    scene.remove(mesh, edges);
    geometry.dispose();
    edges.geometry.dispose();
    return data;
  });
  job.catch(() => thumbCache.delete(url));
  thumbCache.set(url, job);
  return job;
}

// 把 root 里所有 <img data-stl="..."> 换成三维缩略图；失败就用 data-png 的截图
export function hydrateThumbs(root) {
  for (const img of root.querySelectorAll("img[data-stl]")) {
    const stl = img.dataset.stl;
    img.removeAttribute("data-stl");
    thumbnail(stl).then((src) => { img.src = src; }).catch(() => { if (img.dataset.png) img.src = img.dataset.png; });
  }
}
