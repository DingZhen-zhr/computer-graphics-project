// 启动和路由：取启动信息、主题、会话列表；打开一个会话 = 取完整状态 + 从它的 last_seq 订阅事件。
// 事件流断了：顶栏下面显示"连接断开，正在重试"；接上以后先取一次完整状态，再接着收事件（store 按 seq 去重）。
import { configure, del, get, post, subscribe, tokenParam } from "./api.js";
import { $, clear, h, button, toast, icon } from "./dom.js";
import { applyEvent, dispatch, emptyState, getState, onChange, setState } from "./store.js";
import { renderSidebar } from "./sidebar.js";
import { THEME_LABELS, applyTheme, currentTheme, nextTheme, saveTheme } from "./theme.js";

const LAST_KEY = "caliper.lastSession";
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

async function loadState() {
  const { status, body } = await get(`/api/sessions/${encodeURIComponent(app.currentId)}/state`);
  if (status !== 200) {
    toast(body.error);
    return null;
  }
  setState(applyEvent(emptyState(), { type: "state", state: body, seq: body.last_seq }));
  return body;
}

export async function openSession(id) {
  closePage();
  if (app.unsubscribe) app.unsubscribe();
  app.unsubscribe = null;
  app.currentId = id;
  remember(id);
  renderSide();
  const st = await loadState();
  if (!st || app.currentId !== id) return;
  app.unsubscribe = subscribe(id, st.last_seq, onEvent, onStatus);
}

function onEvent(ev) {
  dispatch(ev);
  if (ev.type === "state" || ev.type === "turn_end") refreshSessions();
  if (getState().needResync) loadState();
}

function onStatus(s) {
  if (s === "retrying") {
    app.retrying = true;
    $("conn").classList.remove("hidden");
  } else if (s === "open" && app.retrying) {
    app.retrying = false;
    $("conn").classList.add("hidden");
    loadState();
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
  return `/files/${encodeURIComponent(app.currentId)}/${version}/${name}?${tokenParam()}`;
}

export async function reveal(version) {
  const { status, body } = await post(`/api/sessions/${encodeURIComponent(app.currentId)}/reveal`, { version });
  if (status !== 200) toast(body.error);
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
    if (id === app.currentId) loadState();
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
  clear($("app"), h("div", { class: "fatal" }, h("p", {}, text)));
}

async function start() {
  configure({ token: new URLSearchParams(window.location.search).get("t") || "" });
  $("brand-mark").append(icon("caliper"));
  $("theme-btn").addEventListener("click", () => saveTheme(nextTheme(currentTheme())).then(() => renderTop(getState())));
  $("settings-btn").addEventListener("click", () => openPage("settings"));
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
  const mine = app.sessions.filter((s) => !s.demo);
  if (!mine.length && !body.ready && pages.onboarding) return openPage("onboarding");
  const last = remembered();
  const pick = app.sessions.find((s) => s.id === last) || mine[0];
  if (pick) return openSession(pick.id);
  return createSession();
}

export { button };
start();
