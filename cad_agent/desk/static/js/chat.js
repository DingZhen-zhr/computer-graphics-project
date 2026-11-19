// 中栏：顶部的阶段刻度、对话记录（逐字输出、工具树、各种卡片）、底部输入框（运行时变成"停止"）。
// 对话记录按项缓存：内容没变的项不重画，所以正在填的回答、展开的阶段、滚动位置都不会跳。
import { troubleCard, confirmCard, deliveredCard, questionCard } from "./cards.js";
import { button, clear, h, icon } from "./dom.js";
import { treeLines } from "./tooltree.js";

const EMPTY = "说说你想做什么零件。不用一次说全，缺的尺寸我会问你。";
const EXAMPLES = ["做一个放在桌上看视频的手机支架", "做一个法兰盘，外径 120，上面一圈 6 个螺栓孔", "做一个装电路板的小盒子，外形 80×50×30"];
const PLACEHOLDER = "说说要做什么，或者要怎么改";
const DEMO_NOTE = '这是一段录制好的示例，只能看。想自己做一个，点左上角的"新会话"。';
const FLOW = [["clarify", "澄清"], ["confirm", "确认"], ["planning", "规划"], ["modeling", "建模"], ["delivered", "交付"]];

let ui = null;   // 这一栏的元素和缓存

function setup(root, actions) {
  const input = h("textarea", { class: "composer-input", rows: "2", placeholder: PLACEHOLDER, "aria-label": "给助手的消息" });
  const sendBtn = button("发送", null, { class: "btn composer-send" });
  const note = h("p", { class: "composer-note muted small" });
  const list = h("div", { class: "messages", role: "log", "aria-live": "polite", "aria-label": "对话记录" });
  const ruler = h("div", { class: "progress" });
  ui = { root, input, sendBtn, note, list, ruler, actions, cache: [], expanded: new Map(), state: null, sessionId: null };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      submit();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    syncComposer();
  });
  sendBtn.addEventListener("click", () => (ui.state && ui.state.busy ? actions.stop() : submit()));
  clear(root, ruler, list, h("div", { class: "composer" }, h("div", { class: "composer-row" }, input, sendBtn), note));
}

async function submit() {
  const text = ui.input.value.trim();
  if (!text || !ui.state || ui.state.busy || (ui.state.session && ui.state.session.demo)) return;
  if (await ui.actions.send(text)) {
    ui.input.value = "";
    ui.input.style.height = "auto";
  }
}

// ---- 阶段刻度：有计划时是 S1…Sn，没有计划时是五步流程 ----
function renderRuler(state) {
  const plan = state.plan;
  let ticks;
  let caption;
  if (plan && plan.stages && plan.stages.length) {
    ticks = plan.stages.map((s) => ({ label: s.id.toUpperCase(), done: s.passed, current: s.id === plan.current, title: s.title }));
    const cur = plan.stages.find((s) => s.id === plan.current);
    caption = cur ? `${cur.id.toUpperCase()} ${cur.title}` : "全部阶段已通过";
  } else {
    const at = FLOW.findIndex(([k]) => k === state.phase);
    ticks = FLOW.map(([, label], i) => ({ label, done: i < at, current: i === at, title: label }));
    caption = "";
  }
  if (state.session && state.session.demo) caption = "录制于 1.1 版，只读的真实录制";
  clear(ui.ruler,
    h("ol", { class: "ruler", "aria-label": plan ? "阶段进度" : "流程进度" },
      ticks.map((t) => h("li", { class: `tick${t.done ? " done" : ""}${t.current ? " current" : ""}`, title: t.title,
        "aria-current": t.current ? "step" : null }, h("span", { class: "tick-mark" }), h("span", { class: "tick-label" }, t.label)))),
    caption ? h("span", { class: "ruler-caption" }, caption) : null);
}

// ---- 工具树 ----
function treeEl(work, key) {
  const expanded = ui.expanded.get(key) || new Set();
  return h("div", { class: "tree" }, treeLines(work, expanded).map((line) => {
    const toggle = line.expandable ? () => {
      const set = new Set(expanded);
      if (set.has(line.stage)) set.delete(line.stage);
      else set.add(line.stage);
      ui.expanded.set(key, set);
      ui.cache = ui.cache.filter((c) => c.key !== key);
      render(ui.state, true);
    } : null;
    const inner = [h("span", { class: "tree-mark" }, line.mark), h("span", { class: "tree-text" }, line.text),
      line.detail ? h("span", { class: "tree-detail" }, line.detail) : null];
    const cls = `tree-line d${line.depth} ${line.state}`;
    if (toggle) {
      return h("button", { type: "button", class: `${cls} tree-toggle`, "aria-expanded": line.collapsed ? "false" : "true", onclick: toggle }, inner);
    }
    return h("div", { class: cls }, line.state === "running" ? h("span", { class: "spin", role: "img", "aria-label": "正在运行" }) : null, inner);
  }));
}

// ---- 每一项 ----
function itemEl(item, i, ctx) {
  if (item.role === "user") return h("div", { class: "msg user" }, h("p", {}, item.text));
  if (item.role === "work") return h("div", { class: "msg work" }, treeEl(item, `w${i}`));
  if (item.role === "live") {
    return h("div", { class: "msg live" },
      item.replies.map((r) => h("p", { class: "assistant-text" }, r)),
      item.work.stages.length || item.work.loose.length ? treeEl(item.work, `live${i}`) : null,
      item.streaming ? h("p", { class: "assistant-text streaming" }, item.streaming) : null,
      !item.streaming && !item.work.stages.length && !item.work.loose.length ? h("p", { class: "thinking muted" }, "正在想") : null);
  }
  const latest = i === ctx.lastAssistant;
  const c = { ...ctx, canAnswer: latest && ctx.canAnswer };
  if (item.kind === "question") return questionCard(item, c);
  if (item.kind === "confirm") return confirmCard(item, c);
  if (item.kind === "delivered") return deliveredCard(item, c);
  if (item.kind === "failed" || item.kind === "stopped" || item.kind === "error") return troubleCard(item, c);
  return h("div", { class: "msg assistant" }, h("p", { class: "assistant-text" }, item.text));
}

function emptyEl(ctx) {
  return h("div", { class: "empty" }, h("p", {}, EMPTY),
    h("ul", { class: "examples" }, EXAMPLES.map((t) => h("li", {}, button(t, () => ctx.send(t), { kind: "text" })))));
}

function syncComposer() {
  const s = ui.state;
  const demo = !!(s && s.session && s.session.demo);
  const busy = !!(s && s.busy);
  ui.input.disabled = demo || !s || !s.session;
  ui.note.textContent = demo ? DEMO_NOTE : busy ? '正在运行。点"停止"可以中途停下，已经写好的内容会保留。' : "Enter 发送，Shift + Enter 换行";
  clear(ui.sendBtn, busy ? [icon("stop"), "停止"] : "发送");
  ui.sendBtn.disabled = demo || (!busy && !ui.input.value.trim());
  ui.sendBtn.setAttribute("aria-label", busy ? "停止这一轮" : "发送");
}

export function renderChat(root, state, actions, force = false) {
  if (!ui || ui.root !== root) setup(root, actions);
  render(state, force);
}

function render(state, force) {
  const sessionId = state.session ? state.session.id : null;
  if (sessionId !== ui.sessionId) {
    ui.cache = [];
    ui.expanded = new Map();
    ui.sessionId = sessionId;
    ui.input.value = "";
  }
  ui.state = state;
  const atBottom = ui.list.scrollHeight - ui.list.scrollTop - ui.list.clientHeight < 48;
  renderRuler(state);
  syncComposer();
  const t = state.transcript || [];
  const lastUser = [...t].reverse().find((x) => x.role === "user");
  let lastAssistant = -1;
  t.forEach((x, i) => { if (x.role === "assistant") lastAssistant = i; });
  const demo = !!(state.session && state.session.demo);
  const ctx = { ...ui.actions, demo, lastAssistant, lastUserText: lastUser ? lastUser.text : "", canAnswer: !state.busy && !demo };
  const fresh = [];
  const ctxKey = `${ctx.canAnswer}|${lastAssistant}`;
  t.forEach((item, i) => {
    const key = `${i}|${JSON.stringify(item)}|${ctxKey}`;
    const hit = !force && ui.cache[i] && ui.cache[i].key === key ? ui.cache[i] : null;
    fresh.push(hit || { key, el: itemEl(item, i, ctx) });
  });
  ui.cache = fresh;
  if (!t.length && !demo) clear(ui.list, emptyEl(ctx));
  else if (ui.list.children.length !== fresh.length || fresh.some((c, i) => ui.list.children[i] !== c.el)) clear(ui.list, fresh.map((c) => c.el));
  if (atBottom) ui.list.scrollTop = ui.list.scrollHeight;
}
