// 页面的状态和事件归并。纯逻辑，不碰页面；每次都返回新对象，不改传进来的。
// 完整状态（/state 或 state 事件）整个替换；之后按 seq 只接比它新的事件，所以重连、切会话都不会重复也不会漏。
// 正在进行的一轮在 transcript 末尾放一项 {role: "live"}：逐字输出、这一轮的工具树。

export function emptyState() {
  return { session: null, busy: false, phase: "clarify", transcript: [], brief: null, plan: null, checks: [], gate: null,
    review: null, versions: [], stage_files: [], usage: {}, cost: null, last_seq: 0, pending: null, needResync: false };
}

const newLive = () => ({ role: "live", streaming: "", replies: [], work: { stages: [], loose: [] }, running: null });

function lastIsLive(s) {
  const t = s.transcript;
  return t.length > 0 && t[t.length - 1].role === "live";
}

// 改末尾的进行中那一项（没有就先加一项）
function withLive(s, fn) {
  const transcript = s.transcript.slice();
  const cur = lastIsLive(s) ? transcript.pop() : newLive();
  const live = { ...cur, work: { stages: cur.work.stages.map((x) => ({ ...x, tools: x.tools.slice() })), loose: cur.work.loose.slice() } };
  fn(live);
  transcript.push(live);
  return { ...s, transcript };
}

function stageTitle(s, id) {
  const st = s.plan && s.plan.stages ? s.plan.stages.find((x) => x.id === id) : null;
  return st ? st.title : "";
}

function stageNode(s, live, id) {
  let node = live.work.stages.find((x) => x.id === id);
  if (!node) {
    node = { id, title: stageTitle(s, id), passed: false, tools: [] };
    live.work.stages.push(node);
  }
  return node;
}

// 完整状态 → 页面状态：正在跑时，把这一轮已经有的工具树和逐字输出放进进行中的那一项
function fromFull(full, seq) {
  let s = { ...emptyState(), ...full, needResync: false, last_seq: Math.max(seq || 0, full.last_seq || 0) };
  if (!s.busy) return s;
  const transcript = s.transcript.slice();
  const live = newLive();
  const last = transcript[transcript.length - 1];
  if (last && last.role === "work") {
    transcript.pop();
    live.work = { stages: last.stages.map((x) => ({ ...x, tools: x.tools.map((t) => ({ ...t, state: t.ok ? "ok" : "bad" })) })),
      loose: last.loose.map((t) => ({ ...t, state: t.ok ? "ok" : "bad" })) };
  }
  const p = s.pending || {};
  live.streaming = p.streaming || "";
  s = { ...s, transcript: [...transcript, live] };
  if (p.running) s = addTool(s, { ...p.running });
  return s;
}

function addTool(s, ev) {
  return withLive(s, (live) => {
    const node = { id: ev.id, name: ev.name, label: ev.label, state: "running" };
    const cur = s.plan ? s.plan.current : null;
    if (cur) stageNode(s, live, cur).tools.push(node);
    else live.work.loose.push(node);
  });
}

function endTool(s, ev) {
  return withLive(s, (live) => {
    const lists = [live.work.loose, ...live.work.stages.map((x) => x.tools)];
    for (const list of lists) {
      const i = list.findIndex((t) => t.id === ev.id);
      if (i >= 0) {
        list[i] = { ...list[i], state: ev.ok ? "ok" : "bad", ok: !!ev.ok, summary: ev.summary || "" };
        return;
      }
    }
  });
}

const HANDLERS = {
  resync: (s) => ({ ...s, needResync: true }),
  turn_start: (s, ev) => {
    const transcript = s.transcript.filter((t) => t.role !== "live");
    return { ...s, busy: true, transcript: [...transcript, { role: "user", text: ev.text }, newLive()] };
  },
  delta: (s, ev) => withLive(s, (live) => { live.streaming += ev.text || ""; }),
  delta_reset: (s) => withLive(s, (live) => { live.streaming = ""; }),
  assistant: (s, ev) => withLive(s, (live) => {
    live.streaming = "";
    if (ev.content) live.replies = [...live.replies, ev.content];
  }),
  tool_start: addTool,
  tool_end: endTool,
  plan: (s, ev) => ({ ...s, plan: { stages: ev.stages, current: ev.current } }),
  stage: (s, ev) => {
    const plan = s.plan ? { ...s.plan, stages: s.plan.stages.map((x) => (x.id === ev.id ? { ...x, passed: true } : x)) } : s.plan;
    const files = s.stage_files || [];
    const next = { ...s, plan, stage_files: files.includes(ev.id) ? files : [...files, ev.id] };   // 这个阶段的 STL 已经导出了
    return withLive(next, (live) => {
      const node = stageNode(next, live, ev.id);
      node.passed = true;
      if (ev.title) node.title = ev.title;
      if (typeof ev.checks === "number") node.checks = ev.checks;
    });
  },
  gate: (s, ev) => ({ ...s, gate: { ...ev, seq: undefined, type: undefined } }),
  turn_end: (s) => ({ ...s, busy: false }),
  error: (s, ev) => ({ ...s, busy: false,
    transcript: [...s.transcript.filter((t) => t.role !== "live"), { role: "assistant", kind: "error", text: ev.message || "" }] }),
};

export function applyEvent(state, ev) {
  if (!ev || typeof ev !== "object") return state;
  if (ev.type === "state") return fromFull(ev.state || {}, ev.seq);
  const handler = HANDLERS[ev.type];
  if (!handler) return state;   // 不认识的事件：原样返回
  if (ev.seq && ev.seq <= state.last_seq && ev.type !== "resync") return state;   // 已经包含在完整状态里了
  const next = handler(state, ev);
  return ev.seq ? { ...next, last_seq: Math.max(next.last_seq, ev.seq) } : next;
}

// ---- main.js 用：当前状态和订阅 ----
let current = emptyState();
const listeners = new Set();

export function getState() {
  return current;
}

export function setState(next) {
  current = next;
  for (const fn of listeners) fn(current);
}

export function dispatch(ev) {
  const next = applyEvent(current, ev);
  if (next !== current) setState(next);
}

export function onChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
