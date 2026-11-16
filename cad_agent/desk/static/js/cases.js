// 案例库：两组——自带、我保存的。每个案例一行：标题、标签、一句话需求、阶段标题；我保存的可以删除。
import { del, get } from "./api.js";
import { button, clear, confirmDialog, h, sectionHead, status } from "./dom.js";

const MINE_EMPTY = '还没有保存过案例。交付一个满意的零件后，在"版本"里点"存为案例"，以后做相似的零件时会拿它当参考。';

function caseRow(c, onDelete) {
  return h("li", { class: "case" },
    h("div", { class: "case-head" }, h("h3", {}, c.title),
      h("span", { class: "case-tags" }, c.tags.map((t) => h("span", { class: "tag tag-suggested" }, t))),
      c.builtin ? null : button("删除", () => onDelete(c), { kind: "text", small: true, "aria-label": `删除案例"${c.title}"` })),
    h("p", { class: "case-request" }, c.request),
    h("ol", { class: "case-stages mono small" }, c.stages.map((s, i) => h("li", {}, `S${i + 1} ${s}`))));
}

export async function renderCases(el, actions) {
  let error = null;
  const draw = (cases) => {
    const builtin = cases.filter((c) => c.builtin);
    const mine = cases.filter((c) => !c.builtin);
    const remove = async (c) => {
      if (!(await confirmDialog(`删除案例"${c.title}"？以后规划时就不会再参考它，不能恢复。`, "删除"))) return;
      const res = await del(`/api/cases/${encodeURIComponent(c.id)}`);
      error = res.status === 200 ? null : res.body.error;
      load();
    };
    clear(el, h("div", { class: "page-narrow cases-page" },
      h("div", { class: "page-top" }, h("h1", { class: "page-title" }, "案例库"), button("返回", () => actions.close(), { kind: "text" })),
      h("p", { class: "muted" }, "规划一个新零件时，卡尺会从这里挑最相似的一两个给模型参考。尺寸和结构仍以你的需求单为准。"),
      error ? h("p", { role: "alert" }, status("bad", error)) : null,
      h("section", { "aria-labelledby": "h-cases-builtin" }, sectionHead("01", "自带", `${builtin.length} 个`, "h-cases-builtin"),
        h("ol", { class: "case-list" }, builtin.map((c) => caseRow(c, remove)))),
      h("section", { "aria-labelledby": "h-cases-mine" }, sectionHead("02", "我保存的", mine.length ? `${mine.length} 个` : "", "h-cases-mine"),
        mine.length ? h("ol", { class: "case-list" }, mine.map((c) => caseRow(c, remove)))
          : h("div", { class: "empty-note" }, h("p", { class: "muted" }, MINE_EMPTY), button("回到会话", () => actions.close(), { kind: "text" })))));
  };
  const load = async () => {
    const res = await get("/api/cases");
    if (res.status !== 200) {
      clear(el, h("div", { class: "page-narrow" }, h("p", { role: "alert" }, status("bad", res.body.error)), button("返回", () => actions.close(), { kind: "text" })));
      return;
    }
    draw(res.body);
  };
  await load();
}
