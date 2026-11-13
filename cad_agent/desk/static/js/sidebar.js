// 左栏：新会话、会话列表（标题、相对时间、版本数）、示例会话、案例库入口。
import { button, clear, confirmDialog, h, icon } from "./dom.js";
import { fmtTime } from "./format.js";

const DEMO_NOTE = "录制于 1.1 版";

function titleCell(item, actions, editing) {
  if (!editing) return h("span", { class: "s-title" }, item.title);
  const input = h("input", { class: "s-rename", value: item.title, "aria-label": "新的标题", maxlength: "60" });
  let finished = false;
  const finish = (save) => {
    if (finished) return;
    finished = true;
    actions.stopRename();
    if (save && input.value.trim() && input.value.trim() !== item.title) actions.rename(item.id, input.value.trim());
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  queueMicrotask(() => { input.focus(); input.select(); });
  return input;
}

function row(item, ui, actions) {
  const current = item.id === ui.currentId;
  const editing = item.id === ui.renaming;
  const meta = item.demo
    ? [h("span", {}, DEMO_NOTE)]
    : [h("span", {}, fmtTime(item.updated)), h("span", { class: "num" }, item.versions ? `${item.versions} 版` : "")];
  const open = editing
    ? h("div", { class: "session-open" }, titleCell(item, actions, true))
    : h("button", { type: "button", class: "session-open", "aria-current": current ? "true" : null, onclick: () => actions.open(item.id) },
      titleCell(item, actions, false), h("span", { class: "s-meta" }, meta));
  const tools = item.demo || editing ? null : h("span", { class: "session-tools" },
    button(icon("pencil"), () => actions.startRename(item.id), { kind: "text", small: true, "aria-label": `给"${item.title}"改名`, title: "改名" }),
    button(icon("cross"), async () => {
      if (await confirmDialog(`删除"${item.title}"？它的全部版本和文件都会一起删掉，不能恢复。`, "删除")) actions.remove(item.id);
    }, { kind: "text", small: true, "aria-label": `删除"${item.title}"`, title: "删除" }));
  return h("li", { class: `session${current ? " current" : ""}` }, open, tools);
}

export function renderSidebar(el, sessions, ui, actions) {
  const mine = sessions.filter((s) => !s.demo);
  const demos = sessions.filter((s) => s.demo);
  clear(el,
    h("div", { class: "side-head" }, button([icon("plus"), "新会话"], actions.create, { kind: "normal" })),
    h("nav", { class: "side-list", "aria-label": "会话" },
      mine.length
        ? h("ol", { class: "sessions" }, mine.map((s) => row(s, ui, actions)))
        : h("p", { class: "side-empty" }, "还没有会话。点上面的“新会话”开始做第一个零件。"),
      demos.length ? h("div", { class: "side-group" }, h("h2", { class: "side-label" }, "示例"),
        h("ol", { class: "sessions" }, demos.map((s) => row(s, ui, actions)))) : null),
    h("div", { class: "side-foot" }, button("案例库", actions.cases, { kind: "text" })));
}
