// 舞台中间放什么模型：正在做时是最新一步的样子；做好了是最新版本；多零件时按装好的位置摆，能动、能炸开；
// 对比时把两版一起放上去。三维显示不了、或者文件加载失败时，退回截图并说明。
import { $, h } from "./dom.js";
import { cssVar, onThemeChange } from "./theme.js";
import { loadMotion } from "./motion-logic.js";
import { mountMotion } from "./motion.js";
import { mountAssembly } from "./view3d/assembly.js";
import { mountGizmo } from "./view3d/gizmo.js";
import { createScene, STL_FAILED } from "./view3d/scene.js";

let mv = null;

export function mountModelView(fileUrl) {
  const shot = h("img", { class: "shot gone", alt: "模型截图" });
  const note = h("p", { class: "fallback-note gone", role: "status" });
  $("view").append(shot);
  document.body.append(note);
  mv = { fileUrl, shot, note, scene: null, state: null, motion: null, motionUrl: null, sig: "", stage: null, comparing: null, fallback: null };
  mv.scene = createScene($("view"), { onFallback: (why) => { mv.fallback = why; showShot(); } });
  if (!mv.scene) return;
  mountGizmo($("gizmo"), mv.scene);
  mv.asm = mountAssembly({ partsEl: $("parts"), cardEl: $("part-card"), toolsEl: $("asm-tools"), labelsEl: $("labels") }, mv.scene,
    { onSection: (on) => mv.scene.setSection(on ? "y" : null, 0.5) });
  mv.motionBar = mountMotion($("motion"), {
    onPose: (poses) => mv.asm.setPoses(poses),
    onHit: (ids) => mv.asm.highlight(ids),
    partName: (id) => { const p = mv.state && mv.state.product && mv.state.product.parts.find((x) => x.id === id); return p ? p.name : id; },
  });
  onThemeChange(() => mv.scene.setTheme());
}

function showShot() {
  const png = mv.png;
  mv.shot.classList.toggle("gone", !png);
  if (png) mv.shot.src = png;
  mv.note.textContent = mv.fallback || "";
  mv.note.classList.toggle("gone", !mv.fallback);
}

export function showStage(stageId) { mv.stage = stageId; if (mv.state) updateModel(mv.state, mv.center, true); }
export function setShift(px) { if (mv.scene) mv.scene.setShift(px); }

// 这一刻要显示的东西：{parts, png, motionUrl}
function target(state, center) {
  if (center !== "model" && center !== "failed") return { parts: [], png: null, motionUrl: null };
  const versions = state.versions || [];
  const v = versions[versions.length - 1];
  const prod = state.product;
  const files = state.stage_files || [];
  const building = state.busy || !v || (state.phase !== "delivered" && files.length && !v);
  if (!building && v && prod && prod.parts.length) {
    return { parts: prod.parts.map((p) => ({ id: p.id, url: mv.fileUrl(v.name, `parts/${p.id}/model.stl`), color: p.color, finish: p.finish })),
      png: v.has_png === false ? null : mv.fileUrl(v.name, "view.png"), motionUrl: mv.fileUrl(v.name, "motion.json"), version: v.name };
  }
  if (!building && v) {
    const url = mv.stage && (v.stages || []).includes(mv.stage) ? mv.fileUrl(v.name, `stages/${mv.stage}.stl`) : v.has_stl === false ? null : mv.fileUrl(v.name, "model.stl");
    return { parts: url ? [{ id: "main", url, color: cssVar("--part"), finish: "metal" }] : [], png: v.has_png === false ? null : mv.fileUrl(v.name, "view.png"),
      motionUrl: null, version: v.name, noStl: !url };
  }
  if (!files.length) return { parts: [], png: null, motionUrl: null };
  const sid = mv.stage && files.includes(mv.stage) ? mv.stage : files[files.length - 1];
  return { parts: [{ id: "main", url: mv.fileUrl("current", `stages/${sid}.stl`), color: cssVar("--part"), finish: "metal" }], png: null, motionUrl: null };
}

export async function updateModel(state, center, force = false) {
  mv.state = state;
  mv.center = center;
  if (!mv.scene) { mv.png = target(state, center).png; showShot(); return; }
  if (mv.comparing) return;
  const t = target(state, center);
  const sig = JSON.stringify([t.parts.map((p) => p.url), t.motionUrl]);
  if (sig === mv.sig && !force) { mv.asm.update(state.product && t.motionUrl ? state.product : null, mv.motion); return; }
  mv.sig = sig;
  mv.png = t.png;
  mv.fallback = t.noStl ? STL_FAILED : null;
  showShot();
  if (t.motionUrl !== mv.motionUrl) {
    mv.motionUrl = t.motionUrl;
    mv.motionBar.stop();
    mv.motion = t.motionUrl ? await loadMotion(t.motionUrl) : null;
  }
  const rest = mv.motion && !mv.motion.error ? mv.motion.rest : {};
  const ok = await mv.scene.showParts(t.parts.map((p) => ({ ...p, matrix: rest[p.id] || null })));
  if (ok && t.parts.length) { mv.fallback = null; mv.shot.classList.add("gone"); mv.note.classList.add("gone"); }
  mv.asm.update(state.product && t.motionUrl ? state.product : null, mv.motion);
  mv.motionBar.update(t.motionUrl ? mv.motion : null);
}

// 对比：叠在一起时 b 是实体、a 是半透明的轮廓；左右并排时把 a 挪到左边
export async function showCompare(data, mode) {
  if (!mv.scene) return;
  mv.comparing = data;
  mv.motionBar.update(null);
  const prod = mv.state.product;
  const ver = (name) => (mv.state.versions || []).find((v) => v.name === name);
  const partsOf = (name) => {
    const v = ver(name);
    if (prod) return prod.parts.map((p) => ({ id: `${name}:${p.id}`, url: mv.fileUrl(name, `parts/${p.id}/model.stl`), color: p.color, finish: p.finish, pid: p.id }));
    return v && v.has_stl !== false ? [{ id: `${name}:main`, url: mv.fileUrl(name, "model.stl"), color: cssVar("--part"), finish: "metal" }] : [];
  };
  const motions = {};
  for (const name of [data.a, data.b]) motions[name] = prod ? await loadMotion(mv.fileUrl(name, "motion.json")) : null;
  const a = partsOf(data.a);
  const b = partsOf(data.b);
  const restOf = (name, p) => (motions[name] && !motions[name].error && p.pid ? motions[name].rest[p.pid] : null);
  const list = [...a.map((p) => ({ ...p, matrix: restOf(data.a, p) })), ...b.map((p) => ({ ...p, matrix: restOf(data.b, p) }))];
  data.notes = [!a.length ? `第 ${data.a.replace(/^v/, "")} 版：这个版本没有三维文件，先用截图代替。` : null,
    !b.length ? `第 ${data.b.replace(/^v/, "")} 版：这个版本没有三维文件，先用截图代替。` : null].filter(Boolean);
  await mv.scene.showParts(list);
  const op = {};
  for (const p of a) op[p.id] = mode === "overlay" ? 0.25 : 1;
  mv.scene.setOpacity(op);
  mv.scene.setTint(a.map((p) => p.id), "--mute");
  if (mode === "split") {
    const box = mv.scene.box();
    const dx = (box.max.x - box.min.x) * 0.65 + 10;
    const poses = {};
    for (const p of list) {
      const m = (p.matrix || [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]).slice();
      m[3] += p.id.startsWith(`${data.a}:`) ? -dx : dx;
      poses[p.id] = m;
    }
    mv.scene.setPoses(poses);
  }
}

export function hideCompare() {
  mv.comparing = null;
  mv.sig = "";
  if (mv.state) updateModel(mv.state, mv.center, true);
}
