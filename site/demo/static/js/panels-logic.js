// 需求单卡片和检查面板的纯逻辑（可测）。
import { fmtLen, fmtNum } from "./format.js";

export const WAITING = "等你回答";
const SOURCE = { user: "你给的", suggested: "建议" };
const STATUS = { ok: "量过，对", bad: "没过", none: "没做" };

function label(p) {
  const note = String(p.note || "").trim();
  const cut = note.search(/[，,；;：:（(]/);
  return (cut >= 0 ? note.slice(0, cut) : note).trim() || p.name;
}

// 需求单的一行：名字、数值、单位、来源标签；问题里还在等的参数标成"等你回答"
export function briefRows(brief) {
  if (!brief) return [];
  const open = (brief.open_questions || []).join(" ");
  return (brief.params || []).map((p) => {
    const waiting = p.source === "suggested" && open.includes(label(p));
    return { name: p.name, label: label(p), value: waiting ? "" : fmtNum(p.value), unit: p.unit === "1" ? "" : p.unit,
      tag: waiting ? null : SOURCE[p.source] || null, waiting, part: p.part || null };
  });
}

// 多零件时需求单分几块：零件、共用的尺寸、各零件的尺寸、怎么连、会动的地方
export function briefSections(brief) {
  const rows = briefRows(brief);
  const parts = brief && Array.isArray(brief.parts) ? brief.parts : [];
  if (parts.length < 2) {
    return [{ title: "尺寸", rows }, { title: "组成部分", items: brief ? brief.features || [] : [] },
      { title: "怎么拼在一起", items: brief ? brief.relations || [] : [] }];
  }
  const names = Object.fromEntries(parts.map((p) => [p.id, p.name]));
  return [
    { title: "零件", items: parts.map((p) => `${p.name}：${(p.features || []).join("、")}`) },
    { title: "共用的尺寸", rows: rows.filter((r) => !r.part) },
    ...parts.map((p) => ({ title: `${names[p.id]}的尺寸`, rows: rows.filter((r) => r.part === p.id) })).filter((s) => s.rows.length),
    { title: "怎么连", items: brief.relations || [] },
    { title: "会动的地方", items: brief.motions || [] },
  ];
}

export function checkStatus(c) {
  if (c.passed === true) return { kind: "ok", text: STATUS.ok };
  if (c.passed === false) return { kind: "bad", text: STATUS.bad };
  return { kind: "none", text: STATUS.none };
}

export function checkValue(c) {
  if (c.measured === null || c.measured === undefined) return "";
  const m = fmtLen(c.measured, "");
  return c.expected === null || c.expected === undefined ? m : `${m} / ${fmtLen(c.expected, "")}`;
}

// 检查分组：单零件按步骤（没有步骤的放"检查"），多零件按零件，装配一组放最后
export function groupChecks(checks, { plan = null, product = null } = {}) {
  const list = checks || [];
  if (product && product.parts && product.parts.length) {
    const groups = product.parts.map((p) => ({ group: p.name, items: list.filter((c) => c.part === p.id) })).filter((g) => g.items.length);
    const asm = list.filter((c) => c.part === "assembly");
    return asm.length ? [...groups, { group: "装配", items: asm }] : groups;
  }
  const stages = (plan && plan.stages) || [];
  if (!stages.length) return list.length ? [{ group: "检查", items: list }] : [];
  const groups = stages.map((s) => ({ group: `${s.id.toUpperCase()} ${s.title}`, items: list.filter((c) => c.stage === s.id) }));
  const loose = list.filter((c) => !stages.some((s) => s.id === c.stage));
  return [...groups.filter((g) => g.items.length), ...(loose.length ? [{ group: "检查", items: loose }] : [])];
}

// 修改前后对比：参数变化写成"孔径：6 → 8 毫米"
const UNIT_TEXT = { mm: "毫米", deg: "度", 1: "" };
export function paramChangeText(p) {
  const unit = UNIT_TEXT[p.unit] ?? p.unit ?? "";
  return `${p.label || p.name}：${fmtNum(p.a)} → ${fmtNum(p.b)}${unit ? ` ${unit}` : ""}`;
}

// 对比里一条检查的变化：零件用名字，检查用当前版本里的说明；说明找不到（这一版已经没有这条）就写"一项检查"
const PASS_TEXT = (v) => (v === null || v === undefined ? "没有" : v ? "通过" : "没过");
export function checkChangeText(c, state) {
  const parts = (state && state.product && state.product.parts) || [];
  const where = c.part === "assembly" ? "装配" : c.part && c.part !== "main" ? ((parts.find((p) => p.id === c.part) || {}).name || "一个零件") : "";
  const found = ((state && state.checks) || []).find((x) => x.id === c.id && (x.part || "main") === (c.part || "main"));
  const what = (found && found.detail) || "一项检查";
  return `${where ? `${where}：` : ""}${what}：${PASS_TEXT(c.a)} → ${PASS_TEXT(c.b)}`;
}
