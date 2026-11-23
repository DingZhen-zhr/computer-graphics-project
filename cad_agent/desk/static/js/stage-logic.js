// 舞台上写什么（纯逻辑，可测）：标题、副标题、字幕、可以直接点的回答、舞台中间放什么（设计文档第 7.3 节）。
import { fmtNum } from "./format.js";

export const TEXT = {
  newPart: "新零件",
  welcome: "说说你想做什么。可以是一个零件，也可以是几个零件装在一起、能动的东西。",
  examples: ["做一个放在桌上看视频的手机支架", "做一个带铰链盖的工具盒，盖子能翻开", "做一个法兰盘，外径 120，上面一圈 6 个螺栓孔"],
  placeholder: "说说要做什么，或者要怎么改",
  asking: "还在问你几个问题",
  confirm: "都记下了，你看一下",
  failed: "没做完",
  assembling: "正在装起来",
  allPassed: "项全部量过，都对",
  someChecked: "项已经量过",
  assemble: "装起来",
  stepFailed: "没过，在改",
  stepsDone: "已完成",
  stepRun: "进行中",
  stepTodo: "没开始",
};

function lastAssistant(state) {
  const t = state.transcript || [];
  for (let i = t.length - 1; i >= 0; i -= 1) if (t[i].role === "assistant") return t[i];
  return null;
}

function sizeText(v) {
  if (!v || !Array.isArray(v.size)) return "";
  return v.size.map((x) => fmtNum(x)).join(" × ");
}

function partTitle(state) {
  const name = state.brief && state.brief.part && state.brief.part.name;
  return name || TEXT.newPart;
}

// 正在做哪一步：单零件"第 k 步，共 n 步"；多零件"正在做 <零件名>，第 k 个零件，共 n 个"；全部零件做完在装配时"正在装起来"
function buildingSubtitle(state) {
  const prod = state.product;
  if (prod && prod.parts && prod.parts.length) {
    const idx = prod.parts.findIndex((p) => p.status === "current");
    if (idx < 0 && prod.parts.every((p) => p.status === "done")) return TEXT.assembling;
    const k = idx < 0 ? 1 : idx + 1;
    const name = idx < 0 ? prod.parts[0].name : prod.parts[idx].name;
    return `正在做 ${name}，第 ${k} 个零件，共 ${prod.parts.length} 个`;
  }
  const stages = (state.plan && state.plan.stages) || [];
  if (!stages.length) return "正在做，第 1 步，共 1 步";
  const cur = stages.findIndex((s) => s.id === state.plan.current);
  const k = cur < 0 ? stages.length : cur + 1;
  return `正在做，第 ${k} 步，共 ${stages.length} 步`;
}

// 只有一个问题、而且问题里给了选项（"A 还是 B"、"建议 X"）时，给出可以直接点的按钮
export function choicesFor(entry) {
  if (!entry || entry.kind !== "question" || !Array.isArray(entry.questions) || entry.questions.length !== 1) return [];
  const q = entry.questions[0];
  const either = q.match(/([^，。？?、\s]{1,12})还是([^，。？?、\s]{1,12})[？?]?/);
  if (either) return [either[1], either[2]];
  const suggest = q.match(/建议([^，。；;）)]{1,20})/);
  if (suggest) return [`就按建议：${suggest[1].trim()}`];
  return [];
}

export function phaseView(state) {
  const versions = state.versions || [];
  const last = lastAssistant(state);
  const title = partTitle(state);
  const view = { title, subtitle: "", caption: "", choices: [], center: "model" };
  if (!state.session || (!versions.length && !(state.transcript || []).length && !state.busy)) {
    return { ...view, title: TEXT.newPart, caption: TEXT.welcome, center: "welcome" };
  }
  if (state.phase === "confirm") {
    return { ...view, subtitle: TEXT.confirm, caption: last ? (last.lead || "") : "", center: "confirm" };
  }
  if (state.phase === "clarify") {
    const caption = last && last.kind === "question" ? [last.lead, ...(last.questions || [])].filter(Boolean).join(" ") : last ? (last.text || "") : "";
    return { ...view, subtitle: TEXT.asking, caption, choices: choicesFor(last), center: "brief" };
  }
  if (state.busy || (state.phase !== "delivered" && !versions.length)) {
    const caption = last && last.kind !== "delivered" ? (last.text || "") : "";
    if (!state.busy && last && (last.kind === "failed" || last.kind === "stopped" || last.kind === "error")) {
      return { ...view, subtitle: TEXT.failed, caption: last.text || "", choices: ["继续"], center: "failed" };
    }
    return { ...view, subtitle: buildingSubtitle(state), caption: state.busy ? "" : caption, center: "model" };
  }
  const v = versions[versions.length - 1];
  const k = String(v.name || "").replace(/^v/, "");
  const prod = state.product;
  const subtitle = prod && prod.parts && prod.parts.length ? `第 ${k} 版，${prod.parts.length} 个零件` : `第 ${k} 版，${sizeText(v)} 毫米`;
  const caption = last && last.kind === "delivered" ? (last.text || "").split("\n")[0] : last ? (last.text || "") : "";
  if (last && (last.kind === "failed" || last.kind === "stopped" || last.kind === "error")) {
    return { ...view, subtitle, caption: last.text || "", choices: ["继续"], center: "model" };
  }
  return { ...view, subtitle, caption, choices: choicesFor(last), center: "model" };
}

// 右边的大数字：通过数 / 总数，下面一句话
export function scoreView(state) {
  const checks = state.checks || [];
  if (!checks.length) return null;
  const passed = checks.filter((c) => c.passed).length;
  return { text: `${passed}/${checks.length}`, label: passed === checks.length && state.phase === "delivered" ? TEXT.allPassed : TEXT.someChecked };
}

// 左边的进度清单：单零件列阶段（可以点），多零件列零件和最后的"装起来"（只看）。交付后多零件不列（那里是零件面板）。
export function stepsView(state) {
  const prod = state.product;
  if (prod && prod.parts && prod.parts.length) {
    if (!state.busy && (state.versions || []).length) return null;
    const allDone = prod.parts.every((p) => p.status === "done");
    const items = prod.parts.map((p) => {
      const status = p.status === "done" ? "done" : p.status === "current" && state.busy ? "run" : "todo";
      const c = p.checks || { passed: 0, total: 0 };
      return { id: p.id, title: p.name, status, clickable: false,
        note: status === "done" ? `✓ ${c.passed}/${c.total}` : status === "run" ? TEXT.stepRun : TEXT.stepTodo };
    });
    const a = prod.assembly === "passed" ? "done" : prod.assembly === "failed" ? "failed" : allDone && state.busy ? "run" : "todo";
    items.push({ id: "assembly", title: TEXT.assemble, status: a, clickable: false,
      note: a === "done" ? "✓" : a === "failed" ? TEXT.stepFailed : a === "run" ? TEXT.stepRun : TEXT.stepTodo });
    return { items, done: items.filter((i) => i.status === "done").length, total: items.length };
  }
  const stages = (state.plan && state.plan.stages) || [];
  if (!stages.length) return null;
  const items = stages.map((s) => {
    const n = (state.checks || []).filter((c) => c.stage === s.id);
    const status = s.passed ? "done" : state.busy && s.id === state.plan.current ? "run" : "todo";
    return { id: s.id, title: s.title, status, clickable: true,
      note: status === "done" ? `✓ ${n.filter((c) => c.passed).length}/${n.length}` : status === "run" ? TEXT.stepRun : TEXT.stepTodo };
  });
  return { items, done: items.filter((i) => i.status === "done").length, total: items.length };
}
