"""会话目录：日志、当前状态、各个交付版本。

sessions/<时间>/
  log.jsonl  brief.json  features.json  checks.json  model.py
  versions/v1/ model.py model.step view.png checks.json brief.json changes.md
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from cad_agent.brief import Brief
from cad_agent.checks.spec import CheckResult
from cad_agent.llm.vision import redact_images

VERSION_RE = re.compile(r"^v(\d+)$")


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _write_json(path: Path, data: Any) -> None:
    """先写同目录下的临时文件再改名：写到一半出错（断电、磁盘满）时旧文件还在，不会留下半个文件。"""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


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

    @classmethod
    def open(cls, path: Path) -> "Session":
        """打开已有的会话目录，不新建；目录不存在抛 FileNotFoundError。"""
        path = Path(path)
        if not path.is_dir():
            raise FileNotFoundError(f"没有这个会话目录：{path}")
        obj = cls.__new__(cls)
        obj.dir = path
        return obj

    def read_log(self) -> list[dict]:
        """读 log.jsonl；坏掉的行（不是 JSON、不是对象、没有 kind）跳过。"""
        try:
            text = (self.dir / "log.jsonl").read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        rows = []
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("kind"), str):
                rows.append(row)
        return rows

    def meta(self) -> dict:
        """读 meta.json（标题、创建和更新时间）；没有或读不出来时返回 {}。"""
        try:
            data = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def set_meta(self, **fields: Any) -> None:
        """合并写入 meta.json。"""
        _write_json(self.dir / "meta.json", {**self.meta(), **fields})

    def log(self, kind: str, **data: Any) -> None:
        """往 log.jsonl 追加一行；自动加上 ts 和 kind。图片块只记"图片 <字节数> 字节"，不记内容。"""
        row = {"ts": _now().isoformat(timespec="milliseconds"), "kind": kind, **redact_images(data)}
        with (self.dir / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def part_dir(self, part_id: str = "main") -> Path:
        """零件状态放在哪个目录：单零件（main）就是会话目录本身；多零件时是 parts/<编号>（不存在就建）。"""
        if part_id == "main":
            return self.dir
        d = self.dir / "parts" / part_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_state(self, brief: Brief, features_list: list[dict], checks_raw: list[dict], notebook_text: str,
                   plan: list[dict] | None = None, product: dict | None = None,
                   part_notebooks: dict[str, str] | None = None) -> None:
        """product 是多零件时 product.workspace.product_state 的结果：各零件写进自己的目录，装配写 assembly.json。"""
        d = self.part_dir()
        _write_json(d / "brief.json", brief.to_dict())
        _write_json(d / "features.json", features_list)
        _write_json(d / "checks.json", checks_raw)
        (d / "model.py").write_text(notebook_text, encoding="utf-8")
        if plan is not None:
            _write_json(d / "plan.json", plan)
        if product is not None:
            for pid, st in product["parts"].items():
                pd = self.part_dir(pid)
                _write_json(pd / "features.json", st["features"])
                _write_json(pd / "checks.json", st["checks"])
                _write_json(pd / "connectors.json", st["connectors"])
                if st["plan"] is not None:
                    _write_json(pd / "plan.json", st["plan"])
                if part_notebooks and pid in part_notebooks:
                    (pd / "model.py").write_text(part_notebooks[pid], encoding="utf-8")
            _write_json(d / "assembly.json", {k: product[k] for k in ("active", "assembly", "assembly_passed")}
                        | {"done": [pid for pid, st in product["parts"].items() if st["done"]]})
            _write_json(d / "assembly_checks.json", product["assembly_checks"])

    def versions(self) -> list[Path]:
        root = self.part_dir() / "versions"
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
        stl_src: Path | None = None,
        extra_json: dict[str, Any] | None = None,
        stages_src: Path | None = None,
    ) -> Path:
        existing = self.versions()
        n = int(VERSION_RE.match(existing[-1].name).group(1)) + 1 if existing else 1  # type: ignore[union-attr]
        v = self.part_dir() / "versions" / f"v{n}"
        v.mkdir(parents=True)
        (v / "model.py").write_text(notebook_text, encoding="utf-8")
        shutil.copyfile(step_src, v / "model.step")
        shutil.copyfile(png_src, v / "view.png")
        if stl_src is not None:
            shutil.copyfile(stl_src, v / "model.stl")
        _write_json(v / "checks.json", [r.to_dict() for r in check_results])
        _write_json(v / "brief.json", brief.to_dict())
        lines = [f"# v{n} 变更说明", ""] + ([f"- {c}" for c in changes] if changes else ["- （需求单参数没有变化）"])
        (v / "changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for key, data in (extra_json or {}).items():  # 分阶段时：gate.json、plan.json
            _write_json(v / f"{key}.json", data)
        if stages_src is not None and Path(stages_src).is_dir():  # 各阶段的 STL，给界面的阶段回看用
            shutil.copytree(stages_src, v / "stages")
        return v
