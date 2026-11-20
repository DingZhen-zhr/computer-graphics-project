// 多零件的看法：左侧零件清单（点一个单独看）、右边的零件小卡片、左下的炸开 / 透视 / 剖开 / 名字、零件名字标签。
import { h, svgEl } from "../dom.js";
import { fmtNum } from "../format.js";
import { explodedMatrix, isolateOpacity, layoutLabels } from "./logic.js";

const MATERIAL_NAMES = { abs: "ABS 塑料", aluminum: "铝", anodized: "阳极氧化铝", steel: "不锈钢", brass: "黄铜", rubber: "橡胶", wood: "木头" };

export function mountAssembly({ partsEl, cardEl, toolsEl, labelsEl }, scene, { onSection }) {
  const ui = { product: null, motion: null, focus: null, xray: false, explode: 0, names: true, poses: null, sizes: {} };
  const exRange = h("input", { type: "range", min: "0", max: "1", step: "0.01", value: "0", "aria-label": "炸开的程度",
    oninput: () => { ui.explode = Number(exRange.value); place(); } });
  const tg = (label, key, initial, fn) => {
    const b = h("button", { type: "button", class: "btn-glass", "aria-pressed": String(initial) }, label);
    b.addEventListener("click", () => {
      const on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(on));
      fn(on);
    });
    return b;
  };
  toolsEl.replaceChildren(
    h("span", { class: "explode glass pill" }, "炸开", exRange),
    tg("透视", "xray", false, (on) => { ui.xray = on; opacity(); }),
    tg("剖开", "cut", false, (on) => onSection(on)),
    tg("名字", "names", true, (on) => { ui.names = on; }));
  const lines = svgEl("svg");
  labelsEl.replaceChildren(lines);

  function opacity() {
    const map = {};
    for (const p of (ui.product && ui.product.parts) || []) map[p.id] = isolateOpacity(p.id, ui.focus, ui.xray);
    scene.setOpacity(map);
  }

  // 当前要显示的姿态：运动条给的姿态（没有就是装好时的位置），再加上炸开的平移
  function place() {
    if (!ui.motion) return;
    const base = ui.poses || ui.motion.rest;
    const b = scene.box();
    const scale = b.isEmpty() ? 100 : b.min.distanceTo(b.max) * 0.6;
    const out = {};
    for (const [id, m] of Object.entries(base)) out[id] = explodedMatrix(m, ui.motion.explode[id] || [0, 0, 0], ui.explode, scale);
    scene.setPoses(out);
  }

  // 材料色块：颜色是数据（材料表里的），用 .style 设，不写成内联样式（页面的安全策略不允许）
  function dot(p) {
    const i = h("i", { class: p.status === "current" ? "run" : "" });
    i.style.background = p.color;
    return i;
  }

  function renderList() {
    const prod = ui.product;
    if (!prod) { partsEl.replaceChildren(); cardEl.classList.add("gone"); return; }
    partsEl.replaceChildren(h("small", {}, "零件，点一个单独看"),
      ...prod.parts.map((p) => h("button", { type: "button", class: ui.focus === p.id ? "on" : "", "aria-pressed": String(ui.focus === p.id),
        onclick: () => focus(ui.focus === p.id ? null : p.id) },
        dot(p), p.name,
        h("em", { class: `num ${p.status === "done" ? "status-ok" : "mute"}` }, p.status === "done" ? `✓ ${p.checks.passed}/${p.checks.total}` : p.status === "current" ? "正在做" : "没开始"))),
      h("button", { type: "button", class: "all btn-text", onclick: () => focus(null) }, "看全部"));
  }

  function renderCard() {
    const p = ui.product && ui.product.parts.find((x) => x.id === ui.focus);
    if (!p) { cardEl.classList.add("gone"); return; }
    const size = ui.sizes[p.id] || scene.partSize(p.id);
    cardEl.classList.remove("gone");
    cardEl.replaceChildren(h("h3", {}, p.name),
      h("div", {}, `外形 ${size ? size.map(fmtNum).join(" × ") : "—"}`),
      h("div", {}, `材料 ${MATERIAL_NAMES[p.material] || p.material}`),
      h("div", {}, `${p.checks.total} 项检查，全部量过`));
  }

  function focus(id) {
    ui.focus = id;
    opacity();
    renderList();
    renderCard();
  }

  scene.onFrame((camera) => {
    if (!ui.product || !ui.names) { labelsEl.classList.add("gone"); return; }
    labelsEl.classList.remove("gone");
    const w = window.innerWidth;
    const hh = window.innerHeight;
    const pts = ui.product.parts.filter((p) => !ui.focus || p.id === ui.focus).map((p) => {
      const c = scene.partCenter(p.id);
      if (!c) return { id: p.id, visible: false };
      const v = c.clone().project(camera);
      return { id: p.id, x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * hh, visible: v.z < 1 };
    });
    const boxes = layoutLabels(pts, { width: w, height: hh });
    const names = Object.fromEntries(ui.product.parts.map((p) => [p.id, p.name]));
    const keep = new Set(boxes.map((b) => b.id));
    for (const el of [...labelsEl.querySelectorAll(".label")]) if (!keep.has(el.dataset.id)) el.remove();
    lines.replaceChildren();
    for (const b of boxes) {
      let el = labelsEl.querySelector(`.label[data-id="${b.id}"]`);
      if (!el) { el = h("div", { class: "label glass pill", dataset: { id: b.id } }, names[b.id]); labelsEl.append(el); }
      el.style.transform = `translate(${b.x}px, ${b.y}px)`;
      const ln = svgEl("line", { x1: b.ax, y1: b.ay, x2: b.left ? b.x + b.w : b.x, y2: b.y + b.h });
      lines.append(ln);
    }
  });

  return {
    update(product, motion, sizes) {
      ui.product = product;
      ui.motion = motion && !motion.error ? motion : null;
      ui.sizes = sizes || {};
      if (product && ui.focus && !product.parts.some((p) => p.id === ui.focus)) ui.focus = null;
      renderList();
      renderCard();
      opacity();
      place();
      toolsEl.classList.toggle("gone", !product);
    },
    setPoses(poses) { ui.poses = poses; place(); },
    highlight(ids) { scene.setTint(ids, "--bad"); },
  };
}
