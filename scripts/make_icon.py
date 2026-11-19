"""生成卡尺的图标（第二版计划 4 Task 3）：米白图纸底、墨色线条画一把游标卡尺，两个量爪之间一条制图蓝的尺寸线。

    .venv\\Scripts\\python scripts\\make_icon.py

先在 1024×1024 上画，再缩小，线条边缘更平滑。输出到 cad_agent/desk/static/：
icon.png（256×256）、icon.ico（16、24、32、48、64、128、256 七种尺寸）、icon.icns。
颜色取自视觉规范（设计文档第 5.3 节）。生成的三个文件提交进仓库。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "cad_agent" / "desk" / "static"
PAPER = (244, 241, 234, 255)   # #F4F1EA
INK = (27, 27, 27, 255)        # #1B1B1B
BLUE = (31, 79, 216, 255)      # #1F4FD8
SIZE = 1024
LINE = 30
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw(size: int = SIZE) -> Image.Image:
    im = Image.new("RGBA", (size, size), PAPER)
    d = ImageDraw.Draw(im)
    s = size / SIZE

    def pts(*xy: float) -> list[tuple[float, float]]:
        return [(xy[i] * s, xy[i + 1] * s) for i in range(0, len(xy), 2)]

    w = max(1, round(LINE * s))
    # 尺身：一根横梁，上面有刻度
    d.rectangle(pts(120, 300, 904, 420), outline=INK, width=w)
    for i, x in enumerate(range(330, 880, 44)):
        top = 300 + (16 if i % 5 else 0)
        d.line(pts(x, top + w / s, x, 360 if i % 5 else 380), fill=INK, width=max(1, round(12 * s)))
    # 固定量爪（左）：从横梁往下，内侧是一条竖直的测量面
    d.polygon(pts(120, 420, 290, 420, 290, 860, 120, 760), outline=INK, width=w)
    # 上面的内测量爪
    d.polygon(pts(120, 300, 290, 300, 290, 200, 220, 160), outline=INK, width=w)
    # 游标（右边可以滑动的一块），带自己的量爪
    d.rectangle(pts(540, 260, 720, 460), outline=INK, width=w)
    d.polygon(pts(540, 460, 720, 460, 720, 760, 540, 860), outline=INK, width=w)
    d.polygon(pts(540, 260, 720, 260, 620, 160, 540, 200), outline=INK, width=w)
    # 两个测量面之间的尺寸线：制图蓝，两头是箭头
    y = 700
    d.line(pts(330, y, 500, y), fill=BLUE, width=max(1, round(26 * s)))
    d.polygon(pts(300, y, 360, y - 36, 360, y + 36), fill=BLUE)
    d.polygon(pts(530, y, 470, y - 36, 470, y + 36), fill=BLUE)
    return im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico", sizes=ICO_SIZES)
    big.save(OUT / "icon.icns")
    print(f"已生成：{OUT / 'icon.png'}、icon.ico、icon.icns")


if __name__ == "__main__":
    main()
