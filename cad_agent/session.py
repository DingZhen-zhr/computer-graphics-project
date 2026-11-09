"""会话目录：日志、当前状态、各个交付版本。

sessions/<时间>/
  log.jsonl  brief.json  features.json  checks.json  model.py
  versions/v1/ model.py model.step view.png checks.json brief.json changes.md
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any

from cad_agent.brief import Brief
from cad_agent.checks.spec import CheckResult

VERSION_RE = re.compile(r"^v(\d+)$")


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


class Session:
    def __init__(self, root: Path) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        stamp = _now().strftime("%Y%m%d-%H%M%S")
        n = 1
        while True:
            candidate = root / (stamp if n == 1 else f"{stamp}-{n}")
            try:
                candidate.mkdir()
                break
            except FileExistsError:
                n += 1
        self.dir = candidate

    def log(self, kind: str, **data: Any) -> None:
        """往 log.jsonl 追加一行；自动加上 ts 和 kind。"""
        row = {"ts": _now().isoformat(timespec="milliseconds"), "kind": kind, **data}
        with (self.dir / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def save_state(self, brief: Brief, features_list: list[dict], checks_raw: list[dict], notebook_text: str) -> None:
        _write_json(self.dir / "brief.json", brief.to_dict())
        _write_json(self.dir / "features.json", features_list)
        _write_json(self.dir / "checks.json", checks_raw)
        (self.dir / "model.py").write_text(notebook_text, encoding="utf-8")

    def versions(self) -> list[Path]:
        root = self.dir / "versions"
        if not root.is_dir():
            return []
        found = [(int(m.group(1)), p) for p in root.iterdir() if p.is_dir() and (m := VERSION_RE.match(p.name))]
        return [p for _, p in sorted(found)]

    def new_version(
        self,
        *,
        notebook_text: str,
        brief: Brief,
        check_results: list[CheckResult],
        changes: list[str],
        step_src: Path,
        png_src: Path,
    ) -> Path:
        existing = self.versions()
        n = int(VERSION_RE.match(existing[-1].name).group(1)) + 1 if existing else 1  # type: ignore[union-attr]
        v = self.dir / "versions" / f"v{n}"
        v.mkdir(parents=True)
        (v / "model.py").write_text(notebook_text, encoding="utf-8")
        shutil.copyfile(step_src, v / "model.step")
        shutil.copyfile(png_src, v / "view.png")
        _write_json(v / "checks.json", [r.to_dict() for r in check_results])
        _write_json(v / "brief.json", brief.to_dict())
        lines = [f"# v{n} 变更说明", ""] + ([f"- {c}" for c in changes] if changes else ["- （需求单参数没有变化）"])
        (v / "changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return v
