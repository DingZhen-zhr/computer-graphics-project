// 左上的菜单（左边的抽屉）：做一个新的、最近做过的（名字、时间、几个版本；改名、删除前确认）、示例、案例库、设置、外观。
import { clear, confirmDialog, formDialog, h } from "./dom.js";
import { fmtTime } from "./format.js";

function row(item, currentId, actions) {
  const meta = item.demo ? "录好的示例" : [fmtTime(item.updated), item.versions ? `${item.versions} 版` : ""].filter(Boolean).join("  ");
  return h("div", { class: `item${item.id === currentId ? " on" : ""}` },
    h("button", { type: "button", class: "grow btn-text menu-open", "aria-current": item.id === currentId ? "true" : null,
      onclick: () => actions.open(item.id) }, h("div", {}, item.title), h("div", { class: "small mute num" }, meta)),
    item.demo ? null : h("button", { type: "button", class: "btn-text btn-small", "aria-label": `给"${item.title}"改名`, onclick: async () => {
      const r = await formDialog("改个名字", [{ name: "title", label: "名字", value: item.title }]);
      if (r && r.title.trim() && r.title.trim() !== item.title) actions.rename(item.id, r.title.trim());
    } }, "改名"),
    item.demo ? null : h("button", { type: "button", class: "btn-text btn-small", "aria-label": `删除"${item.title}"`, onclick: async () => {
      if (await confirmDialog(`删除"${item.title}"？它的全部版本和文件都会一起删掉，不能恢复。`, "删除")) actions.remove(item.id);
    } }, "删除"));
}

export function renderMenu(el, sessions, currentId, actions) {
  const mine = sessions.filter((s) => !s.demo);
  const demos = sessions.filter((s) => s.demo);
  clear(el,
    h("header", {}, h("h2", {}, "菜单"), h("button", { type: "button", class: "x", "data-close": "", "aria-label": "收起", onclick: actions.close }, "×")),
    actions.readOnly ? null : h("button", { type: "button", class: "btn-primary", onclick: actions.create }, "做一个新的"),
    h("h3", {}, "最近做过的"),
    mine.length ? h("div", { class: "list" }, mine.map((s) => row(s, currentId, actions)))
      : h("p", { class: "mute small" }, "还没有做过东西。点上面的按钮开始第一个。"),
    demos.length ? [h("h3", {}, "示例"), h("div", { class: "list" }, demos.map((s) => row(s, currentId, actions)))] : null,
    h("h3", {}, "更多"),
    h("div", { class: "list" },
      h("button", { type: "button", class: "item", onclick: actions.cases }, "案例库"),
      actions.readOnly ? null : h("button", { type: "button", class: "item", onclick: actions.settings }, "设置"),
      h("button", { type: "button", class: "item", onclick: actions.theme }, actions.themeLabel())));
}
