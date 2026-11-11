"""桌面端的视觉规范（第二版计划 3 Task 2）：颜色、对比度、线和圆角、不用阴影渐变和网络字体。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "cad_agent" / "desk" / "static" / "css"
TOKENS = CSS_DIR / "tokens.css"

LIGHT = {"--paper": "#F4F1EA", "--ink": "#1B1B1B", "--ink-2": "#6B675E", "--accent": "#1F4FD8", "--ok": "#2E6B3F", "--bad": "#B3261E"}
DARK = {"--paper": "#0F2A4A", "--ink": "#E6EEF8", "--ink-2": "#9DB7D6", "--accent": "#FFD166", "--ok": "#8FD6A3", "--bad": "#FF8A80"}
_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def _block(css: str, selector: str) -> str:
    """取出某个选择器后面第一对大括号里的内容（不处理嵌套的选择器）。"""
    start = css.index(selector + " {")
    return css[css.index("{", start) + 1: css.index("}", start)]


def _vars(block: str) -> dict[str, str]:
    return {k: v.strip() for k, v in _DECL.findall(block)}


def _palettes() -> tuple[dict[str, str], dict[str, str]]:
    css = TOKENS.read_text(encoding="utf-8")
    return _vars(_block(css, ":root")), _vars(_block(css, ':root[data-theme="dark"]'))


def _resolve(value: str, table: dict[str, str]) -> str:
    m = re.fullmatch(r"var\((--[\w-]+)\)", value)
    return _resolve(table[m.group(1)], table) if m else value


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    def ch(i: int) -> float:
        c = int(h[i:i + 2], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(0) + 0.7152 * ch(2) + 0.0722 * ch(4)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _css_files() -> list[Path]:
    files = sorted(CSS_DIR.glob("*.css"))
    assert files, "还没有样式文件"
    return files


def test_token_values():
    light, dark = _palettes()
    for name, value in LIGHT.items():
        assert light[name].upper() == value, name
    for name, value in DARK.items():
        assert dark[name].upper() == value, name
    assert set(light) >= {"--paper", "--ink", "--ink-2", "--accent", "--ok", "--bad", "--line", "--line-soft", "--part", "--part-edge",
                          "--font-ui", "--font-mono", "--s-1", "--s-2", "--s-3", "--s-4", "--s-5", "--s-6", "--radius"}
    colour_names = {k for k, v in light.items() if v.startswith("#") or v.startswith("var(--")}
    assert colour_names == {k for k, v in dark.items() if v.startswith("#") or v.startswith("var(--")}
    assert light["--part"].upper() == "#D9D5CB" and dark["--part"].upper() == "#7FA3CC"
    assert light["--line"] == "var(--ink)" and light["--line-soft"] == "var(--ink-2)" and light["--part-edge"] == "var(--ink)"
    assert light["--radius"] == "2px"
    assert [light[f"--s-{i}"] for i in range(1, 7)] == ["4px", "8px", "12px", "16px", "24px", "32px"]
    assert light["--font-ui"] == '"Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif'
    assert light["--font-mono"] == '"Cascadia Mono", "SF Mono", Consolas, monospace'
    css = TOKENS.read_text(encoding="utf-8")
    assert ':root[data-theme="system"]' in css and "prefers-color-scheme: dark" in css


def test_system_theme_uses_dark_palette_under_media_query():
    css = TOKENS.read_text(encoding="utf-8")
    media = css[css.index("@media (prefers-color-scheme: dark)"):]
    _, dark = _palettes()
    system = _vars(_block(media, ':root[data-theme="system"]'))
    assert {k: system[k] for k in DARK} == {k: dark[k] for k in DARK}


def test_contrast_at_least_4_5():
    for table in _palettes():
        paper = _resolve(table["--paper"], table)
        for name in ("--ink", "--ink-2", "--accent", "--ok", "--bad"):
            ratio = _contrast(_resolve(table[name], table), paper)
            assert ratio >= 4.5, (name, round(ratio, 2))


def test_no_shadow_gradient_blur_webfont():
    for path in _css_files():
        text = path.read_text(encoding="utf-8")
        for bad in ("box-shadow", "text-shadow", "gradient(", "blur(", "@font-face", "@import", "http://", "https://"):
            assert bad not in text, (path.name, bad)


def test_radius_at_most_2px():
    allowed = {"0", "var(--radius)", "1px", "2px", "50%"}
    for path in _css_files():
        for value in re.findall(r"border-radius\s*:\s*([^;]+);", path.read_text(encoding="utf-8")):
            assert value.strip() in allowed, (path.name, value)


def test_colors_only_in_tokens():
    for path in _css_files():
        if path.name == "tokens.css":
            continue
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), path.name
        assert "rgb(" not in text and "rgba(" not in text and "hsl(" not in text, path.name


def test_reduced_motion_rule_exists():
    text = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    block = text[text.index("@media (prefers-reduced-motion: reduce)"):]
    assert "transition" in block and "animation" in block


def test_base_has_three_buttons_section_head_and_states():
    text = (CSS_DIR / "base.css").read_text(encoding="utf-8")
    for sel in (".btn-primary", ".btn ", ".btn-text", ".section-head", ".ok", ".bad", ".none", ":focus-visible", "font-size: 14px"):
        assert sel in text, sel
