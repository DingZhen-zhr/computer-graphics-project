// 左栏：对话。用户的话靠右、助手的话靠左；提问、请确认、交付各有自己的样子。

import { add, clear, fileUrl, h, yuan } from "./dom.js";

function meta(entry) {
  if (!entry.llm_calls) return null;
  const cost = yuan(entry.cost);
  return h("div", { class: "meta", text: `模型调用 ${entry.llm_calls} 次${cost ? ` · ${cost}` : ""}` });
}

function deliveryCard(entry, state) {
  const info = state.versions.find((v) => v.name === entry.version);
  const latest = state.versions.length ? state.versions[state.versions.length - 1].name : null;
  const passed = state.checks.filter((c) => c.passed).length;
  const summary = entry.version === latest && state.checks.length ? `检查 ${passed}/${state.checks.length} 通过` : "检查全部通过";
  return h("div", { class: "delivery" },
    h("div", { class: "ver" }, h("i", { "aria-hidden": "true" }), entry.version || "已交付"),
    h("div", { class: "muted", text: summary }),
    h("div", { class: "links" },
      entry.version ? h("a", { href: fileUrl(entry.version, "model.step"), download: `${entry.version}.step`, text: "下载 STEP" }) : null,
      entry.version && info && info.has_stl ? h("a", { href: fileUrl(entry.version, "model.stl"), download: `${entry.version}.stl`, text: "下载 STL" }) : null,
    ),
  );
}

function renderEntry(entry, index, state, handlers) {
  if (entry.role === "user") {
    return h("div", { class: "msg user" }, h("div", { class: "bubble", text: entry.text }));
  }
  const isLast = index === state.transcript.length - 1;
  const body = h("div", { class: `msg assistant ${entry.kind}` });
  if (entry.kind === "confirm") {
    const split = entry.text.indexOf("【需求单】");
    const lead = split > 0 ? entry.text.slice(0, split).trim() : "";
    const sheet = split >= 0 ? entry.text.slice(split) : entry.text;
    body.append(
      h("div", { class: "bubble", text: lead || "我整理了一份需求单，请你确认：" }),
      h("div", { class: "brief-text", text: sheet }),
    );
    if (isLast && !state.busy) {
      body.append(h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", onclick: handlers.confirm, text: "确认" }),
        h("button", { class: "btn", type: "button", onclick: handlers.revise, text: "我要修改" }),
      ));
    }
  } else if (entry.kind === "delivered") {
    const first = entry.text.split("\n")[0];
    body.append(h("div", { class: "bubble", text: first }), deliveryCard(entry, state));
  } else {
    body.append(h("div", { class: "bubble", text: entry.text }));
  }
  add(body, meta(entry));
  return body;
}

export function renderChat(container, state, handlers) {
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  clear(container);
  if (!state.transcript.length) {
    container.append(h("p", { class: "empty", text: "说出你想做的零件，比如：做一个放在桌上看视频的小支架。" }));
  }
  state.transcript.forEach((entry, i) => container.append(renderEntry(entry, i, state, handlers)));
  if (nearBottom || state.busy) container.scrollTop = container.scrollHeight;
}

export function renderProgress(el, state) {
  el.classList.toggle("hidden", !state.busy);
  if (!state.busy) return;
  clear(el);
  const steps = state.activity.length ? state.activity : ["正在思考…"];
  const now = steps[steps.length - 1];
  el.append(h("div", { class: "now" }, h("span", { class: "dot", "aria-hidden": "true" }), now));
  const before = steps.slice(-4, -1);
  if (before.length) el.append(h("div", { class: "prev", text: before.join(" → ") }));
}
