// 参数面板的纯逻辑：滑块范围、哪些参数改了、输入框里的数对不对。

const clean = (x) => Number(Number(x).toFixed(6));
const isCount = (param) => param.unit === "1" && Number.isInteger(Number(param.value));

// 单位是 1 的整数：当前值上下 3（最小 1），步长 1；数值是 0：0 到 10；其余：当前值的 0.5 到 1.5 倍，分成大约 100 格
export function sliderRange(param) {
  const v = Number(param.value);
  if (isCount(param)) return { min: Math.max(1, v - 3), max: v + 3, step: 1 };
  if (v === 0) return { min: 0, max: 10, step: 0.1 };
  const a = clean(v * 0.5);
  const b = clean(v * 1.5);
  const [min, max] = a < b ? [a, b] : [b, a];
  const step = Number(((max - min) / 100).toPrecision(1));
  return { min, max, step };
}

// 只返回和原值不一样的 {名字: 新值}
export function pendingChanges(params, edits) {
  const out = {};
  for (const p of params || []) {
    if (Object.prototype.hasOwnProperty.call(edits || {}, p.name) && Number(edits[p.name]) !== Number(p.value)) out[p.name] = Number(edits[p.name]);
  }
  return out;
}

export function validateEdit(param, text) {
  const t = String(text ?? "").trim();
  if (!t) return { ok: false, message: "请填一个数。" };
  if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t)) return { ok: false, message: "这里只能填数字。" };
  const value = Number(t);
  if (!Number.isFinite(value)) return { ok: false, message: "这个数太大了。" };
  if (isCount(param) && !Number.isInteger(value)) return { ok: false, message: "这个参数是个数，只能填整数。" };
  return { ok: true, value };
}
