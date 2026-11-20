// 调参数面板：从底部升起，舞台往上让；按组列出参数，滑条和数字框一起改；"应用"从头重做一遍、再量一遍。
// 不做"只生成不检查"的预览（偏离 D32）：改动要点"应用"才会重做。
import { $, clear, h } from "./dom.js";
import { fmtNum } from "./format.js";
import { pendingChanges, sliderRange, validateEdit } from "./params-logic.js";

const NOTE = '改好后点"应用"，会从头重做一遍、再量一遍。不花钱。';
const NOT_YET = "做好第一个版本之后，就可以在这里直接改数值。";
const BUSY = "正在做，等这一轮结束再改。";
const FAILED = "改成这些数值后没有全部通过，已经退回原来的数值。";
const UNIT = { mm: "mm", deg: "°", 1: "" };
const SOURCE = { user: "你给的", suggested: "建议" };

let ui = null;

export function mountTune(actions) {
  ui = { actions, edits: {}, open: false, state: null, msg: "", failed: null, working: false };
}

export function isTuneOpen() { return !!(ui && ui.open); }

export function openTune() { ui.open = true; ui.edits = {}; ui.msg = ""; ui.failed = null; render(); ui.actions.onOpen(true); }
export function closeTune() { if (!ui || !ui.open) return; ui.open = false; render(); ui.actions.onOpen(false); }

export function updateTune(state) { ui.state = state; if (ui.open) render(); }

function groupsOf(params) {
  const out = new Map();
  for (const p of params) {
    if (!out.has(p.group)) out.set(p.group, []);
    out.get(p.group).push(p);
  }
  return [...out.entries()];
}

function rowEl(p) {
  const r = sliderRange(p);
  const cur = Object.prototype.hasOwnProperty.call(ui.edits, p.name) ? ui.edits[p.name] : p.value;
  const range = h("input", { type: "range", min: String(Math.min(r.min, cur)), max: String(Math.max(r.max, cur)), step: String(r.step), value: String(cur),
    "aria-label": p.label, disabled: ui.working });
  const num = h("input", { type: "number", value: fmtNum(cur), step: String(r.step), "aria-label": `${p.label}的数值`, disabled: ui.working });
  const set = (v) => { ui.edits[p.name] = v; range.value = String(v); num.value = fmtNum(v); mark(); };
  range.addEventListener("input", () => set(Number(range.value)));
  num.addEventListener("change", () => {
    const v = validateEdit(p, num.value);
    if (v.ok) set(v.value);
    else { num.value = fmtNum(cur); ui.msg = v.message; footer(); }
  });
  const row = h("div", { class: "prow", dataset: { name: p.name } }, h("label", { title: p.name }, p.label), range, num,
    h("small", {}, UNIT[p.unit] ?? p.unit), h("span", { class: "tag" }, SOURCE[p.source] || ""));
  return row;
}

function mark(keep = false) {
  const changed = pendingChanges(ui.state.params_view || [], ui.edits);
  for (const row of document.querySelectorAll(".prow")) row.classList.toggle("changed", row.dataset.name in changed);
  const n = Object.keys(changed).length;
  if (n || !keep) ui.msg = n ? `改了 ${n} 处，点"应用"才会真正重做` : "还没有改动";
  footer();
}

function footer() {
  const f = $("tune-footer");
  if (!f) return;
  const changed = Object.keys(pendingChanges((ui.state && ui.state.params_view) || [], ui.edits)).length;
  clear(f,
    h("span", { class: "st", role: "status" }, ui.msg),
    ui.failed ? h("button", { type: "button", class: "btn-glass", onclick: askModel }, "让模型帮我处理") : null,
    h("button", { type: "button", class: "btn-glass", disabled: ui.working || !changed, onclick: () => { ui.edits = {}; ui.failed = null; render(); } }, "还原"),
    h("button", { type: "button", class: "btn-primary", disabled: ui.working || !changed, onclick: apply }, "应用"));
}

function askModel() {
  const params = ui.state.params_view || [];
  const text = Object.entries(ui.failed).map(([n, v]) => {
    const p = params.find((x) => x.name === n);
    return `${p ? p.label : n}改成 ${fmtNum(v)}${p ? (UNIT[p.unit] ?? "") : ""}`;
  }).join("，");
  closeTune();
  ui.actions.send(`${text}。直接改没有全部通过，请帮我看看怎么改才行。`);
}

async function apply() {
  const values = pendingChanges(ui.state.params_view || [], ui.edits);
  if (!Object.keys(values).length) return;
  ui.working = true;
  ui.msg = "正在从头重做、再量一遍……";
  render();
  const r = await ui.actions.applyParams(values);
  ui.working = false;
  if (r.ok) {
    ui.edits = {};
    ui.failed = null;
    ui.msg = `已存为第 ${String(r.version || "").replace(/^v/, "")} 版`;
  } else {
    ui.failed = r.busy ? null : values;
    ui.msg = r.busy ? BUSY : FAILED;
  }
  render();
}

function render() {
  const el = $("tune");
  el.classList.toggle("on", ui.open);
  el.setAttribute("aria-hidden", String(!ui.open));
  if (!ui.open) return;
  const s = ui.state || {};
  const params = s.params_view || [];
  const blocked = !(s.versions || []).length ? NOT_YET : s.busy ? BUSY : null;
  clear(el,
    h("header", {}, h("h2", {}, "调参数"), h("span", {}, NOTE),
      h("button", { type: "button", class: "x", "aria-label": "收起", onclick: closeTune }, "×")),
    blocked ? h("p", { class: "mute" }, blocked)
      : h("div", { class: "groups" }, groupsOf(params).map(([g, items]) => h("div", { class: "group" }, h("h3", {}, g), items.map(rowEl)))),
    blocked ? null : h("footer", { id: "tune-footer" }));
  if (!blocked) { if (!ui.msg) ui.msg = "还没有改动"; mark(true); }
}
