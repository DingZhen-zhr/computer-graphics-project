// 三维舞台的纯逻辑（可测，不依赖 three.js）：坐标轴小图、材质、多零件的炸开和透视、名字标签的位置。
// 坐标约定：和建模一样，Z 朝上（相机的 up 是 +Z）。四元数写成 [x, y, z, w]。

function rotate(q, v) {
  const [x, y, z, w] = q;
  const ix = w * v[0] + y * v[2] - z * v[1];
  const iy = w * v[1] + z * v[0] - x * v[2];
  const iz = w * v[2] + x * v[1] - y * v[0];
  const iw = -x * v[0] - y * v[1] - z * v[2];
  return [ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x];
}
const conj = ([x, y, z, w]) => [-x, -y, -z, w];

export const AXES = [{ axis: "X", v: [1, 0, 0], color: "--axis-x" }, { axis: "Y", v: [0, 1, 0], color: "--axis-y" }, { axis: "Z", v: [0, 0, 1], color: "--axis-z" }];

// 每个轴（正负两头）在小图上的位置：x 向右、y 向下（屏幕坐标，以小图中心为原点，半径 1）；depth 大的在前面
export function axisLayout(cameraQuaternion) {
  const inv = conj(cameraQuaternion);
  const out = [];
  for (const a of AXES) {
    const p = rotate(inv, a.v);
    out.push({ axis: a.axis, x: p[0], y: -p[1], depth: p[2], positive: true, color: a.color });
    out.push({ axis: a.axis, x: -p[0], y: p[1], depth: -p[2], positive: false, color: a.color });
  }
  return out.sort((a, b) => a.depth - b.depth);
}

export const VIEWS = { front: [0, -1, 0], top: [0, 0, 1], right: [1, 0, 0], iso: [1, -1.2, 0.9], bottom: [0, 0, -1] };

// 点一个轴：相机转到那一头去看（返回从目标指向相机的方向）
export function snapDirection(axis, positive) {
  const a = AXES.find((x) => x.axis === axis);
  return a.v.map((c) => (positive ? c : 0 - c));
}

// 转到正上或正下时，相机的 up（+Z）和视线平行会翻转：把方向往 -Y 偏一点点，并给一个稳定的 up
export function safeView(dir) {
  const n = Math.hypot(...dir) || 1;
  const d = dir.map((c) => c / n);
  if (Math.abs(d[2]) > 0.999) return { dir: [0, -0.001, Math.sign(d[2])], up: [0, 0, 1] };
  return { dir: d, up: [0, 0, 1] };
}

// 三种质感：哑光、金属、抛光；深色时整体略提亮
export function materialFor(finish, color, theme) {
  const base = { matte: { roughness: 0.75, metalness: 0.05 }, metal: { roughness: 0.42, metalness: 0.35 }, polished: { roughness: 0.25, metalness: 0.45 } };
  const m = base[finish] || base.matte;
  return { color, roughness: m.roughness, metalness: m.metalness, lift: theme === "dark" ? 0.12 : 0 };
}

// 炸开：沿方向平移 amount × scale（scale 是产品包围盒对角线的 0.6 倍）；矩阵按行 16 个数
export function explodedMatrix(rest, direction, amount, scale) {
  const m = rest.slice();
  const k = amount * scale;
  m[3] += direction[0] * k;
  m[7] += direction[1] * k;
  m[11] += direction[2] * k;
  return m;
}

// 单独看一个零件、透视时，每个零件的不透明度
export function isolateOpacity(partId, focusId, xray) {
  if (!focusId) return xray ? 0.35 : 1;
  if (partId === focusId) return xray ? 0.9 : 1;
  return xray ? 0.22 : 0.12;
}

// 名字标签：放在零件屏幕位置的左上或右上（看在屏幕哪一半），彼此重叠时依次往上挪
export function layoutLabels(points, { width, height = 0, boxW = 90, boxH = 24, gap = 6, offset = 40 } = {}) {
  const placed = [];
  const order = points.map((p, i) => ({ ...p, i })).filter((p) => p.visible !== false).sort((a, b) => a.y - b.y);
  for (const p of order) {
    const left = p.x < width / 2;
    const x = left ? p.x - offset - boxW : p.x + offset;
    let y = p.y - offset - boxH;
    const overlaps = (yy) => placed.some((q) => x < q.x + q.w && q.x < x + boxW && yy < q.y + q.h + gap && q.y < yy + boxH + gap);
    let guard = 0;
    while (overlaps(y) && guard < 50) {
      y -= boxH + gap;
      guard += 1;
    }
    placed.push({ id: p.id, x, y: Math.max(y, -height), w: boxW, h: boxH, ax: p.x, ay: p.y, left });
  }
  return placed;
}
