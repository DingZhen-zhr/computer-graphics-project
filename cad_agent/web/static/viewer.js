// 01 模型里的 3D 预览。只负责 3D：加载 STL、转动、缩放、平移、线框、重置视角。
// z 轴朝上；z=0 平面上画一个淡网格。出任何错都交给调用方（它会退回显示截图）。

import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";
import { STLLoader } from "/static/vendor/three/STLLoader.js";

const MODEL_COLOR = 0xc9c9ce;
const EDGE_COLOR = 0x1d1d1f;
const GRID_COLOR = 0xd2d2d7;

export class Viewer {
  // box：放画布的容器。WebGL 不可用时这里会抛错，由调用方接住。
  constructor(box) {
    this.box = box;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0xffffff, 1);
    this.canvas = this.renderer.domElement;
    this.canvas.setAttribute("aria-label", "模型的三维预览，可以拖动旋转、滚轮缩放、右键平移");
    this.canvas.tabIndex = 0;
    box.prepend(this.canvas);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    this.camera.up.set(0, 0, 1);   // z 轴朝上
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = false;
    this.controls.addEventListener("change", () => this.render());

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xb8b8c0, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(1, -1.5, 2);
    this.scene.add(sun);

    this.mesh = null;
    this.edges = null;
    this.grid = null;
    this.wireframe = false;
    this.frame = { center: new THREE.Vector3(), radius: 50 };
    this.token = 0;   // 换版本时，丢掉还没回来的旧请求

    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(box);
    this.resize();
  }

  get visible() { return this.canvas.style.display !== "none"; }
  setVisible(on) { this.canvas.style.display = on ? "block" : "none"; if (on) this.resize(); }

  resize() {
    const { clientWidth: w, clientHeight: h } = this.box;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.render();
  }

  render() { this.renderer.render(this.scene, this.camera); }

  // 加载并显示一个版本的 STL；成功返回 true。失败（没有文件、格式不对……）抛错。
  async show(url) {
    const token = ++this.token;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`加载模型失败（${res.status}）`);
    const buffer = await res.arrayBuffer();
    if (token !== this.token) return false;   // 这期间用户已经换了别的版本
    const geometry = new STLLoader().parse(buffer);
    if (!geometry.attributes.position || geometry.attributes.position.count === 0) {
      geometry.dispose();
      throw new Error("模型文件是空的");
    }
    geometry.computeVertexNormals();
    this.clear();
    const material = new THREE.MeshStandardMaterial({ color: MODEL_COLOR, metalness: 0.05, roughness: 0.65, flatShading: true, wireframe: this.wireframe });
    this.mesh = new THREE.Mesh(geometry, material);
    this.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30),
      new THREE.LineBasicMaterial({ color: EDGE_COLOR, transparent: true, opacity: 0.35 }));
    this.edges.visible = !this.wireframe;
    this.scene.add(this.mesh, this.edges);
    this.fit(geometry);
    this.resetView();
    return true;
  }

  fit(geometry) {
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    const box = geometry.boundingBox;
    const size = box.getSize(new THREE.Vector3());
    this.frame = { center: box.getCenter(new THREE.Vector3()), radius: Math.max(geometry.boundingSphere.radius, 1) };
    // 淡网格画在 z=0 平面上（GridHelper 默认在 xz 平面，转 90° 放到 xy 平面）
    const span = Math.max(size.x, size.y, 20) * 2;
    const step = span > 400 ? 50 : span > 120 ? 20 : 10;
    const cells = Math.max(2, Math.ceil(span / step));
    this.grid = new THREE.GridHelper(cells * step, cells, GRID_COLOR, GRID_COLOR);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.position.set(this.frame.center.x, this.frame.center.y, 0);
    this.scene.add(this.grid);
    this.camera.near = this.frame.radius / 100;
    this.camera.far = this.frame.radius * 100;
    this.camera.updateProjectionMatrix();
  }

  resetView() {
    const { center, radius } = this.frame;
    const distance = radius / Math.sin((this.camera.fov * Math.PI) / 360) * 1.05;
    const direction = new THREE.Vector3(1, -1.25, 0.85).normalize();
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.controls.target.copy(center);
    this.controls.update();
    this.render();
  }

  setWireframe(on) {
    this.wireframe = on;
    if (this.mesh) this.mesh.material.wireframe = on;
    if (this.edges) this.edges.visible = !on;
    this.render();
  }

  // 释放旧模型的几何体和材质，免得换几次版本就越占越多
  clear() {
    for (const obj of [this.mesh, this.edges, this.grid]) {
      if (!obj) continue;
      this.scene.remove(obj);
      obj.geometry.dispose();
      (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach((m) => m.dispose());
    }
    this.mesh = this.edges = this.grid = null;
    this.render();
  }

  dispose() {
    this.token++;
    this.observer.disconnect();
    this.clear();
    this.controls.dispose();
    this.renderer.dispose();
    this.canvas.remove();
  }
}
