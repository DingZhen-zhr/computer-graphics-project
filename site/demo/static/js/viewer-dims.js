// 3D 视图里的外形尺寸：三条尺寸线的端点、延伸线和文字位置（世界坐标，z 朝上）；以及什么时候退回截图。纯逻辑。
import { fmtNum } from "./format.js";

export const NO_WEBGL = "这台电脑现在显示不了三维画面，先用截图代替。";
export const STL_FAILED = "三维模型没有加载出来，先用截图代替。";

const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];

function seg(axis, from, to, extFrom, extTo, length) {
  return { axis, from, to, label: mid(from, to), text: fmtNum(length), length, ext: [[extFrom, from], [extTo, to]] };
}

// bbox = [x0, y0, z0, x1, y1, z1]。尺寸线离开包围盒一段距离，用延伸线和盒子的棱连起来
export function dimSegments(bbox) {
  const [x0, y0, z0, x1, y1, z1] = bbox.map(Number);
  const dx = x1 - x0;
  const dy = y1 - y0;
  const dz = z1 - z0;
  const off = Math.max(2, 0.12 * Math.max(dx, dy, dz));
  return [
    // x：前面底边，往 −y 挪出去
    seg("x", [x0, y0 - off, z0], [x1, y0 - off, z0], [x0, y0, z0], [x1, y0, z0], dx),
    // y：右边底边，往 +x 挪出去
    seg("y", [x1 + off, y0, z0], [x1 + off, y1, z0], [x1, y0, z0], [x1, y1, z0], dy),
    // z：左前竖边，往 −x 挪出去
    seg("z", [x0 - off, y0, z0], [x0 - off, y0, z1], [x0, y0, z0], [x0, y0, z1], dz),
  ];
}

export function fallbackReason({ webgl, stlOk }) {
  if (!webgl) return NO_WEBGL;
  if (!stlOk) return STL_FAILED;
  return null;
}
