// 对话里的几种卡片：提问、确认需求单、交付、失败 / 停止 / 出错。文字一律用后端给的。
import { button, h, status } from "./dom.js";
import { fmtLen } from "./format.js";

const KIND_LABEL = { question: "提问", confirm: "请确认", delivered: "交付", failed: "停下了", stopped: "已停止", error: "出错了" };

function head(kind, extra = "") {
  return h("div", { class: "card-head" }, h("span", { class: "card-kind" }, KIND_LABEL[kind] || ""), extra ? h("span", { class: "card-extra" }, extra) : null);
}

function text(t, cls = "card-text") {
  return t ? h("p", { class: cls }, t) : null;
}

// ---- 提问：问题带编号，每个问题一个输入框，"发送回答"把各条拼成 1. …\n2. … ----
export function questionCard(entry, ctx) {
  const qs = entry.questions || [];
  const inputs = qs.map((q, i) => h("textarea", { rows: "1", class: "answer", "aria-label": `第 ${i + 1} 个问题的回答`, disabled: !ctx.canAnswer }));
  const submit = () => {
    const filled = inputs.map((el) => el.value.trim());
    if (!filled.some(Boolean)) return;
    ctx.send(filled.map((v, i) => `${i + 1}. ${v || "（这条先不定）"}`).join("\n"));
  };
  inputs.forEach((el) => el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      submit();
    }
  }));
  return h("article", { class: "card question" }, head("question"), text(entry.lead),
    h("ol", { class: "questions" }, qs.map((q, i) => h("li", {}, h("span", { class: "q-no" }, String(i + 1)), h("div", { class: "q-body" }, h("p", {}, q), inputs[i])))),
    ctx.canAnswer ? h("div", { class: "card-actions" }, button("发送回答", submit), h("span", { class: "muted small" }, "也可以直接在下面的输入框里回答")) : null);
}

// ---- 确认需求单 ----
function paramRows(params) {
  return params.map((p) => h("tr", {},
    h("td", { class: "mono" }, p.name),
    h("td", { class: "num" }, fmtLen(p.value, p.unit)),
    h("td", {}, h("span", { class: `tag ${p.source === "user" ? "tag-user" : "tag-suggested"}` }, p.source === "user" ? "用户" : "建议")),
    h("td", { class: "muted" }, p.note || "")));
}

export function briefBlock(brief) {
  const part = brief.part || {};
  return h("div", { class: "brief" },
    h("h3", { class: "brief-name" }, part.name || "（还没有零件名）"),
    part.purpose ? h("p", { class: "muted" }, part.purpose) : null,
    (brief.params || []).length ? h("table", { class: "table params" },
      h("thead", {}, h("tr", {}, h("th", {}, "参数"), h("th", { class: "num" }, "数值"), h("th", {}, "来源"), h("th", {}, "说明"))),
      h("tbody", {}, paramRows(brief.params))) : null,
    (brief.features || []).length ? h("div", { class: "brief-list" }, h("h4", {}, "组成部分"), h("ul", {}, brief.features.map((f) => h("li", {}, f)))) : null,
    (brief.relations || []).length ? h("div", { class: "brief-list" }, h("h4", {}, "位置关系"), h("ul", {}, brief.relations.map((r) => h("li", {}, r)))) : null);
}

export function confirmCard(entry, ctx) {
  return h("article", { class: "card confirm" }, head("confirm"), text(entry.lead),
    entry.brief ? briefBlock(entry.brief) : text(entry.text),
    ctx.canAnswer ? h("div", { class: "card-actions" }, button("确认，开始建模", () => ctx.send("确认"), { kind: "primary" }),
      h("span", { class: "muted small" }, "要改什么，直接在下面说")) : null);
}

// ---- 交付 ----
export function mutationLine(gate) {
  if (!gate || !Array.isArray(gate.mutation) || !gate.mutation.length) return status("none", "参数扰动验证：没做");
  const ok = gate.mutation.filter((m) => m.verdict === "constrained").length;
  const loose = gate.unconstrained || [];
  const odd = gate.unbuildable || [];
  if (loose.length) return status("bad", `参数扰动验证：${loose.join("、")} 没有被约束`);
  return status("ok", `参数扰动验证：${ok} 个参数被检查约束${odd.length ? `，${odd.length} 个无法单独扰动` : ""}`);
}

export function reviewLine(review) {
  if (!review) return status("none", "看图审查：没做");
  if (review.skipped) return status("none", `看图审查：没做（${review.skipped}）`);
  const against = (review.items || []).filter((i) => i.verdict === "不符合");
  if (!against.length) return status("ok", "看图审查：符合需求单");
  return h("div", {}, status("bad", "看图审查有异议"), h("ul", { class: "objections" }, against.map((i) => h("li", {}, `${i.target}：${i.reason}`))));
}

export function deliveredCard(entry, ctx) {
  const v = entry.version;
  const checks = entry.total ? status(entry.passed === entry.total ? "ok" : "bad", `检查 ${entry.passed}/${entry.total}`) : null;
  return h("article", { class: "card delivered" },
    head("delivered", v || ""),
    h("div", { class: "card-lines" }, checks, mutationLine(entry.gate), reviewLine(entry.review)),
    (entry.changes || []).length ? h("p", { class: "changes" }, `本版变化：${entry.changes.join("；")}`) : null,
    v ? h("div", { class: "card-actions" },
      h("a", { class: "btn small", href: ctx.fileUrl(v, "model.step"), download: `${v}.step` }, "下载 STEP"),
      h("a", { class: "btn small", href: ctx.fileUrl(v, "model.stl"), download: `${v}.stl` }, "下载 STL"),
      ctx.demo ? null : button("在文件夹中显示", () => ctx.reveal(v), { kind: "text", small: true })) : null);
}

// ---- 失败、停止、出错 ----
const NEXT = {
  failed: "可以告诉我怎么调整，或者让我接着试。",
  stopped: "",
  error: "需求单和已经写好的内容都还在，可以再发一次。",
};

export function troubleCard(entry, ctx) {
  const again = entry.kind === "error" ? ctx.lastUserText : "继续";
  return h("article", { class: `card trouble ${entry.kind}` }, head(entry.kind), text(entry.text),
    h("div", { class: "card-actions" }, h("span", { class: "muted small" }, NEXT[entry.kind]),
      ctx.canAnswer && again ? button(entry.kind === "error" ? "再发一次" : "继续", () => ctx.send(again), { small: true }) : null));
}
