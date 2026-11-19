// 一轮的工具调用树 → 要显示的行。纯逻辑，不碰页面。
// 阶段行的记号是 S1、S2…；阶段下面的工具：不是最后一个用 ├，最后一个用 └。
// 通过了的阶段默认折叠成一行（"底板 ✓ 检查 5 条"），expanded 里有它的编号时才展开。
// 不属于任何阶段的工具（规划之前的）放在最前面，没有阶段行。

function toolState(t) {
  if (t.state) return t.state;
  return t.ok === false ? "bad" : "ok";
}

function toolLine(t, depth, mark) {
  return { depth, mark, text: t.label || t.name, detail: t.summary || "", state: toolState(t), name: t.name };
}

function stageState(stage, tools) {
  const states = tools.map(toolState);
  if (states.includes("running")) return "running";
  if (stage.passed) return "ok";
  if (states.length && states[states.length - 1] === "bad") return "bad";
  return "open";
}

export function treeLines(work, expanded = new Set()) {
  const lines = [];
  const loose = (work && work.loose) || [];
  for (const t of loose) lines.push(toolLine(t, 0, "─"));
  for (const stage of (work && work.stages) || []) {
    const tools = stage.tools || [];
    const state = stageState(stage, tools);
    const collapsed = stage.passed && state !== "running" && !expanded.has(stage.id);
    const checks = typeof stage.checks === "number" ? ` 检查 ${stage.checks} 条` : "";
    const text = stage.passed ? `${stage.title} ✓${checks}` : stage.title;
    lines.push({ depth: 0, mark: String(stage.id || "").toUpperCase(), text, detail: "", state, stage: stage.id, collapsed,
      expandable: stage.passed && tools.length > 0 });
    if (collapsed) continue;
    tools.forEach((t, i) => lines.push(toolLine(t, 1, i === tools.length - 1 ? "└" : "├")));
  }
  return lines;
}
