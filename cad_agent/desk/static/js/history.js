// 对话记录（左边的抽屉）：完整的对话；每一轮里做了什么可以展开（写了几条检查、做了什么、量了几项、通过没有）。
import { clear, h } from "./dom.js";

const KIND = { question: "问你", confirm: "请你确认", delivered: "做好了", failed: "没做完", stopped: "停下了", error: "出错了" };

function workLines(work) {
  const lines = [];
  for (const s of work.stages || []) {
    const tools = s.tools || [];
    lines.push(`${s.title || s.id}：${s.passed ? "通过" : "没通过"}${typeof s.checks === "number" ? `，量了 ${s.checks} 项` : ""}`);
    for (const t of tools) lines.push(`　${t.label || t.name}${t.state === "bad" || t.ok === false ? "（出错，改了）" : ""}`);
  }
  for (const t of work.loose || []) lines.push(`${t.label || t.name}${t.state === "bad" || t.ok === false ? "（出错，改了）" : ""}`);
  return lines;
}

function itemEl(item) {
  if (item.role === "user") return h("div", { class: "turn" }, h("div", { class: "who" }, "你"), h("p", {}, item.text));
  if (item.role === "work" || item.role === "live") {
    const work = item.role === "live" ? item.work : item;
    const lines = workLines(work);
    const replies = item.role === "live" ? [...(item.replies || []), item.streaming].filter(Boolean) : [];
    if (!lines.length && !replies.length) return item.role === "live" ? h("div", { class: "turn mute" }, "正在想") : null;
    return h("div", { class: "turn" }, replies.map((r) => h("p", {}, r)),
      lines.length ? h("details", {}, h("summary", {}, `做了 ${lines.length} 件事`), lines.map((l) => h("div", {}, l))) : null);
  }
  const text = item.kind === "question" ? [item.lead, ...(item.questions || []).map((q, i) => `${i + 1}. ${q}`)].filter(Boolean).join("\n") : item.text;
  return h("div", { class: "turn" }, h("div", { class: "who" }, `Datum · ${KIND[item.kind] || "回复"}`),
    String(text || "").split("\n").map((l) => h("p", {}, l)));
}

export function renderHistory(el, state, actions) {
  const items = (state.transcript || []).map(itemEl).filter(Boolean);
  clear(el,
    h("header", {}, h("h2", {}, "对话记录"), h("button", { type: "button", class: "x", "data-close": "", "aria-label": "收起", onclick: actions.close }, "×")),
    items.length ? items : h("p", { class: "mute small" }, "还没有对话。在下面的输入框里说说要做什么。"));
}
