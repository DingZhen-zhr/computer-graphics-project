"""桌面端的视觉规范（3.0 计划 3 Task 1，换掉第二版的 8 条）：展台的两套颜色、对比度、本地字体、颜色只在 tokens.css、
不用投影阴影做卡片、减少动态效果、圆角、三种按钮。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "cad_agent" / "desk" / "static"
CSS_DIR = STATIC / "css"
TOKENS = CSS_DIR / "tokens.css"

# 设计文档第 7.2 节（浅色的次要文字按偏离 D35 加深到 #5E5A66，才够 4.5:1）
LIGHT = {"--ink": "#17151B", "--mute": "#5E5A66", "--acc": "#17151B", "--move": "#4767E8", "--ok": "#1F8A4C", "--bad": "#C93A2E"}
DARK = {"--ink": "#EEF1F6", "--mute": "#8A93A6", "--acc": "#A9CBFF", "--move": "#7FB2FF", "--ok": "#7FE0A8", "--bad": "#FF8A80"}
LIGHT_BG = ("#FFFFFF", "#EEEDF1", "#D9D8DE")
DARK_BG = ("#1C2230", "#0A0D13", "#030405")
NAMES = {"--bg", "--ink", "--mute", "--acc", "--acc-ink", "--move", "--ok", "--bad", "--glass", "--line", "--panel",
         "--font-ui", "--font-num", "--r-pill", "--r-card", "--t"}
_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def _block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[css.index("{", start) + 1: css.index("}", start)]


def _vars(block: str) -> dict[str, str]:
    return {k: v.strip() for k, v in _DECL.findall(block)}


def _palettes() -> tuple[dict[str, str], dict[str, str]]:
    css = TOKENS.read_text(encoding="utf-8")
    return _vars(_block(css, ":root")), _vars(_block(css, ':root[data-theme="dark"]'))


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    def ch(i: int) -> float:
        c = int(h[i:i + 2], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(0) + 0.7152 * ch(2) + 0.0722 * ch(4)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _css() -> list[Path]:
    files = sorted(CSS_DIR.glob("*.css"))
    assert files, "还没有样式文件"
    return files


def test_token_values():
    light, dark = _palettes()
    for name, value in LIGHT.items():
        assert light[name].upper() == value, name
    for name, value in DARK.items():
        assert dark[name].upper() == value, name
    for stops, table in ((LIGHT_BG, light), (DARK_BG, dark)):
        assert [s.upper() for s in re.findall(r"#[0-9A-Fa-f]{6}", table["--bg"])] == list(stops)
        assert table["--bg"].startswith("radial-gradient(")
    assert NAMES <= set(light) and set(light) == set(dark)
    css = TOKENS.read_text(encoding="utf-8")
    system = _vars(_block(css, ':root[data-theme="system"]'))   # 跟随系统、系统是深色时：和深色一样
    assert all(dark[k] == v for k, v in system.items()) and {"--bg", "--ink", "--mute", "--acc"} <= set(system)
    assert "prefers-color-scheme: dark" in css and ':root[data-theme="system"]' in css


def test_contrast_at_least_4_5():
    light, dark = _palettes()
    for table, stops in ((light, LIGHT_BG), (dark, DARK_BG)):
        for name in ("--ink", "--mute"):
            for bg in stops:
                assert _contrast(table[name], bg) >= 4.5, (name, table[name], bg)
        assert _contrast(table["--acc-ink"], table["--acc"]) >= 4.5


def test_no_external_resources_and_font_is_local():
    for p in _css():
        assert "http" not in p.read_text(encoding="utf-8"), p.name
    base = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    assert re.search(r'@font-face\s*{[^}]*url\("\.\./fonts/Archivo\.ttf"\)\s*format\("truetype"\)', base)
    assert "font-display: swap" in base
    assert (STATIC / "fonts" / "Archivo.ttf").stat().st_size > 100_000
    assert "SIL Open Font License" in (STATIC / "fonts" / "OFL.txt").read_text(encoding="utf-8")


def test_colors_only_in_tokens():
    pat = re.compile(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(|hsla?\(")
    for p in _css():
        if p.name == "tokens.css":
            continue
        assert not pat.search(p.read_text(encoding="utf-8")), p.name


def test_no_box_shadow_cards():
    for p in _css():
        css = p.read_text(encoding="utf-8")
        for m in re.finditer(r"([^{}]+)\{([^}]*box-shadow[^}]*)\}", css):
            assert ":focus-visible" in m.group(1), (p.name, m.group(1).strip())


def test_reduced_motion_rule_exists():
    base = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*{(.*?)}\s*}", base, re.S)
    assert m and "transition: none" in m.group(1) and "animation: none" in m.group(1)


def test_radius_values():
    allowed = re.compile(r"^(0|50%|var\(--r-pill\)|var\(--r-card\)|(8|9|10|11|12)px|(16|17|18|19|20|21|22)px)$")
    for p in _css():
        for v in re.findall(r"border-radius\s*:\s*([^;]+);", p.read_text(encoding="utf-8")):
            assert allowed.match(v.strip()), (p.name, v)


def test_buttons_defined():
    base = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    for cls in (".btn-primary", ".btn-glass", ".btn-text"):
        assert cls in base, cls


def test_stage_steps_do_not_hijack_onboarding_ruler():
    """舞台左侧步骤栏不能用泛化的 .steps 选择器，否则会覆盖引导页的 .ruler.steps。"""
    stage = (CSS_DIR / "stage.css").read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w-])\.steps\b", stage), "stage.css 不应使用 .steps，应限定为 #steps"
    assert "#steps, .parts {" in stage


def test_prompt_focus_outline_is_on_capsule():
    """底部输入框获得焦点时，描边画在外层胶囊 .prompt 上，不画在内层 textarea 上。"""
    stage = (CSS_DIR / "stage.css").read_text(encoding="utf-8")
    assert ".prompt textarea:focus-visible" in stage and "outline: none" in stage
    assert ".prompt:has(textarea:focus-visible)" in stage
