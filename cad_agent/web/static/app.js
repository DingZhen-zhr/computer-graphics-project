// 页面入口：每秒取一次 /api/state，哪一块的数据变了就只重画哪一块。

import { h, clear, fmtCost, fmtNum, fmtPercent, fmtTokens, fileUrl } from "./dom.js";
import { renderChat, tickWorking } from "./chat.js";
import { renderChecks, renderBrief, renderVersions } from "./panels.js";
import { Viewer, hydrateThumbs } from "./viewer.js";

const $ = (id) => document.getElementById(id);
const STAGES = ["clarify", "confirm", "modeling", "checking", "delivered"];
const POLL_MS = 1000;

const els = {
  rail: $("rail"), usage: $("usage-pill"), model: $("model-pill"), replay: $("replay-pill"), reset: $("reset-btn"),
  notice: $("notice"), messages: $("messages"), composer: $("composer"), input: $("input"), send: $("send"), hint: $("composer-hint"),
  partName: $("part-name"), partPurpose: $("part-purpose"), versionTag: $("version-tag"), versionTagText: $("version-tag-text"),
  modelMeta: $("model-meta"), viewport: $("viewport"), vpEmpty: $("viewport-empty"), vpNote: $("vp-note"), readout: $("vp-readout"),
  hint3d: $("vp-hint"), mode3d: $("mode-3d"), modeShot: $("mode-shot"), wire: $("wire-btn"), fit: $("fit-btn"),
  checks: $("checks"), checksMeta: $("checks-meta"), brief: $("brief"), briefMeta: $("brief-meta"),
  versions: $("versions"), versionsMeta: $("versions-meta"), toast: $("toast"),
};

let state = null;
let pending = null;           // 刚发出去、服务器还没记下的那句话
const last = {};              // 每一块上次画的数据（JSON），没变就不重画
const ui = { shown: null, follow: true, mode: "3d" };  // 3D 里显示哪个版本；是否自动跟到最新版
let viewer = null;
let shotImg = null;

// ------------------------------------------------------------------ 小工具

let toastTimer = null;
function toast(text) {
  els.toast.textContent = text;
  els.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("show"), 2600);
}

function changed(key, value) {
  const json = JSON.stringify(value);
  if (last[key] === json) return false;
  last[key] = json;
  return true;
}

async function api(path, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), options.timeout || 5000);
  try {
    const res = await fetch(path, { ...options, signal: ctrl.signal, headers: { "Content-Type": "application/json" } });
    const body = await res.json().catch(() => ({}));
    return { status: res.status, body };
  } finally {
    clearTimeout(timer);
  }
}

// ------------------------------------------------------------------ 动作

const live = () => state && state.mode === "live";

async function send(text) {
  text = (text ?? els.input.value).trim();
  if (!text || !live() || state.busy || pending) return;
  pending = text;
  last.sentAt = state.transcript.length;
  els.input.value = "";
  autosize();
  renderAll(true);
  try {
    const { status, body } = await api("/api/message", { method: "POST", body: JSON.stringify({ text }) });
    if (status !== 202) {
      pending = null;
      if (status !== 409) els.input.value = text;
      toast(body.error || "没有发出去，请再试一次");
      renderAll(true);
      return;
    }
  } catch {
    pending = null;
    els.input.value = text;
    toast("连接不上本地服务，请确认它还在运行");
    renderAll(true);
    return;
  }
  poll();
}

function answerTemplate(n) {
  els.input.value = Array.from({ length: n }, (_, i) => `${i + 1}. `).join("\n");
  autosize();
  els.input.focus();
  els.input.setSelectionRange(3, 3);
}

function focusInput() {
  els.input.focus();
}

function showVersion(name) {
  ui.shown = name;
  ui.follow = state && name === state.versions.at(-1)?.name;
  renderModel(true);
  renderVersions(els.versions, els.versionsMeta, state.versions, { shown: ui.shown, showVersion });
  hydrateThumbs(els.versions);
  document.getElementById("viewport").scrollIntoView({ behavior: "smooth", block: "center" });
}

const actions = { send, answerTemplate, focus: focusInput, showVersion };

// ------------------------------------------------------------------ 顶栏

// 分隔点跟着后面那一项：那一项在窄屏下隐藏时，分隔点也一起隐藏
const sep = (p) => h("span", { class: p?.classList?.contains("usage-tokens") ? "usage-tokens" : "" }, " · ");

function renderTop() {
  const s = state;
  els.model.textContent = s.model || "模型";
  els.replay.classList.toggle("hidden", s.mode !== "replay");
  els.reset.disabled = s.mode !== "live" || s.busy;
  const st = s.stats || {};
  const parts = [];
  const cost = fmtCost(st.cost);
  if (cost) parts.push(h("strong", {}, cost));
  if (st.prompt_tokens) parts.push(h("span", { class: "usage-tokens" }, `输入 ${fmtTokens(st.prompt_tokens)} token`));
  const ratio = fmtPercent(st.cache_ratio);
  if (ratio) parts.push(h("span", {}, "缓存命中 ", h("strong", {}, ratio)));
  clear(els.usage, parts.length ? parts.flatMap((p, i) => (i ? [sep(p), p] : [p])) : ["尚无用量"]);

  const current = STAGES.indexOf(s.stage);
  for (const li of els.rail.children) {
    const i = STAGES.indexOf(li.dataset.stage);
    li.classList.toggle("done", i < current);
    li.classList.toggle("current", i === current);
    li.classList.toggle("working", i === current && s.busy);
    li.setAttribute("aria-current", i === current ? "step" : "false");
  }
}

// ------------------------------------------------------------------ 对话

function renderComposer() {
  const disabled = !live() || state.busy || !!pending;
  els.input.disabled = !live();
  els.send.disabled = disabled || !els.input.value.trim();
  els.hint.textContent = !live()
    ? `回放模式：正在查看已保存的会话 ${state.replay_of || ""}，不能发消息`
    : state.busy ? "正在处理上一条消息，完成后可以继续说" : "Enter 发送 · Shift + Enter 换行";
}

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 180)}px`;
  if (state) renderComposer();
}

// ------------------------------------------------------------------ 01 模型

function shownVersion() {
  const versions = state.versions || [];
  if (!versions.length) return null;
  if (ui.follow || !versions.some((v) => v.name === ui.shown)) ui.shown = versions.at(-1).name;
  return versions.find((v) => v.name === ui.shown);
}

function setNote(text) {
  els.vpNote.textContent = text || "";
  els.vpNote.classList.toggle("hidden", !text);
}

function showShot(v) {
  viewer?.hide();
  if (!shotImg) {
    shotImg = h("img", { class: "shot", alt: "模型截图", onerror: () => { shotImg.classList.add("hidden"); setNote("这个版本的截图也打不开"); } });
    els.viewport.prepend(shotImg);
  }
  shotImg.src = fileUrl(v.name, "view.png");
  shotImg.classList.remove("hidden");
}

function hideShot() {
  shotImg?.classList.add("hidden");
}

function setMode(mode) {
  ui.mode = mode;
  els.mode3d.setAttribute("aria-pressed", String(mode === "3d"));
  els.modeShot.setAttribute("aria-pressed", String(mode === "shot"));
  renderModel(true);
}

function readout(size) {
  const volume = (state.checks || []).find((c) => c.id === "positive_volume")?.measured ?? state.facts?.volume;
  const sizeText = size ? size.map((x) => fmtNum(x, 1)).join(" × ") + " mm" : null;
  clear(els.readout,
    sizeText ? h("div", {}, sizeText) : null,
    volume ? h("div", { class: "sub" }, `体积 ${fmtNum(volume, 0)} mm³`) : null);
  els.readout.classList.toggle("hidden", !sizeText && !volume);
}

async function renderModel(force = false) {
  const part = state.part || {};
  const v = shownVersion();
  if (!changed("model", [part, v, ui.mode, state.checks?.length]) && !force) return;
  els.partName.textContent = part.name || "还没有零件";
  els.partName.classList.toggle("placeholder", !part.name);
  els.partPurpose.textContent = part.purpose || "在左边用一句话描述你想做的东西";
  els.versionTag.classList.toggle("hidden", !v);
  els.versionTagText.textContent = v ? `${v.name}${v.name === state.versions.at(-1)?.name ? " · 最新" : ""}` : "";
  els.modelMeta.textContent = v ? `检查 ${v.passed}/${v.total}` : "";
  els.vpEmpty.classList.toggle("hidden", !!v);
  for (const b of [els.mode3d, els.modeShot, els.wire, els.fit]) b.disabled = !v;
  els.hint3d.classList.toggle("hidden", !v || ui.mode !== "3d");
  if (!v) {
    viewer?.hide();
    hideShot();
    setNote("");
    els.readout.classList.add("hidden");
    return;
  }
  const can3d = viewer?.ok && v.has_stl;
  if (ui.mode === "shot" || !can3d) {
    if (ui.mode === "3d") setNote(!viewer?.ok ? "这台电脑不支持 WebGL，显示的是截图" : "这个版本没有 STL，显示的是截图");
    else setNote("");
    showShot(v);
    readout(viewer?.info?.size && viewer.url === fileUrl(v.name, "model.stl") ? viewer.info.size : null);
    return;
  }
  setNote("");
  hideShot();
  try {
    const info = await viewer.load(fileUrl(v.name, "model.stl"));
    viewer.show();
    readout(info.size);
  } catch (e) {
    console.warn("STL 加载失败，改用截图", e);
    setNote("3D 预览加载失败，显示的是截图");
    showShot(v);
  }
}

// ------------------------------------------------------------------ 整页

function renderAll(force = false) {
  if (!state) return;
  if (pending && state.transcript.some((t, i) => i >= (last.sentAt ?? 0) && t.role === "user" && t.text === pending)) pending = null;
  renderTop();
  const chatData = [state.transcript, state.busy, state.activity, pending, state.mode];
  if (changed("chat", chatData) || force) {
    renderChat(els.messages, state, pending, { ...actions, live: live() });
    hydrateThumbs(els.messages);
  }
  else if (state.busy) tickWorking(els.messages, state.busy_seconds);
  renderComposer();
  if (changed("checks", state.checks)) renderChecks(els.checks, els.checksMeta, state.checks);
  if (changed("brief", state.brief)) renderBrief(els.brief, els.briefMeta, state.brief);
  if (changed("versions", [state.versions, ui.shown])) {
    renderVersions(els.versions, els.versionsMeta, state.versions, { shown: shownVersion()?.name, showVersion });
    hydrateThumbs(els.versions);
  }
  renderModel(force);
  els.notice.classList.toggle("hidden", !state.error);
  els.notice.textContent = state.error || "";
}

let polling = false;
let failures = 0;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const { status, body } = await api("/api/state", { timeout: 4000 });
    if (status !== 200) throw new Error(String(status));
    if (failures) {
      els.notice.classList.add("hidden");
      toast("已重新连上");
    }
    failures = 0;
    state = body;
    renderAll();
  } catch {
    failures += 1;
    if (failures >= 2) {
      els.notice.textContent = "和本地服务的连接断开了，正在重试……";
      els.notice.classList.remove("hidden");
    }
  } finally {
    polling = false;
  }
}

// ------------------------------------------------------------------ 启动

function boot() {
  viewer = new Viewer(els.viewport, {});
  els.composer.addEventListener("submit", (e) => { e.preventDefault(); send(); });
  els.input.addEventListener("input", autosize);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  els.reset.addEventListener("click", async () => {
    if (!live() || state.busy) return;
    if (!confirm("开一个新会话？当前会话的记录和版本都会保留在会话目录里。")) return;
    const { status, body } = await api("/api/reset", { method: "POST", body: "{}" });
    if (status !== 200) return toast(body.error || "现在不能开新会话");
    ui.shown = null;
    ui.follow = true;
    for (const k of Object.keys(last)) delete last[k];
    poll();
  });
  els.mode3d.addEventListener("click", () => setMode("3d"));
  els.modeShot.addEventListener("click", () => setMode("shot"));
  els.wire.addEventListener("click", () => {
    const on = els.wire.getAttribute("aria-pressed") !== "true";
    els.wire.setAttribute("aria-pressed", String(on));
    viewer?.setWire(on);
  });
  els.fit.addEventListener("click", () => viewer?.fit());
  poll();
  setInterval(poll, POLL_MS);
}

boot();
