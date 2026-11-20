// 启动和路由：取启动信息、主题、会话列表；打开一个会话 = 取完整状态 + 从它的 last_seq 订阅事件。
// 事件流断了：顶栏下面显示"连接断开，正在重试"；接上以后先取一次完整状态，再接着收事件（store 按 seq 去重）。
import { configure, del, fileUrl as versionFileUrl, get, isStatic, post, subscribe } from "./api.js";
import { renderBench, showTab } from "./bench.js";
import { renderChecks } from "./bench-checks.js";
import { renderModel, viewVersion } from "./bench-model.js";
import { renderParams } from "./bench-params.js";
import { renderVersions } from "./bench-versions.js";
import { renderTitleblock } from "./titleblock.js";
import { renderCases } from "./cases.js";
import { renderChat } from "./chat.js";
import { renderOnboarding } from "./onboarding.js";
import { renderSettings } from "./settings.js";
import { $, clear, h, button, toast, icon } from "./dom.js";
import { applyEvent, dispatch, emptyState, getState, onChange, setState } from "./store.js";
import { renderSidebar } from "./sidebar.js";
import { THEME_LABELS, applyTheme, currentTheme, nextTheme, saveTheme } from "./theme.js";

const LAST_KEY = "datum.lastSession";
export const app = { boot: null, sessions: [], currentId: null, renaming: null, unsubscribe: null, retrying: false };
const views = [];
const pages = {};

// 别的模块（对话栏、工作台、各个整页）在这里登记自己
export function registerView(render) {
  views.push(render);
}
export function registerPage(name, render) {
  pages[name] = render;
}

function remember(id) {
  try {
    localStorage.setItem(LAST_KEY, id);
  } catch { /* 存不了就算了：下次打开第一个会话 */ }
}
function remembered() {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

// ---- 会话 ----
export async function refreshSessions() {
  const { status, body } = await get("/api/sessions");
  if (status === 200) app.sessions = body;
  renderSide();
}

function renderSide() {
  renderSidebar($("sidebar"), app.sessions, { currentId: app.currentId, renaming: app.renaming }, sideActions);
}

async function loadState(id = app.currentId) {
  const { status, body } = await get(`/api/sessions/${encodeURIComponent(id)}/state`);
  if (id !== app.currentId) return null;   // 回来得太晚：用户已经切到别的会话了
  if (status !== 200) {
    toast(body.error);
    return null;
  }
  setState(applyEvent(emptyState(), { type: "state", state: body, seq: body.last_seq }));
  return body;
}

export async function openSession(id) {
  closePage();
  app.currentId = id;
  remember(id);
  renderSide();
  await resubscribe(id);
}

// 先停掉事件流，取一次完整状态，再从它的 last_seq 接着订阅：这样中间的事件既不会丢，也不会被完整状态盖掉
async function resubscribe(id) {
  if (app.unsubscribe) app.unsubscribe();
  app.unsubscribe = null;
  const st = await loadState(id);
  if (!st || app.currentId !== id || app.unsubscribe) return;
  app.unsubscribe = subscribe(id, st.last_seq, onEvent, onStatus);
}

function onEvent(ev) {
  dispatch(ev);
  if (ev.type === "state" || ev.type === "turn_end") refreshSessions();
  if (getState().needResync) resubscribe(app.currentId);
}

function onStatus(s) {
  if (s === "retrying") {
    app.retrying = true;
    $("conn").classList.remove("hidden");
  } else if (s === "open" && app.retrying) {
    app.retrying = false;
    $("conn").classList.add("hidden");
    resubscribe(app.currentId);
    refreshSessions();
  }
}

export async function createSession(firstMessage = null) {
  const { status, body } = await post("/api/sessions", {});
  if (status !== 200) return toast(body.error);
  await refreshSessions();
  await openSession(body.id);
  if (firstMessage) await sendMessage(firstMessage);
}

export async function sendMessage(text) {
  const { status, body } = await post(`/api/sessions/${encodeURIComponent(app.currentId)}/message`, { text });
  if (status !== 200) toast(body.error);
  return status === 200;
}

export async function stopTurn() {
  await post(`/api/sessions/${encodeURIComponent(app.currentId)}/stop`, {});
}

export function fileUrl(version, name) {
  return versionFileUrl(app.currentId, version, name);
}

export async function reveal(version) {
  const { status, body } = await post(`/api/sessions/${encodeURIComponent(app.currentId)}/reveal`, { version });
  if (status !== 200) toast(body.error);
}

const chatActions = { send: (t) => sendMessage(t), stop: () => stopTurn(), reveal: (v) => reveal(v), fileUrl: (v, n) => fileUrl(v, n) };
registerView((state) => renderChat($("chat"), state, chatActions));

const sid = () => encodeURIComponent(app.currentId);
const benchActions = {
  fileUrl: (v, n) => fileUrl(v, n),
  focusInput: () => document.querySelector(".composer-input")?.focus(),
  send: (t) => sendMessage(t),
  toast,
  reveal: (v) => reveal(v),
  showModel: (v) => { showTab("model"); viewVersion(v); },
  modelName: () => modelName(),
  applyParams: async (values) => {
    const { status, body } = await post(`/api/sessions/${sid()}/params`, { values });
    if (status === 409) return { ok: false, busy: true, text: body.error };
    return status === 200 ? body : { ok: false, text: body.error, failed_checks: [] };
  },
  diff: async (a, b) => {
    const { status, body } = await get(`/api/sessions/${sid()}/diff?a=${a}&b=${b}`);
    return status === 200 ? body.lines : { error: body.error };
  },
  saveCase: async (title, tags) => {
    const { status, body } = await post(`/api/sessions/${sid()}/case`, { title, tags });
    toast(status === 200 ? "已存为案例，可以在案例库里看到。" : body.error);
  },
};
registerView((state) => renderBench($("bench"), state, {
  model: (panel, s) => renderModel(panel, s, benchActions),
  checks: (panel, s) => renderChecks(panel, s, benchActions),
  params: (panel, s) => renderParams(panel, s, benchActions),
  versions: (panel, s) => renderVersions(panel, s, benchActions),
  titleblock: (slot, s) => renderTitleblock(slot, s, benchActions),
}));

const pageActions = {
  boot: () => app.boot,
  setBoot: (b) => { app.boot = b; renderTop(getState()); },
  toast,
  close: () => backToSession(),
  openDemo: () => { const d = app.sessions.find((x) => x.demo); if (d) openSession(d.id); else backToSession(); },
  start: () => createSession(),
};
registerPage("onboarding", (el) => renderOnboarding(el, pageActions));
registerPage("settings", (el) => renderSettings(el, pageActions));
registerPage("cases", (el) => renderCases(el, pageActions));

function backToSession() {
  if (app.currentId) {
    closePage();
    renderSide();
    return;
  }
  const mine = app.sessions.find((x) => !x.demo);
  if (mine) openSession(mine.id);
  else createSession();
}

function modelName() {
  const b = app.boot;
  if (!b) return "";
  const p = (b.providers || []).find((x) => x.id === b.settings.provider);
  return b.settings.model || (p && p.models[0]) || "";
}

const sideActions = {
  open: (id) => openSession(id),
  create: () => createSession(),
  startRename: (id) => { app.renaming = id; renderSide(); },
  stopRename: () => { app.renaming = null; setTimeout(renderSide, 0); },
  rename: async (id, title) => {
    const { status, body } = await post(`/api/sessions/${encodeURIComponent(id)}/rename`, { title });
    if (status !== 200) toast(body.error);
    await refreshSessions();
    if (id === app.currentId) resubscribe(id);
  },
  remove: async (id) => {
    const { status, body } = await del(`/api/sessions/${encodeURIComponent(id)}`);
    if (status !== 200) return toast(body.error);
    await refreshSessions();
    if (id === app.currentId) {
      const next = app.sessions.find((s) => !s.demo);
      if (next) openSession(next.id);
      else createSession();
    }
  },
  cases: () => openPage("cases"),
};

// ---- 整页（设置、案例库、引导） ----
export function openPage(name, arg) {
  const render = pages[name];
  if (!render) return toast("这一页还没有做好。");
  document.body.classList.add("on-page");
  const el = $("page");
  el.classList.remove("hidden");
  clear(el);
  render(el, arg);
}

export function closePage() {
  document.body.classList.remove("on-page");
  $("page").classList.add("hidden");
  clear($("page"));
}

// ---- 顶栏和主题 ----
function renderTop(state) {
  $("top-title").textContent = state.session ? state.session.title : "";
  const t = currentTheme();
  const btn = $("theme-btn");
  btn.textContent = `外观：${THEME_LABELS[t]}`;
  btn.setAttribute("aria-label", `外观：${THEME_LABELS[t]}，点一下切换`);
}

// ---- 启动 ----
function fatal(text) {
  clear($("app"), h("div", { class: "fatal" }, h("p", {}, text), h("p", { class: "muted" }, "关掉这个窗口，重新打开 Datum 再试。")));
}

async function start() {
  configure({ token: new URLSearchParams(window.location.search).get("t") || "", tokenHeader: document.documentElement.dataset.tokenHeader || "" });
  $("brand-mark").append(icon("brand"));
  $("theme-btn").addEventListener("click", () => saveTheme(nextTheme(currentTheme())).then(() => renderTop(getState())));
  $("settings-btn").addEventListener("click", () => openPage("settings"));
  if (isStatic()) {
    // 在线示例：只有一个只读的示例会话；没有设置和引导，右上角换成回主页安装的链接
    document.body.classList.add("static-mode");
    $("settings-btn").replaceWith(h("a", { class: "btn btn-text", href: "../" }, "安装 Datum"));
  }
  onChange((state) => {
    renderTop(state);
    for (const render of views) render(state);
  });
  const { status, body } = await get("/api/boot");
  if (status !== 200) return fatal(body.error);
  app.boot = body;
  applyTheme(body.settings.theme);
  renderTop(getState());
  await refreshSessions();
  if (isStatic()) return app.sessions.length ? openSession(app.sessions[0].id) : fatal(body.error || "在线示例的数据没有加载出来。");
  const mine = app.sessions.filter((s) => !s.demo);
  if (!mine.length && !body.ready && pages.onboarding) return openPage("onboarding");
  const last = remembered();
  const pick = app.sessions.find((s) => s.id === last) || mine[0];
  if (pick) return openSession(pick.id);
  return createSession();
}

export { button };
start();
