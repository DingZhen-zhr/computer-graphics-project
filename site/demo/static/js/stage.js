// 舞台外壳：标题、副标题、字幕、可以直接点的回答、输入框（运行时变成停止）、四角的按钮、左边的步骤、右边的大数字。
import { isStatic } from "./api.js";
import { $, clear, h } from "./dom.js";
import { phaseView, scoreView, TEXT } from "./stage-logic.js";

export { phaseView } from "./stage-logic.js";

const DEMO_NOTE = '这是一段录制好的示例，只能看。想自己做一个，点左上角的"菜单"，再点"做一个新的"。';
const STATIC_NOTE = '这是一段录制好的示例，只能看。想自己做一个，点右上角的"安装 Datum"。';
let ui = null;

export function mountStage(actions) {
  const input = h("textarea", { rows: "1", placeholder: TEXT.placeholder, "aria-label": "给助手的消息" });
  const send = h("button", { type: "button", class: "send", "aria-label": "发送" }, "↑");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 132)}px`; });
  send.addEventListener("click", () => (ui.state && ui.state.busy ? actions.stop() : submit()));
  clear($("prompt"), input, send);
  ui = { actions, input, send, state: null, stepFocus: null };
}

async function submit() {
  const text = ui.input.value.trim();
  const s = ui.state;
  if (!text || !s || s.busy || (s.session && s.session.demo)) return;
  if (await ui.actions.send(text)) { ui.input.value = ""; ui.input.style.height = "auto"; }
}

export function focusPrompt() { if (ui) ui.input.focus(); }

function renderSteps(state) {
  const el = $("steps");
  const stages = (state.plan && state.plan.stages) || [];
  if (state.product || !stages.length) { el.classList.add("gone"); return; }
  el.classList.remove("gone");
  const checksOf = (id) => (state.checks || []).filter((c) => c.stage === id);
  clear(el, stages.map((s) => {
    const running = state.busy && s.id === state.plan.current;
    const n = checksOf(s.id);
    const done = s.passed;
    return h("button", { type: "button", class: ui.stepFocus === s.id ? "on" : "", "aria-pressed": String(ui.stepFocus === s.id),
      onclick: () => { ui.stepFocus = ui.stepFocus === s.id ? null : s.id; ui.actions.showStage(ui.stepFocus); renderSteps(state); } },
      h("i", { class: done ? "done" : running ? "run" : "" }), s.title,
      h("em", { class: `num ${done ? "status-ok" : "mute"}` }, done ? `✓ ${n.filter((c) => c.passed).length}/${n.length}` : running ? "进行中" : "没开始"));
  }));
}

export function renderStage(state) {
  ui.state = state;
  const v = phaseView(state);
  $("title-h1").textContent = v.title;
  $("title-sub").textContent = v.subtitle;
  const demo = !!(state.session && state.session.demo);
  $("caption").textContent = demo && v.center === "welcome" ? (isStatic() ? STATIC_NOTE : DEMO_NOTE) : v.caption;
  const welcome = v.center === "welcome";
  clear($("choices"), welcome && !demo
    ? TEXT.examples.map((t) => h("button", { type: "button", class: "btn-glass", onclick: () => ui.actions.send(t) }, t))
    : v.choices.map((t, i) => h("button", { type: "button", class: i === 0 ? "btn-primary" : "btn-glass", disabled: state.busy || demo, onclick: () => ui.actions.send(t) }, t)));
  $("choices").classList.toggle("welcome", welcome);
  const busy = !!state.busy;
  ui.input.disabled = demo || !state.session;
  ui.send.classList.toggle("stop", busy);
  ui.send.textContent = busy ? "■" : "↑";
  ui.send.setAttribute("aria-label", busy ? "停止这一轮" : "发送");
  if (demo) ui.input.placeholder = isStatic() ? STATIC_NOTE : DEMO_NOTE;
  else ui.input.placeholder = TEXT.placeholder;
  const score = scoreView(state);
  $("score").classList.toggle("gone", !score || v.center !== "model");
  if (score) { $("score-n").textContent = score.text; $("score-l").textContent = score.label; }
  const hasModel = v.center === "model" || v.center === "failed";
  const tune = $("tune-open");   // 在线示例里它换成了"安装 Datum"的链接
  if (tune) tune.classList.toggle("gone", !(state.versions || []).length);
  $("gizmo").classList.toggle("hide", !hasModel);
  renderSteps(state);
  return v;
}
