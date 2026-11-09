"""给一个会话里还没有 model.stl 的版本补导出一份 STL（网页 3D 预览要用）。

    .venv\\Scripts\\python scripts\\backfill_stl.py <会话目录>

只在本地用 SCA 重新运行该版本的 model.py，不调用大模型，不花钱。已有 model.stl 的版本跳过。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cad_agent.notebook import RenderedNotebook  # noqa: E402
from cad_agent.sandbox.execute import run_job  # noqa: E402
from cad_agent.session import VERSION_RE  # noqa: E402


def backfill(session_dir: Path, timeout_s: float = 120) -> list[str]:
    """返回每个版本的处理结果（中文一行）。"""
    root = Path(session_dir) / "versions"
    if not root.is_dir():
        return [f"{session_dir} 里没有 versions 目录"]
    report = []
    for v in sorted((p for p in root.iterdir() if VERSION_RE.match(p.name)), key=lambda p: int(p.name[1:])):
        if (v / "model.stl").is_file():
            report.append(f"{v.name}：已有 model.stl，跳过")
            continue
        text = (v / "model.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="cad-agent-stl-") as tmp:
            out = Path(tmp) / "model.stl"
            result = run_job(RenderedNotebook(text=text, cell_lines={}), [], set(), export_stl=out, timeout_s=timeout_s)
            if result.stl_path is not None and result.stl_path.is_file():
                shutil.copyfile(result.stl_path, v / "model.stl")
                report.append(f"{v.name}：已导出 model.stl（{(v / 'model.stl').stat().st_size} 字节）")
            else:
                why = result.stl_error or (result.error or {}).get("message") or "原因不明"
                report.append(f"{v.name}：导出失败：{why}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="给会话里的各版本补导出 model.stl")
    parser.add_argument("session_dir")
    args = parser.parse_args(argv)
    lines = backfill(Path(args.session_dir))
    print("\n".join(lines))
    return 0 if all("失败" not in line and "没有" not in line for line in lines) else 1


if __name__ == "__main__":
    sys.exit(main())
