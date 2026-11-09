// 左栏：对话记录、工作中的进度、欢迎页。只负责画，不发请求；按钮动作由 app.js 传进来。

import { h, clear, fmtCost, fmtNum, fmtPercent, fileUrl } from "./dom.js";

const SLOW_SECONDS = 45;
const KIND_LABEL = { reply: "回复", question: "提问", confirm: "请确认", delivered: "交付", failed: "停下", error: "出错" };
const SOURCE_LABEL = { user: "用户", suggested: "建议" };
const EXAMPLES = [
  "做一个放在桌上看视频的小支架",
  "帮我做一个法兰盘",
  "做一个 L 形的安装支架，要带加强筋",
];

function usageLine(entry) {
  if (!entry.llm_calls) return null;
  const parts = [`模型调用 ${entry.llm_calls} 次`];
  const cost = fmtCost(entry.cost);
  if (cost) parts.push(cost);
  const ratio = entry.prompt_tokens ? fmtPercent(entry.cached_tokens / entry.prompt_tokens) : null;
  if (ratio) parts.push(`缓存命中 ${ratio}`);
  return h("div", { class: "usage" }, parts.join(" · "));
}

function questionCard(entry, actions) {
  const qs = entry.questions || [];
  return [
    entry.lead ? h("div", { class: "text" }, entry.lead) : null,
    h("div", { class: "card" },
      h("ol", { class: "qlist" }, qs.map((q, i) => h("li", {}, h("span", { class: "qno" }, String(i + 1).padStart(2, "0")), h("span", {}, q)))),
      actions.live && actions.latest
        ? h("div", { class: "actions" }, h("button", { class: "btn btn-secondary", type: "button", onclick: () => actions.answerTemplate(qs.length) }, "逐条回答"))
        : null),
  ];
}

function confirmCard(entry, actions) {
  const params = entry.brief?.params || [];
  const body = params.length
    ? h("table", { class: "mini-params" }, h("tbody", {}, params.map((p) =>
        h("tr", {}, h("td", {}, p.name), h("td", {}, `${fmtNum(p.value)} ${p.unit === "1" ? "" : p.unit}`.trim()),
          h("td", {}, h("span", { class: `badge ${p.source}` }, SOURCE_LABEL[p.source] || p.source))))))
    : h("div", { class: "text muted" }, entry.text.split("【需求单】")[1] || entry.text);
  return [
    entry.lead ? h("div", { class: "text" }, entry.lead) : null,
    h("div", { class: "card" },
      h("div", { class: "card-title" }, h("span", { class: "square", "aria-hidden": "true" }), "需求单 · 请确认"),
      body,
      actions.live && actions.latest
        ? h("div", { class: "actions" },
            h("button", { class: "btn btn-primary", type: "button", onclick: () => actions.send("确认") }, "确认，开始建模"),
            h("button", { class: "btn btn-secondary", type: "button", onclick: () => actions.focus() }, "我要修改"))
        : null),
  ];
}

function deliveredCard(entry, actions) {
  const v = entry.version;
  const ok = entry.total !== null && entry.passed === entry.total;
  return h("div", { class: "card delivered" },
    h("img", { class: "thumb", "data-stl": fileUrl(v, "model.stl"), "data-png": fileUrl(v, "view.png"), alt: `${v} 的模型`,
      onerror: (e) => e.target.replaceWith(h("div", { class: "thumb" })) }),
    h("div", {},
      h("div", { class: "v-title" }, h("span", {}, `${v} 已交付`)),
      entry.total !== null
        ? h("div", { class: "v-line", style: `color: var(${ok ? "--pass" : "--fail"})` }, `检查 ${entry.passed}/${entry.total} ${ok ? "全部通过" : "有没通过的"}`)
        : null,
      entry.repairs ? h("div", { class: "v-line muted" }, `建模中自动修复 ${entry.repairs} 次`) : null,
      entry.changes?.length && v !== "v1" ? h("ul", { class: "changes" }, entry.changes.slice(0, 4).map((c) => h("li", {}, c))) : null,
      h("div", { class: "links" },
        h("button", { class: "link", type: "button", onclick: () => actions.showVersion(v) }, "在 3D 中查看"),
        h("a", { href: fileUrl(v, "model.step"), download: `${v}.step` }, "STEP"),
        h("a", { href: fileUrl(v, "model.stl"), download: `${v}.stl` }, "STL"),
        h("a", { href: fileUrl(v, "model.py"), download: `${v}.py` }, "源文件"))));
}

function assistantMessage(entry, actions) {
  const body = {
    question: () => questionCard(entry, actions),
    confirm: () => confirmCard(entry, actions),
    delivered: () => deliveredCard(entry, actions),
    failed: () => h("div", { class: "card failed" }, h("div", { class: "text" }, entry.text)),
    error: () => h("div", { class: "card failed" }, h("div", { class: "text" }, entry.text)),
  }[entry.kind]?.() ?? h("div", { class: "text" }, entry.text);
  return h("div", { class: "msg msg-assistant" },
    h("div", { class: "meta" }, h("span", { class: "who" }, "助手"), h("span", { class: "kind" }, KIND_LABEL[entry.kind] || entry.kind)),
    body, usageLine(entry));
}

function welcome(actions) {
  return h("div", { class: "welcome" },
    h("h1", {}, "说出你想做的零件。"),
    h("p", {}, "我会先把需求问清楚，请你确认后再建模；每个尺寸都由程序测量核对，全部通过才交付。"),
    actions.live
      ? h("div", { class: "examples" }, EXAMPLES.map((text) =>
          h("button", { class: "example", type: "button", onclick: () => actions.send(text) }, h("span", {}, text), h("span", { class: "arrow", "aria-hidden": "true" }, "→"))))
      : null);
}

function working(state) {
  const secs = state.busy_seconds ? `${Math.round(state.busy_seconds)} 秒` : "";
  const steps = (state.activity || []).slice(-6);
  return h("div", { class: "working", "aria-live": "polite" },
    h("div", { class: "working-head" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("span", {}, "正在处理"), h("span", { class: "muted num secs" }, secs)),
    h("div", { class: `slow-hint ${state.busy_seconds > SLOW_SECONDS ? "" : "hidden"}` }, "模型这一步想得比较久，复杂的零件可能要几分钟，请稍等。"),
    steps.length ? h("ul", { class: "steps" }, steps.map((s) => h("li", {}, s))) : null);
}

export function renderChat(el, state, pendingText, actions) {
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  const items = [];
  const transcript = state.transcript || [];
  const lastAssistant = transcript.map((t) => t.role).lastIndexOf("assistant");
  if (!transcript.length && !pendingText) items.push(welcome(actions));
  transcript.forEach((entry, i) => {
    if (entry.role === "user") items.push(h("div", { class: "msg msg-user" }, h("div", { class: "bubble" }, entry.text)));
    else items.push(assistantMessage(entry, { ...actions, latest: i === lastAssistant && i === transcript.length - 1 && !state.busy }));
  });
  if (pendingText) items.push(h("div", { class: "msg msg-user pending" }, h("div", { class: "bubble" }, pendingText)));
  // 只给新出现的消息加入场动画，重画时旧消息不再闪
  const seen = Number(el.dataset.seen || 0);
  items.forEach((node, i) => { if (i >= seen && node.classList.contains("msg")) node.classList.add("new"); });
  el.dataset.seen = String(items.length);
  if (state.busy) items.push(working(state));
  clear(el, items);
  if (nearBottom) el.scrollTop = el.scrollHeight;
}

export function tickWorking(el, seconds) {
  const span = el.querySelector(".working .secs");
  if (span) span.textContent = seconds ? `${Math.round(seconds)} 秒` : "";
  el.querySelector(".working .slow-hint")?.classList.toggle("hidden", !(seconds > SLOW_SECONDS));
}
