import json
import re

from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.session import Session


def make_brief(tilt: float = 65) -> Brief:
    return Brief(part_name="手机支架", params=[Param("tilt_deg", tilt, "deg", "user", "支撑角度")], confirmed=True)


def make_version(s: Session, tmp_path, changes, tilt=65):
    step, png = tmp_path / "in.step", tmp_path / "in.png"
    step.write_bytes(b"STEP-DATA")
    png.write_bytes(b"\x89PNG-DATA")
    results = [CheckResult("valid", "valid", True, None, None, None, "几何体有效")]
    return s.new_version(notebook_text="# model\n", brief=make_brief(tilt), check_results=results,
                         changes=changes, step_src=step, png_src=png)


def test_dir_created(tmp_path):
    s = Session(tmp_path / "sessions")
    assert s.dir.is_dir() and s.dir.parent == tmp_path / "sessions"
    assert re.fullmatch(r"\d{8}-\d{6}", s.dir.name)


def test_same_second_gets_suffix(tmp_path, monkeypatch):
    import datetime

    import cad_agent.session as session_module

    monkeypatch.setattr(session_module, "_now", lambda: datetime.datetime(2026, 11, 9, 12, 0, 0))
    names = [Session(tmp_path).dir.name for _ in range(3)]
    assert names == ["20261109-120000", "20261109-120000-2", "20261109-120000-3"]
    assert all((tmp_path / n).is_dir() for n in names)


def test_log_jsonl(tmp_path):
    s = Session(tmp_path)
    s.log("user", text="做一个支架")
    s.log("tool", name="build", result={"passed": False}, path=tmp_path)
    lines = (s.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert [r["kind"] for r in rows] == ["user", "tool"]
    assert all("ts" in r for r in rows)
    assert rows[0]["text"] == "做一个支架" and "做一个支架" in lines[0]  # 中文不转义
    assert rows[1]["result"] == {"passed": False} and rows[1]["path"] == str(tmp_path)


def test_save_state(tmp_path):
    s = Session(tmp_path)
    feats = [{"slug": "base", "role": "build", "code": "base = 1"}]
    checks = [{"id": "w", "type": "bbox", "axis": "x", "expected": 1}]
    s.save_state(make_brief(), feats, checks, "# notebook\n")
    assert json.loads((s.dir / "brief.json").read_text(encoding="utf-8")) == make_brief().to_dict()
    assert json.loads((s.dir / "features.json").read_text(encoding="utf-8")) == feats
    assert json.loads((s.dir / "checks.json").read_text(encoding="utf-8")) == checks
    assert (s.dir / "model.py").read_text(encoding="utf-8") == "# notebook\n"
    s.save_state(make_brief(70), feats, checks, "# changed\n")  # 再次保存会覆盖
    assert (s.dir / "model.py").read_text(encoding="utf-8") == "# changed\n"


def test_new_version_increments_and_copies(tmp_path):
    s = Session(tmp_path)
    v1 = make_version(s, tmp_path, ["tilt_deg: 新增 65 deg（用户给的）"])
    v2 = make_version(s, tmp_path, ["tilt_deg: 65 → 70 (deg)"], tilt=70)
    assert (v1.name, v2.name) == ("v1", "v2") and v1.parent == s.dir / "versions"
    for v in (v1, v2):
        assert sorted(p.name for p in v.iterdir()) == ["brief.json", "changes.md", "checks.json", "model.py", "model.step", "view.png"]
    assert "65 → 70" in (v2 / "changes.md").read_text(encoding="utf-8")
    assert (v2 / "model.step").read_bytes() == b"STEP-DATA" and (v2 / "view.png").read_bytes() == b"\x89PNG-DATA"
    assert json.loads((v2 / "checks.json").read_text(encoding="utf-8"))[0]["id"] == "valid"
    assert json.loads((v2 / "brief.json").read_text(encoding="utf-8"))["params"][0]["value"] == 70
    assert (v1 / "model.py").read_text(encoding="utf-8") == "# model\n"


def test_empty_changes_still_writes_changes_md(tmp_path):
    s = Session(tmp_path)
    v = make_version(s, tmp_path, [])
    assert (v / "changes.md").read_text(encoding="utf-8").strip() != ""


def test_versions_sorted(tmp_path):
    s = Session(tmp_path)
    assert s.versions() == []
    for name in ("v10", "v2", "v1"):
        (s.dir / "versions" / name).mkdir(parents=True)
    (s.dir / "versions" / "notes.txt").write_text("x", encoding="utf-8")  # 不是版本目录，要忽略
    assert [p.name for p in s.versions()] == ["v1", "v2", "v10"]


def test_next_version_follows_highest_number(tmp_path):
    s = Session(tmp_path)
    (s.dir / "versions" / "v10").mkdir(parents=True)
    assert make_version(s, tmp_path, []).name == "v11"
