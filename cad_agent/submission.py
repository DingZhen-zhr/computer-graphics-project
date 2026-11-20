"""一键整理作业提交材料（3.0 计划 5 Task 1）：datum submission <目录> [--session <会话编号> ...]

文件夹结构照设计文档第 9 节：代码、提示词与工具定义、测试需求与验收结果、参数化源文件与 STEP、运行日志、配置和运行说明，
外加一份清单.md。整理前先搜一遍要复制的文字文件里有没有 key：搜到就停下，说明是哪个文件哪一行，不生成。
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

CODE_DIRS = ("cad_agent", "benchmarks", "scripts", "tests")
SKIP = {".venv", "__pycache__", "sessions", "results", ".pytest_cache", ".simplecad", "node_modules"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".txt", ".js", ".css", ".html"}
VERSION_FILES = ("model.py", "assembly.py", "model.step", "product.step", "model.stl", "view.png", "checks.json", "motion.json", "brief.json")


@dataclass
class SubmissionReport:
    folder: Path | None
    items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _secrets() -> list[str]:
    """环境变量里名字含 KEY、TOKEN 的值，和钥匙串里存的 key（只在内存里比较，不打印）。"""
    vals = [v.strip() for k, v in os.environ.items() if ("KEY" in k.upper() or "TOKEN" in k.upper()) and len(v.strip()) >= 12]
    try:
        from cad_agent.keystore import get_key
        from cad_agent.settings import load_settings

        stored = get_key(load_settings().provider, "")
        if stored:
            vals.append(stored)
    except Exception:  # noqa: BLE001 - 钥匙串不可用时只用环境变量比较
        pass
    return [v for v in set(vals) if v]


def _scan(files: list[Path], base: Path, secrets: list[str]) -> list[str]:
    hits = []
    for f in files:
        if f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if any(s in line for s in secrets):
                hits.append(f"{f.relative_to(base).as_posix()} 第 {i} 行里有 key")
    return hits


def _copy_tree(src: Path, dst: Path) -> list[Path]:
    out = []
    for p in src.rglob("*"):
        if p.is_file() and not (set(p.relative_to(src).parts) & SKIP):
            t = dst / p.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, t)
            out.append(t)
    return out


def _free_folder(target: Path) -> Path:
    if not target.exists():
        return target
    n = 2
    while (target.parent / f"{target.name}-{n}").exists():
        n += 1
    return target.parent / f"{target.name}-{n}"


def _session_files(session: Path) -> list[tuple[Path, str]]:
    """会话里要带走的文件：(源文件, 放在提交包里的相对路径)。"""
    out = []
    for name in ("log.jsonl", "brief.json", "checks.json"):
        if (session / name).is_file():
            out.append((session / name, f"05-运行日志/{session.name}/{name}"))
    vroot = session / "versions"
    for v in sorted(vroot.iterdir()) if vroot.is_dir() else []:
        for p in v.rglob("*"):
            if p.is_file() and (p.name in VERSION_FILES or p.suffix in (".step", ".stl")):
                out.append((p, f"04-参数化源文件与STEP/{session.name}/{p.relative_to(vroot).as_posix()}"))
    return out


def build_submission(sessions: list[Path], target: Path, *, repo_root: Path) -> SubmissionReport:
    secrets = _secrets()
    planned: list[tuple[Path, str]] = []
    for d in CODE_DIRS:
        planned += [(p, f"01-代码/{d}/{p.relative_to(repo_root / d).as_posix()}") for p in (repo_root / d).rglob("*")
                    if p.is_file() and not (set(p.relative_to(repo_root / d).parts) & SKIP)]
    planned.append((repo_root / "docs" / "prompts-and-tools.md", "02-提示词与工具定义/prompts-and-tools.md"))
    planned += [(p, f"03-测试需求与验收结果/tasks/{p.name}") for p in sorted((repo_root / "benchmarks" / "tasks").glob("*.yaml"))]
    results = repo_root / "docs" / "results-v3.md"
    if results.is_file():
        planned.append((results, "03-测试需求与验收结果/results-v3.md"))
    for s in sessions:
        planned += _session_files(Path(s))
    for name, rel in (("config.example.toml", "06-配置和运行说明/config.example.toml"), ("README.md", "06-配置和运行说明/README.md"),
                      ("docs/install-notes.md", "06-配置和运行说明/install-notes.md")):
        if (repo_root / name).is_file():
            planned.append((repo_root / name, rel))
    hits = []
    for src, rel in planned:
        hits += [h.replace(src.name, rel, 1) for h in _scan([src], src.parent, secrets)]
    if hits:
        return SubmissionReport(folder=None, warnings=hits)
    folder = _free_folder(Path(target))
    for src, rel in planned:
        dst = folder / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    items = [
        {"要求": "代码", "位置": "01-代码/", "状态": "已放入"},
        {"要求": "提示词与工具定义", "位置": "02-提示词与工具定义/", "状态": "已放入"},
        {"要求": "测试需求与验收结果", "位置": "03-测试需求与验收结果/", "状态": "已放入" if results.is_file() else "评测结果文档还没有写（docs/results-v3.md）"},
    ]
    for s in sessions:
        has = (Path(s) / "versions").is_dir() and any((Path(s) / "versions").iterdir())
        items.append({"要求": f"参数化源文件与 STEP（会话 {Path(s).name}）", "位置": f"04-参数化源文件与STEP/{Path(s).name}/",
                      "状态": "已放入" if has else "这个会话没有交付版本，只带了运行日志"})
    items += [{"要求": "运行日志", "位置": "05-运行日志/", "状态": "已放入" if sessions else "没有选会话"},
              {"要求": "配置和运行说明", "位置": "06-配置和运行说明/", "状态": "已放入"}]
    lines = ["# 提交材料清单", "", "| 要求 | 放在哪里 | 状态 |", "|---|---|---|"] + [f"| {i['要求']} | {i['位置']} | {i['状态']} |" for i in items]
    (folder / "清单.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SubmissionReport(folder=folder, items=items)


def submission_main(argv: list[str]) -> int:
    from cad_agent.paths import sessions_dir

    parser = argparse.ArgumentParser(prog="datum submission", description="整理作业提交材料")
    parser.add_argument("target", help="放到哪个目录（已经存在就另建一个带序号的）")
    parser.add_argument("--session", nargs="*", default=None, help="要带上的会话编号；不给就带上全部有交付版本的会话")
    args = parser.parse_args(argv)
    root = sessions_dir()
    if args.session:
        chosen = [root / s for s in args.session]
        missing = [p.name for p in chosen if not p.is_dir()]
        if missing:
            print(f"没有这些会话：{'、'.join(missing)}")
            return 2
    else:
        chosen = [p for p in sorted(root.iterdir()) if p.is_dir() and (p / "versions").is_dir()] if root.is_dir() else []
    report = build_submission(chosen, Path(args.target), repo_root=Path(__file__).resolve().parent.parent)
    if report.folder is None:
        print("发现 key，没有生成提交材料：")
        for w in report.warnings:
            print(f"- {w}")
        return 1
    print(f"提交材料放在 {report.folder}")
    return 0
