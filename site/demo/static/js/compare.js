// 修改前后的对比：叠在一起（b 是实体，a 是半透明轮廓）或左右并排（共用一个相机）；下面列出参数和检查的变化。
// 某一版没有三维文件时，那一边用截图代替。Esc 或"关掉对比"回到当前版本。
import { $, clear, h } from "./dom.js";
import { paramChangeText } from "./panels-logic.js";

export const NO_STL = "这个版本没有三维文件，先用截图代替。";
let ui = null;

// 两个版本里用哪个文件显示：有 STL 用 STL，没有就用截图并说明（纯逻辑）
export function compareSources(va, vb, fileUrl, product) {
  const one = (v) => {
    if (!v) return null;
    if (product) return { kind: "parts", name: v.name };
    if (v.has_stl === false) return { kind: "png", name: v.name, url: fileUrl(v.name, "view.png"), note: NO_STL };
    return { kind: "stl", name: v.name, url: fileUrl(v.name, "model.stl") };
  };
  return { a: one(va), b: one(vb) };
}

export function mountCompare(actions) { ui = { actions, open: false, mode: "overlay", data: null }; }
export const isComparing = () => !!(ui && ui.open);

export async function openCompare(a, b) {
  const r = await ui.actions.fetchCompare(a, b);
  if (r.error) { ui.actions.toast(r.error); return; }
  ui.open = true;
  ui.data = { a, b, ...r };
  await ui.actions.show(ui.data, ui.mode);
  render();
}

export function closeCompare() {
  if (!ui || !ui.open) return;
  ui.open = false;
  $("compare-bar").classList.add("gone");
  $("compare-changes").classList.add("gone");
  $("compare-split").classList.add("gone");
  ui.actions.hide();
}

function render() {
  const d = ui.data;
  const bar = $("compare-bar");
  bar.classList.remove("gone");
  const mode = (m, label) => h("button", { type: "button", class: "btn-glass btn-small", "aria-pressed": String(ui.mode === m),
    onclick: async () => { ui.mode = m; await ui.actions.show(ui.data, ui.mode); render(); } }, label);
  clear(bar, h("span", { class: "small num compare-title" }, `对比 第 ${d.a.replace(/^v/, "")} 版 → 第 ${d.b.replace(/^v/, "")} 版`),
    mode("overlay", "叠在一起"), mode("split", "左右并排"),
    h("button", { type: "button", class: "btn-primary btn-small", onclick: closeCompare }, "关掉对比"));
  $("compare-split").classList.toggle("gone", ui.mode !== "split");
  const ch = $("compare-changes");
  ch.classList.remove("gone");
  const checks = (d.checks || []).map((c) => `${c.part && c.part !== "main" ? `${c.part} · ` : ""}${c.id}：${c.a === null ? "没有" : c.a ? "通过" : "没过"} → ${c.b === null ? "没有" : c.b ? "通过" : "没过"}`);
  clear(ch, (d.params || []).length ? d.params.map((p) => h("div", { class: "num" }, paramChangeText(p))) : h("div", { class: "mute" }, "参数没有变化"),
    checks.length ? [h("div", { class: "small mute compare-sub" }, "检查的变化"), checks.map((t) => h("div", { class: "small" }, t))] : null,
    d.notes && d.notes.length ? d.notes.map((n) => h("div", { class: "small mute" }, n)) : null);
}
