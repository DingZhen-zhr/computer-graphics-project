// 工作台·模型：3D 视图、工具条（线框、重置视角、截图）、版本下拉、下面一条阶段刻度（点一个刻度看那个阶段的零件）。
// 正在建模、还没有版本时，看 current 的各阶段 STL，新阶段通过时自动切过去。WebGL 不可用或 STL 加载失败时退回截图并说明。
import { button, clear, h } from "./dom.js";
import { onThemeChange } from "./theme.js";
import { createViewer } from "./viewer.js";
import { NO_WEBGL } from "./viewer-dims.js";

const EMPTY = "还没有模型。在对话里说说要做什么零件，第一个阶段通过后，这里就能转着看。";
const DONE = "完成";
let ui = null;

function setup(panel, actions) {
  const viewport = h("div", { class: "viewport" });
  const shot = h("img", { class: "shot hidden", alt: "模型截图" });
  const note = h("p", { class: "viewer-note hidden", role: "status" });
  const empty = h("div", { class: "bench-empty hidden" }, h("p", {}, EMPTY), button("去对话里说", () => actions.focusInput(), { kind: "text" }));
  const select = h("select", { class: "version-select", "aria-label": "看哪个版本" });
  const wireBtn = button("线框", () => { ui.wire = !ui.wire; ui.viewer.setWireframe(ui.wire); syncTools(); }, { small: true, "aria-pressed": "false" });
  const resetBtn = button("重置视角", () => ui.viewer.resetView(), { small: true });
  const shotBtn = button("截图", () => { ui.mode = ui.mode === "shot" ? "3d" : "shot"; show(); }, { small: true, "aria-pressed": "false" });
  const ruler = h("div", { class: "stage-ruler" });
  select.addEventListener("change", () => {
    ui.version = select.value;
    ui.stage = null;
    ui.pinned = select.value !== ui.latest;
    update();
  });
  clear(panel,
    h("div", { class: "model-bar" }, h("div", { class: "model-tools" }, wireBtn, resetBtn, shotBtn), select),
    h("div", { class: "model-stage" }, viewport, shot, note, empty),
    ruler);
  ui = { panel, actions, viewport, shot, note, empty, select, wireBtn, shotBtn, ruler, mode: "3d", wire: false, version: null,
    stage: null, pinned: false, latest: null, url: null, fallback: null, state: null, sessionId: null, counts: "" };
  ui.viewer = createViewer(viewport, { onFallback: (why) => { ui.fallback = why; show(); } });
  onThemeChange(() => ui.viewer.setTheme());
}

function syncTools() {
  ui.wireBtn.setAttribute("aria-pressed", String(ui.wire));
  ui.shotBtn.setAttribute("aria-pressed", String(ui.mode === "shot"));
  ui.wireBtn.disabled = !ui.viewer.ok || ui.mode === "shot" || !!ui.fallback;
}

// 现在要看什么：{source: "版本名" | "current", stages, url, png}
function target(state) {
  const versions = state.versions || [];
  const fileUrl = ui.actions.fileUrl;
  if (versions.length) {
    const v = versions.find((x) => x.name === ui.version) || versions[versions.length - 1];
    const stl = ui.stage ? fileUrl(v.name, `stages/${ui.stage}.stl`) : v.has_stl ? fileUrl(v.name, "model.stl") : null;
    return { source: v.name, stages: v.stages || [], withDone: true, url: stl, png: v.has_png === false ? null : fileUrl(v.name, "view.png") };
  }
  const files = state.stage_files || [];
  if (!files.length) return null;
  const sid = ui.stage && files.includes(ui.stage) ? ui.stage : files[files.length - 1];
  return { source: "current", stages: files, withDone: false, url: fileUrl("current", `stages/${sid}.stl`), png: null, sid };
}

function show() {
  const t = ui.target;
  const has = !!t;
  ui.empty.classList.toggle("hidden", has);
  const useShot = has && (ui.mode === "shot" || !!ui.fallback || !t.url);
  const canShot = useShot && t && t.png;
  ui.viewport.classList.toggle("hidden", !has || useShot);
  ui.shot.classList.toggle("hidden", !canShot);
  if (canShot && ui.shot.getAttribute("src") !== t.png) ui.shot.src = t.png;
  const why = has && ui.mode !== "shot" ? ui.fallback || (!t.url ? "这个版本没有三维模型文件，先用截图代替。" : null) : null;
  ui.note.textContent = why || "";
  ui.note.classList.toggle("hidden", !why);
  syncTools();
}

function renderRuler(t) {
  if (!t || !t.stages.length) return clear(ui.ruler);
  const ticks = t.stages.map((sid) => [sid, sid.toUpperCase()]);
  if (t.withDone) ticks.push([null, DONE]);
  const current = t.source === "current" ? t.sid : ui.stage;
  clear(ui.ruler, h("ol", { class: "ruler wide", "aria-label": "阶段回看" }, ticks.map(([sid, label]) => {
    const on = sid === current;
    return h("li", { class: `tick done${on ? " current" : ""}` },
      h("button", { type: "button", class: "tick-btn", "aria-pressed": String(on), "aria-label": sid ? `看 ${label} 结束时的零件` : "看完成的零件",
        onclick: () => { ui.stage = sid; update(); } }, h("span", { class: "tick-mark" }), h("span", { class: "tick-label" }, label)));
  })));
}

function update() {
  const state = ui.state;
  const versions = state.versions || [];
  ui.latest = versions.length ? versions[versions.length - 1].name : null;
  if (!ui.pinned || !versions.some((v) => v.name === ui.version)) ui.version = ui.latest;
  clear(ui.select, versions.map((v) => h("option", { value: v.name, selected: v.name === ui.version }, v.name === ui.latest ? `${v.name}（最新）` : v.name)));
  ui.select.disabled = versions.length < 2;
  ui.select.classList.toggle("hidden", !versions.length);
  ui.target = target(state);
  renderRuler(ui.target);
  const url = ui.target && ui.target.url && ui.mode === "3d" ? ui.target.url : null;
  if (url && url !== ui.url && ui.viewer.ok) {
    ui.url = url;
    ui.fallback = null;
    ui.viewer.load(url).then((ok) => { if (ok) { ui.fallback = null; show(); } });
  }
  show();
}

export function renderModel(panel, state, actions) {
  if (!ui || ui.panel !== panel) setup(panel, actions);
  const sid = state.session ? state.session.id : null;
  const counts = `${(state.versions || []).length}|${(state.stage_files || []).join(",")}`;
  if (sid !== ui.sessionId) {
    Object.assign(ui, { sessionId: sid, version: null, stage: null, pinned: false, url: null, counts,
      fallback: ui.viewer.ok ? null : NO_WEBGL });   // 没有 WebGL 时这条说明要一直留着
  } else if (counts !== ui.counts) {
    Object.assign(ui, { stage: null, pinned: false, counts });   // 新版本或新阶段通过：自动切过去
  }
  ui.state = state;
  update();
}

export function viewVersion(name) {
  if (!ui) return;
  ui.version = name;
  ui.pinned = true;
  ui.stage = null;
  update();
}
