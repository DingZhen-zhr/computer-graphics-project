// 运动条：每个关节一条（几个关节时左右切换）；播放 / 暂停、滑条、当前值；下面一排小点，每个取样位置一个。
import { h } from "./dom.js";
import { fmtNum } from "./format.js";
import { createPlayer, hitAt, MOTION_BROKEN, poseAt } from "./motion-logic.js";

const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const unitText = (j) => (j.unit === "deg" ? "°" : " 毫米");

export function mountMotion(el, { onPose, onHit, partName }) {
  const ui = { motion: null, joint: null, index: 0 };
  const playBtn = h("button", { type: "button", class: "play", "aria-label": "播放" }, "▶");
  const prev = h("button", { type: "button", class: "btn-text", "aria-label": "上一个会动的地方" }, "‹");
  const next = h("button", { type: "button", class: "btn-text", "aria-label": "下一个会动的地方" }, "›");
  const name = h("span", {});
  const range = h("input", { type: "range", step: "0.5", "aria-label": "动到哪里" });
  const value = h("b", { class: "num" });
  const ticks = h("div", { class: "ticks", "aria-hidden": "true" });
  const status = h("div", { class: "st", role: "status" });
  el.replaceChildren(h("div", { class: "row" }, prev, playBtn, name, range, value, next), ticks, status);

  const player = createPlayer((f) => {
    if (!f.joint) return;
    range.value = String(f.value);
    value.textContent = `${fmtNum(f.value)}${unitText(f.joint)}`;
    playBtn.textContent = f.playing ? "❚❚" : "▶";
    playBtn.setAttribute("aria-label", f.playing ? "暂停" : "播放");
    onPose(poseAt(f.joint, f.value));
    const hit = f.joint.samples.find((s) => s.hits && s.hits.length && Math.abs(s.value - f.value) < 1e-6);
    onHit(hit ? [hit.hits[0].a, hit.hits[0].b] : []);
  }, { reduced: reduced() });
  const loop = () => { player.tick(); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);

  playBtn.addEventListener("click", () => (player.state().playing ? player.pause() : player.play()));
  range.addEventListener("input", () => player.seek(Number(range.value)));
  prev.addEventListener("click", () => choose(ui.index - 1));
  next.addEventListener("click", () => choose(ui.index + 1));

  function choose(i) {
    const joints = ui.motion.joints;
    ui.index = (i + joints.length) % joints.length;
    const j = joints[ui.index];
    ui.joint = j;
    name.textContent = j.label;
    range.min = String(j.samples[0].value);
    range.max = String(j.samples[j.samples.length - 1].value);
    ticks.replaceChildren(...j.samples.map((s) => h("i", { class: s.hits && s.hits.length ? "hit" : "" })));
    const hit = hitAt(j);
    status.classList.toggle("bad", !!hit);
    status.textContent = hit ? `在 ${fmtNum(hit.value)}${unitText(j)} 附近碰到了：${partName(hit.a)} 和 ${partName(hit.b)}`
      : `动到哪里都没有碰到别的零件（量了 ${j.samples.length} 个位置）`;
    prev.hidden = next.hidden = joints.length < 2;
    player.select(j);
  }

  return {
    // motion 是 loadMotion 的结果；null 表示没有会动的地方（运动条藏起来）
    update(motion) {
      if (motion === ui.motion) return;
      player.stop();
      ui.motion = motion;
      const has = !!motion && (motion.error || (motion.joints && motion.joints.length));
      el.classList.toggle("gone", !has);
      document.body.classList.toggle("has-motion", !!has);
      if (!has) return;
      if (motion.error) {
        [playBtn, range, prev, next].forEach((x) => { x.disabled = true; });
        name.textContent = "";
        value.textContent = "";
        ticks.replaceChildren();
        status.textContent = MOTION_BROKEN;
        status.classList.add("bad");
        return;
      }
      [playBtn, range, prev, next].forEach((x) => { x.disabled = false; });
      choose(0);
    },
    stop() { player.stop(); },
  };
}
