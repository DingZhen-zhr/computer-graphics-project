// 页面的主程序：每秒读一次 /api/state，内容变了才重画；发消息、确认、重置、选版本都在这里接线。

import { clear, fileUrl, h, yuan } from "./dom.js";
import { renderChat, renderProgress } from "./chat.js";
import { renderBrief, renderChecks, renderVersions } from "./panels.js";

const $ = (id) => document.getElementById(id);
const POLL_MS = 1000;

const ui = {
  selected: [],            // 04 版本里选中的版本（最多两个）
  diffs: new Map(),        // "v1|v2" → {changes} | "loading" | "error"
  forceImage: false,       // 用户点了"切换到截图"
  wireframe: false,
  shownKey: null,          // 3D 里当前正在显示（或正在加载）的 "版本|有无STL"
  failedKey: null,         // 加载失败的那个 key，失败后退回截图
};
let state = null;
let lastJson = "";
let viewer = null;         // viewer.js 的 Viewer；three.js 或 WebGL 不可用时是 null
let timer = null;
let noticeTimer = null;

// ---------------------------------------------------------------- 小提示（顶栏下面的一行）

function banner(text) {
  const el = $("banner");
  el.textContent = text || "";
  el.classList.toggle("hidden", !text);
}

function notice(text) {
  banner(text);
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { banner(""); noticeTimer = null; }, 3500);
}

// ---------------------------------------------------------------- 读状态

async function poll() {
  clearTimeout(timer);
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const text = await res.text();
    if (!noticeTimer) banner("");
    if (text !== lastJson) {   // 内容没变就不重画
      lastJson = text;
      state = JSON.parse(text);
      render();
    }
  } catch (e) {
    clearTimeout(noticeTimer);
    noticeTimer = null;
    banner("连接断开，正在重试");
  } finally {
    timer = setTimeout(poll, POLL_MS);
  }
}

// ---------------------------------------------------------------- 画面

function render() {
  const versionNames = state.versions.map((v) => v.name);
  ui.selected = ui.selected.filter((n) => versionNames.includes(n));
  renderTopbar();
  renderChat($("messages"), state, { confirm: () => send("确认"), revise: () => $("input").focus() });
  renderProgress($("progress"), state);
  renderChecks($("checks-body"), state.checks);
  renderBrief($("brief-body"), state.brief);
  renderVersionsCard();
  syncModel();
  $("send").disabled = state.busy;
}

function renderTopbar() {
  $("model-name").textContent = state.model;
  const { cost, prompt_tokens: prompt, cached_tokens: cached } = state.stats;
  const parts = [];
  if (cost !== null && prompt > 0) parts.push(`本次会话 ${yuan(cost)}`);
  else parts.push("本次会话");
  parts.push(prompt > 0 ? `缓存命中 ${Math.round((cached / prompt) * 100)}%` : "尚无用量");
  $("usage").textContent = parts.join(" · ");
}

function renderVersionsCard() {
  renderVersions($("versions-body"), state, ui, { toggle: toggleVersion });
}

function toggleVersion(name) {
  if (ui.selected.includes(name)) ui.selected = ui.selected.filter((n) => n !== name);
  else ui.selected = [...ui.selected, name].slice(-2);
  if (ui.selected.length === 2) loadDiff(...[...ui.selected].sort((a, b) => Number(a.slice(1)) - Number(b.slice(1))));
  renderVersionsCard();
  syncModel();
}

async function loadDiff(a, b) {
  const key = `${a}|${b}`;
  if (ui.diffs.has(key) && ui.diffs.get(key) !== "error") return;
  ui.diffs.set(key, "loading");
  try {
    const res = await fetch(`/api/diff?a=${a}&b=${b}`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    ui.diffs.set(key, await res.json());
  } catch (e) {
    ui.diffs.set(key, "error");
  }
  renderVersionsCard();
}

// ---------------------------------------------------------------- 01 模型

function targetVersion() {
  const names = state.versions.map((v) => v.name);
  if (!names.length) return null;
  const picked = ui.selected.length ? ui.selected[ui.selected.length - 1] : null;   // 最后点的那个
  return picked && names.includes(picked) ? picked : names[names.length - 1];
}

function syncModel() {
  const name = targetVersion();
  const empty = $("viewer-empty"), img = $("viewer-img"), note = $("viewer-note");
  const buttons = { reset: $("btn-reset-view"), wire: $("btn-wire"), image: $("btn-image") };
  if (!name) {
    empty.classList.remove("hidden");
    img.classList.add("hidden");
    note.classList.add("hidden");
    if (viewer) viewer.setVisible(false);
    Object.values(buttons).forEach((b) => { b.disabled = true; });
    return;
  }
  empty.classList.add("hidden");
  const info = state.versions.find((v) => v.name === name);
  const key = `${name}|${info.has_stl}`;
  const unavailable = !viewer || !info.has_stl || ui.failedKey === key;
  const useImage = ui.forceImage || unavailable;

  if (!useImage && ui.shownKey !== key) loadModel(name, key);
  const png = fileUrl(name, "view.png");
  if (img.getAttribute("src") !== png) img.setAttribute("src", png);
  img.classList.toggle("hidden", !useImage);
  if (viewer) viewer.setVisible(!useImage);
  note.classList.toggle("hidden", !(unavailable && !ui.forceImage));
  note.textContent = "3D 预览不可用，显示的是截图";

  buttons.reset.disabled = buttons.wire.disabled = useImage;
  buttons.image.disabled = !viewer || !info.has_stl;   // 没有 3D 可切换时，这个按钮没意义
  buttons.image.textContent = ui.forceImage ? "切换到 3D" : "切换到截图";
  buttons.image.setAttribute("aria-pressed", String(ui.forceImage));
  buttons.wire.setAttribute("aria-pressed", String(ui.wireframe));
}

async function loadModel(name, key) {
  ui.shownKey = key;
  try {
    await viewer.show(fileUrl(name, "model.stl"));
    if (ui.failedKey === key) ui.failedKey = null;
  } catch (e) {
    console.warn("3D 预览加载失败，改显示截图：", e);
    ui.failedKey = key;
  }
  if (state) syncModel();
}

async function initViewer() {
  try {
    const mod = await import("/static/viewer.js");   // 动态加载：three.js 或 WebGL 出问题，也只是退回截图，不影响别的块
    viewer = new mod.Viewer($("viewer-box"));
    viewer.setVisible(false);
  } catch (e) {
    console.warn("3D 预览不可用：", e);
    viewer = null;
  }
  if (state) syncModel();
}

// ---------------------------------------------------------------- 发消息

async function send(text) {
  text = (text || "").trim();
  if (!text || (state && state.busy)) return;
  try {
    const res = await fetch("/api/message", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    if (res.status === 202) {
      $("input").value = "";
      autosize();
      poll();   // 马上读一次，不用等下一个一秒
    } else if (res.status === 409) {
      notice("上一条还在处理，请稍等");
    } else if (res.status !== 400) {
      notice("发送失败，请再试一次");
    }
  } catch (e) {
    banner("连接断开，正在重试");
  }
}

function autosize() {
  const input = $("input");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
}

function wireEvents() {
  const input = $("input");
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {   // 输入法选字时的回车不算发送
      e.preventDefault();
      send(input.value);
    }
  });
  $("btn-reset-view").addEventListener("click", () => viewer && viewer.resetView());
  $("btn-wire").addEventListener("click", () => {
    ui.wireframe = !ui.wireframe;
    if (viewer) viewer.setWireframe(ui.wireframe);
    if (state) syncModel();
  });
  $("btn-image").addEventListener("click", () => { ui.forceImage = !ui.forceImage; if (state) syncModel(); });
  $("reset-btn").addEventListener("click", async () => {
    if (!window.confirm("开始新会话？当前的对话和版本会收起来，从头开始。")) return;
    try {
      const res = await fetch("/api/reset", { method: "POST" });
      if (res.status === 409) notice("正在处理消息，现在不能重置");
      else { ui.selected = []; ui.diffs.clear(); ui.shownKey = ui.failedKey = null; lastJson = ""; poll(); }
    } catch (e) {
      banner("连接断开，正在重试");
    }
  });
}

wireEvents();
initViewer();
poll();
