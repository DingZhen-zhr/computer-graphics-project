// 启动和路由：取启动信息、主题、会话列表；打开一个会话 = 取完整状态 + 从它的 last_seq 订阅事件。
// 事件流断了：顶上显示"连接断开，正在重试"；接上以后先取一次完整状态，再接着收事件（store 按 seq 去重）。
import { configure, del, fileUrl as versionFileUrl, get, isStatic, post, subscribe } from "./api.js";
import { renderBrief } from "./brief-card.js";
import { closeCompare, isComparing, mountCompare, openCompare } from "./compare.js";
import { $, clear, h, toast } from "./dom.js";
import { closeAll, isOpen, onEscape, openDrawer, setupDrawers } from "./drawers.js";
import { renderHistory } from "./history.js";
import { renderInspector, showInspectorTab } from "./inspector.js";
import { renderMenu } from "./menu.js";
import { hideCompare, mountModelView, setShift, showCompare, showStage, updateModel } from "./model-view.js";
import { renderCases } from "./pages/cases.js";
import { renderOnboarding } from "./pages/onboarding.js";
import { renderSettings } from "./pages/settings.js";
import { focusPrompt, mountStage, renderStage } from "./stage.js";
import { applyEvent, dispatch, emptyState, getState, onChange, setState } from "./store.js";
import { THEME_LABELS, applyTheme, currentTheme, nextTheme, saveTheme } from "./theme.js";
import { closeTune, mountTune, openTune, updateTune } from "./tune.js";

const LAST_KEY = "datum.lastSession";
const app = { boot: null, sessions: [], currentId: null, unsubscribe: null, retrying: false };
const sid = () => encodeURIComponent(app.currentId);
const fileUrl = (version, name) => versionFileUrl(app.currentId, version, name);

function remember(id) { try { localStorage.setItem(LAST_KEY, id); } catch { /* 存不了就算了 */ } }
function remembered() { try { return localStorage.getItem(LAST_KEY); } catch { return null; } }

// ---- 会话 ----
async function refreshSessions() {
  const { status, body } = await get("/api/sessions");
  if (status === 200) app.sessions = body;
  renderDrawers(getState());
}

async function loadState(id = app.currentId) {
  const { status, body } = await get(`/api/sessions/${encodeURIComponent(id)}/state`);
  if (id !== app.currentId) return null;   // 回来得太晚：用户已经切到别的会话了
  if (status !== 200) { toast(body.error); return null; }
  setState(applyEvent(emptyState(), { type: "state", state: body, seq: body.last_seq }));
  return body;
}

async function openSession(id) {
  closePage();
  closeAll();
  closeTune();
  closeCompare();
  app.currentId = id;
  remember(id);
  await resubscribe(id);
}

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
  if (s === "retrying") { app.retrying = true; $("conn").classList.remove("gone"); }
  else if (s === "open" && app.retrying) { app.retrying = false; $("conn").classList.add("gone"); resubscribe(app.currentId); refreshSessions(); }
}

async function createSession(firstMessage = null) {
  const { status, body } = await post("/api/sessions", {});
  if (status !== 200) return toast(body.error);
  await refreshSessions();
  await openSession(body.id);
  if (firstMessage) await sendMessage(firstMessage);
}

async function sendMessage(text) {
  if (!app.currentId || (getState().session && getState().session.demo)) return false;
  const { status, body } = await post(`/api/sessions/${sid()}/message`, { text });
  if (status !== 200) toast(body.error);
  return status === 200;
}

// ---- 各个部件要用的动作 ----
const actions = {
  send: (t) => sendMessage(t),
  stop: () => post(`/api/sessions/${sid()}/stop`, {}),
  showStage: (id) => showStage(id),
  focusPrompt: () => focusPrompt(),
  close: () => closeAll(),
  fileUrl,
  readOnly: isStatic(),
  download: async (v, rel, filename) => {
    const { status, body } = await post(`/api/sessions/${sid()}/download`, { version: v, file: rel, filename });
    toast(status === 200 ? `已保存到“下载”文件夹：${body.name || filename}` : body.error);
  },
  reveal: async (v) => { const { status, body } = await post(`/api/sessions/${sid()}/reveal`, { version: v }); if (status !== 200) toast(body.error); },
  saveCase: async (title, tags) => {
    const { status, body } = await post(`/api/sessions/${sid()}/case`, { title, tags });
    toast(status === 200 ? "已存为案例，可以在案例库里看到。" : body.error);
  },
  compare: (name) => {
    const vs = (getState().versions || []).map((v) => v.name);
    const i = vs.indexOf(name);
    const [a, b] = i > 0 ? [vs[i - 1], name] : [name, vs[vs.length - 1]];
    if (a === b) return;
    closeAll();
    openCompare(a, b);
  },
  applyParams: async (values) => {
    const { status, body } = await post(`/api/sessions/${sid()}/params`, { values });
    if (status === 409) return { ok: false, busy: true, text: body.error };
    return status === 200 ? body : { ok: false, text: body.error, failed_checks: [] };
  },
};

const menuActions = {
  open: (id) => openSession(id),
  create: () => { closeAll(); createSession(); },
  rename: async (id, title) => { const { status, body } = await post(`/api/sessions/${encodeURIComponent(id)}/rename`, { title }); if (status !== 200) toast(body.error); await refreshSessions(); if (id === app.currentId) resubscribe(id); },
  remove: async (id) => {
    const { status, body } = await del(`/api/sessions/${encodeURIComponent(id)}`);
    if (status !== 200) return toast(body.error);
    await refreshSessions();
    if (id === app.currentId) { const next = app.sessions.find((s) => !s.demo); if (next) openSession(next.id); else createSession(); }
  },
  cases: () => { closeAll(); openPage("cases"); },
  settings: () => { closeAll(); openPage("settings"); },
  theme: () => saveTheme(nextTheme(currentTheme())).then(() => renderDrawers(getState())),
  themeLabel: () => `外观：${THEME_LABELS[currentTheme()]}`,
  close: () => closeAll(),
  readOnly: isStatic(),
};

function renderDrawers(state) {
  renderMenu($("menu"), app.sessions, app.currentId, menuActions);
  renderHistory($("history"), state, actions);
  renderInspector($("inspector"), state, actions);
}

// ---- 整页（设置、案例库、引导） ----
const pageActions = {
  boot: () => app.boot,
  setBoot: (b) => { app.boot = b; },
  toast,
  close: () => backToSession(),
  openDemo: () => { const d = app.sessions.find((x) => x.demo); if (d) openSession(d.id); else backToSession(); },
  start: () => createSession(),
};
const pages = { onboarding: renderOnboarding, settings: renderSettings, cases: renderCases };

function openPage(name) {
  const el = $("page");
  el.classList.remove("gone");
  const panel = h("div", { class: "page-panel" });
  clear(el, panel);
  pages[name](panel, pageActions);
}

function closePage() { $("page").classList.add("gone"); clear($("page")); }

function backToSession() {
  closePage();
  if (app.currentId) return;
  const mine = app.sessions.find((x) => !x.demo);
  if (mine) openSession(mine.id); else createSession();
}

// ---- 启动 ----
function fatal(text) {
  clear($("page"), h("div", { class: "fatal" }, h("p", {}, text), h("p", { class: "mute" }, "关掉这个窗口，重新打开 Datum 再试。")));
  $("page").classList.remove("gone");
}

function wire() {
  $("menu-btn").addEventListener("click", (e) => { renderDrawers(getState()); openDrawer("menu", e.currentTarget); });
  $("history-btn").addEventListener("click", (e) => { renderDrawers(getState()); openDrawer("history", e.currentTarget); });
  $("score").addEventListener("click", (e) => { showInspectorTab("checks"); renderInspector($("inspector"), getState(), actions); openDrawer("inspector", e.currentTarget); });
  $("versions-btn").addEventListener("click", (e) => { showInspectorTab("versions"); renderInspector($("inspector"), getState(), actions); openDrawer("inspector", e.currentTarget); });
  $("tune-open").addEventListener("click", () => openTune());
  onEscape(() => { closeTune(); if (isComparing()) closeCompare(); });
  setupDrawers();
}

async function start() {
  configure({ token: new URLSearchParams(window.location.search).get("t") || "", tokenHeader: document.documentElement.dataset.tokenHeader || "" });
  mountStage(actions);
  mountTune({ ...actions, onOpen: (on) => setShift(on ? 130 : 0) });
  mountCompare({ fetchCompare: async (a, b) => {
    const { status, body } = await get(`/api/sessions/${sid()}/compare?a=${a}&b=${b}`);
    return status === 200 ? body : { error: body.error };
  }, toast, show: (d, m) => showCompare(d, m), hide: () => hideCompare() });
  mountModelView(fileUrl);
  wire();
  if (isStatic()) {
    document.body.classList.add("static-mode");
    $("tune-open").replaceWith(h("a", { class: "corner tune-open glass pill", href: "../" }, "安装 Datum"));
  }
  onChange((state) => {
    const v = renderStage(state);
    renderBrief(state, v.center, actions);
    updateModel(state, v.center);
    updateTune(state);
    if (isOpen("history") || isOpen("inspector") || isOpen("menu")) renderDrawers(state);
  });
  const { status, body } = await get("/api/boot");
  if (status !== 200) return fatal(body.error);
  app.boot = body;
  applyTheme(body.settings.theme);
  await refreshSessions();
  if (isStatic()) return app.sessions.length ? openSession(app.sessions[0].id) : fatal(body.error || "在线示例的数据没有加载出来。");
  const mine = app.sessions.filter((s) => !s.demo);
  if (!mine.length && !body.ready) return openPage("onboarding");
  const pick = app.sessions.find((s) => s.id === remembered()) || mine[0];
  if (pick) return openSession(pick.id);
  return createSession();
}

start();
