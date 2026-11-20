// 右上角：坐标轴小图（X 红、Y 绿、Z 蓝，Z 朝上）、五个视角按钮、看图工具（剖开、尺寸标注、正交视图）。
import * as THREE from "three";
import { h, svgEl } from "../dom.js";
import { fmtNum } from "../format.js";
import { cssVar } from "../theme.js";
import { axisLayout, snapDirection, VIEWS } from "./logic.js";

const VIEW_LABELS = [["front", "前"], ["top", "上"], ["right", "右"], ["iso", "立体"], ["bottom", "底"]];

export function mountGizmo(root, scene) {
  const svg = svgEl("svg", { viewBox: "0 0 104 104", role: "img", "aria-label": "方向：点一个轴，转到从那边看" });
  const views = h("div", { class: "views glass" }, VIEW_LABELS.map(([k, t]) => h("button", { type: "button", onclick: () => scene.flyTo(VIEWS[k]) }, t)));
  const dims = dimsOverlay(scene);
  const state = { section: null, t: 0.5, ortho: false, dims: false };
  const secAxis = h("select", { "aria-label": "沿哪个方向剖开", onchange: () => { state.section = secAxis.value; apply(); } },
    ["x", "y", "z"].map((a) => h("option", { value: a }, a.toUpperCase())));
  const secRange = h("input", { type: "range", min: "0", max: "1", step: "0.01", value: "0.5", "aria-label": "剖开的位置",
    oninput: () => { state.t = Number(secRange.value); apply(); } });
  const secCtl = h("div", { class: "section-ctl gone" }, secAxis, secRange);
  const secBtn = toggle("剖开", (on) => { state.section = on ? secAxis.value : null; secCtl.classList.toggle("gone", !on); apply(); });
  const dimBtn = toggle("尺寸标注", (on) => { state.dims = on; dims.show(on); });
  const orthoBtn = toggle("正交视图", (on) => { state.ortho = on; scene.setOrtho(on); });
  function apply() { scene.setSection(state.section, state.t); }
  root.replaceChildren(svg, views, h("div", { class: "view-tools" }, secBtn, secCtl, dimBtn, orthoBtn));
  svg.addEventListener("click", (e) => {
    const d = e.target.dataset;
    if (d && d.axis) scene.flyTo(snapDirection(d.axis, d.positive === "1"));
  });
  let last = "";
  scene.onFrame((camera) => {
    const q = camera.quaternion;
    const sig = [q.x, q.y, q.z, q.w].map((v) => v.toFixed(3)).join();
    dims.update(camera);
    if (sig === last) return;
    last = sig;
    draw(svg, axisLayout([q.x, q.y, q.z, q.w]));
  });
  return { setSectionVisible(on) { secBtn.parentElement.hidden = !on; }, reset() { dims.refresh(); } };
}

function toggle(label, fn) {
  const b = h("button", { type: "button", class: "btn-glass", "aria-pressed": "false" }, label);
  b.addEventListener("click", () => {
    const on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    fn(on);
  });
  return b;
}

function draw(svg, items) {
  svg.replaceChildren();
  for (const o of items) {
    const c = cssVar(o.color);
    const x = 52 + o.x * 36;
    const y = 52 + o.y * 36;
    if (o.positive) svg.append(svgEl("line", { x1: 52, y1: 52, x2: x, y2: y, stroke: c, "stroke-width": 2.5 }));
    const dot = svgEl("circle", { cx: x, cy: y, r: o.positive ? 10 : 7, fill: o.positive ? c : "none", stroke: c, "stroke-width": 2 });
    dot.dataset.axis = o.axis;
    dot.dataset.positive = o.positive ? "1" : "0";
    dot.style.cursor = "pointer";
    svg.append(dot);
    if (o.positive) {
      const t = svgEl("text", { x, y: y + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 700, fill: cssVar("--acc-ink") });
      t.style.pointerEvents = "none";
      t.style.fontFamily = "Archivo";
      t.textContent = o.axis;
      svg.append(t);
    }
  }
}

// 尺寸标注：外形包围盒的三条边，标上长度（毫米）
function dimsOverlay(scene) {
  const layer = h("div", { class: "dims", "aria-hidden": "true" });
  document.body.append(layer);
  let helper = null;
  let labels = [];
  let on = false;
  function refresh() {
    if (helper) { scene.root.parent.remove(helper); helper = null; }
    layer.replaceChildren();
    labels = [];
    if (!on) return;
    const b = scene.box();
    if (b.isEmpty()) return;
    helper = new THREE.Box3Helper(b, new THREE.Color(cssVar("--mute")));
    scene.root.parent.add(helper);
    const s = b.getSize(new THREE.Vector3());
    const mid = (x, y, z) => new THREE.Vector3(x, y, z);
    labels = [[mid((b.min.x + b.max.x) / 2, b.min.y, b.min.z), s.x], [mid(b.max.x, (b.min.y + b.max.y) / 2, b.min.z), s.y],
      [mid(b.max.x, b.min.y, (b.min.z + b.max.z) / 2), s.z]].map(([at, len]) => {
      const el = h("span", { class: "dim-label num glass pill" }, `${fmtNum(len)} mm`);
      layer.append(el);
      return { el, at };
    });
  }
  return {
    show(v) { on = v; refresh(); },
    refresh,
    update(camera) {
      const w = window.innerWidth;
      const hh = window.innerHeight;
      for (const l of labels) {
        const p = l.at.clone().project(camera);
        l.el.style.transform = `translate(${((p.x + 1) / 2) * w}px, ${((1 - p.y) / 2) * hh}px) translate(-50%, -50%)`;
        l.el.style.visibility = p.z < 1 ? "visible" : "hidden";
      }
    },
  };
}
