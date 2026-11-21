// 运动数据（版本目录里的 motion.json）：校验、按关节的值算每个零件的位置、播放器的状态（纯逻辑，可测）。
// 界面播放的姿态和碰撞检查用的是同一份取样，两个取样之间才插值。

export const MOTION_BROKEN = "动画数据读不出来，先按装好时的样子显示。";
const DURATION_MS = 2200;

const isMat = (m) => Array.isArray(m) && m.length === 16 && m.every((x) => typeof x === "number" && Number.isFinite(x));

export function validateMotion(data) {
  if (!data || typeof data !== "object" || !data.parts || !data.rest || !Array.isArray(data.joints)) return false;
  if (!Object.values(data.rest).every(isMat)) return false;
  for (const j of data.joints) {
    if (!j || typeof j.id !== "string" || !Array.isArray(j.samples) || !j.samples.length) return false;
    for (const s of j.samples) if (typeof s.value !== "number" || !s.poses || !Object.values(s.poses).every(isMat)) return false;
  }
  return true;
}

export async function loadMotion(url, fetchFn = fetch) {
  try {
    const r = await fetchFn(url);
    if (!r.ok) return { error: MOTION_BROKEN };
    const data = await r.json();
    return validateMotion(data) ? data : { error: MOTION_BROKEN };
  } catch {
    return { error: MOTION_BROKEN };
  }
}

// ---- 插值：平移线性，转动用四元数球面插值 ----
function toQuat(m) {
  const [a, b, c, , d, e, f, , g, hh, i] = m;
  const tr = a + e + i;
  let x; let y; let z; let w;
  if (tr > 0) {
    const s = Math.sqrt(tr + 1) * 2;
    w = s / 4; x = (hh - f) / s; y = (c - g) / s; z = (d - b) / s;
  } else if (a > e && a > i) {
    const s = Math.sqrt(1 + a - e - i) * 2;
    w = (hh - f) / s; x = s / 4; y = (b + d) / s; z = (c + g) / s;
  } else if (e > i) {
    const s = Math.sqrt(1 + e - a - i) * 2;
    w = (c - g) / s; x = (b + d) / s; y = s / 4; z = (f + hh) / s;
  } else {
    const s = Math.sqrt(1 + i - a - e) * 2;
    w = (d - b) / s; x = (c + g) / s; y = (f + hh) / s; z = s / 4;
  }
  return [x, y, z, w];
}

function slerp(q1, q2, t) {
  let [x2, y2, z2, w2] = q2;
  let cos = q1[0] * x2 + q1[1] * y2 + q1[2] * z2 + q1[3] * w2;
  if (cos < 0) { cos = -cos; x2 = -x2; y2 = -y2; z2 = -z2; w2 = -w2; }
  let k1 = 1 - t; let k2 = t;
  if (cos < 0.9995) {
    const th = Math.acos(cos); const s = Math.sin(th);
    k1 = Math.sin((1 - t) * th) / s; k2 = Math.sin(t * th) / s;
  }
  const q = [q1[0] * k1 + x2 * k2, q1[1] * k1 + y2 * k2, q1[2] * k1 + z2 * k2, q1[3] * k1 + w2 * k2];
  const n = Math.hypot(...q);
  return q.map((v) => v / n);
}

function fromQuat([x, y, z, w], t) {
  return [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), t[0],
    2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), t[1],
    2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), t[2], 0, 0, 0, 1];
}

function mix(m1, m2, t) {
  const tr = [3, 7, 11].map((i) => m1[i] + (m2[i] - m1[i]) * t);
  return fromQuat(slerp(toQuat(m1), toQuat(m2), t), tr);
}

// 关节放到 value 时每个零件的矩阵：在相邻两个取样之间插值；超出范围取两端
export function poseAt(joint, value) {
  const s = joint.samples;
  if (value <= s[0].value) return { ...s[0].poses };
  const last = s[s.length - 1];
  if (value >= last.value) return { ...last.poses };
  let i = 0;
  while (i < s.length - 2 && s[i + 1].value < value) i += 1;
  const a = s[i]; const b = s[i + 1];
  const t = b.value === a.value ? 0 : (value - a.value) / (b.value - a.value);
  const out = {};
  for (const id of Object.keys(a.poses)) out[id] = b.poses[id] ? mix(a.poses[id], b.poses[id], t) : a.poses[id];
  return out;
}

// 碰到的位置
export function hitAt(joint) {
  const s = joint.samples.find((x) => x.hits && x.hits.length);
  return s ? { value: s.value, a: s.hits[0].a, b: s.hits[0].b } : null;
}

function ease(t) {   // cubic-bezier(0.65, 0, 0.35, 1) 的近似：前后慢、中间快
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

// 播放器：来回播放，一次单程 2.2 秒。now 由调用方给（测试里可以控制时间）
export function createPlayer(onFrame, { reduced = false, now = () => performance.now() } = {}) {
  const st = { joint: null, value: 0, playing: false, dir: 1, t0: 0 };
  const emit = () => onFrame && onFrame({ joint: st.joint, value: st.value, playing: st.playing });
  const lo = () => st.joint.samples[0].value;
  const hi = () => st.joint.samples[st.joint.samples.length - 1].value;
  const rest = () => (lo() <= 0 && hi() >= 0 ? 0 : lo());
  return {
    state: () => ({ ...st }),
    select(joint) { st.joint = joint; st.playing = false; st.value = joint ? rest() : 0; emit(); },
    play() { if (!st.joint || reduced) return false; st.playing = true; st.t0 = now(); st.from = st.value; emit(); return true; },
    pause() { st.playing = false; emit(); },
    seek(value) { if (!st.joint) return; st.playing = false; st.value = Math.min(hi(), Math.max(lo(), value)); emit(); },
    stop() { st.playing = false; if (st.joint) st.value = rest(); emit(); },
    tick() {
      if (!st.playing || !st.joint) return false;
      // 这一段从 st.from 走到这个方向的尽头；从中间接着播时，时间按剩下的路程缩短
      const end = st.dir > 0 ? hi() : lo();
      const whole = hi() - lo();
      const ms = whole > 0 ? DURATION_MS * Math.abs(end - st.from) / whole : 0;
      const k = ms > 0 ? Math.min(1, (now() - st.t0) / ms) : 1;
      st.value = st.from + (end - st.from) * ease(k);
      if (k >= 1) { st.value = end; st.from = end; st.dir = -st.dir; st.t0 = now(); }
      emit();
      return true;
    },
  };
}
