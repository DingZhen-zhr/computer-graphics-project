"""名字集中在 cad_agent/brand.py（3.0 计划 1 Task 1）。只读文件，不动任何东西。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import cad_agent
from cad_agent import brand

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "cad_agent"
OLD_NAME = re.compile(r"caliper|卡尺", re.IGNORECASE)
SUFFIXES = {".py", ".js", ".css", ".html", ".toml"}
# brand.py 里只允许这三行带旧名字（迁移要用）
OLD_CONSTANTS = re.compile(r'^(OLD_HOME_DIR|OLD_KEYRING_SERVICE|OLD_DIST) = "[^"]*"$')


def test_brand_values():
    assert brand.PRODUCT == "Datum"
    assert brand.PRODUCT_ZH == "基准"
    assert brand.DISPLAY == "Datum 基准"
    assert brand.COMMAND == "datum"
    assert brand.GUI_COMMAND == "datum-app"
    assert brand.DIST == "datum-cad"
    assert brand.VERSION == "3.0.0"
    assert brand.HOME_DIR == "Datum"
    assert brand.HOME_ENV == "DATUM_HOME"
    assert brand.ENV_PREFIX == "DATUM_"
    assert brand.KEYRING_SERVICE == "datum"
    assert brand.DOCTOR_SERVICE == "datum-doctor"
    assert brand.TOKEN_HEADER == "X-Datum-Token"
    assert brand.OLD_HOME_DIR == "Caliper"
    assert brand.OLD_KEYRING_SERVICE == "caliper"
    assert brand.OLD_DIST == "caliper-cad"


def test_version_matches_pyproject():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert cad_agent.__version__ == brand.VERSION == data["project"]["version"]


def _own_files() -> list[Path]:
    """cad_agent 下面要查的文件；static/vendor/ 下是第三方文件，跳过。"""
    found = []
    for path in sorted(PKG.rglob("*")):
        rel = path.relative_to(PKG).as_posix()
        if path.is_file() and path.suffix in SUFFIXES and "__pycache__" not in rel and "static/vendor/" not in rel:
            found.append(path)
    return found


def test_no_old_name_outside_migration():
    files = _own_files()
    assert PKG / "brand.py" in files and len(files) > 20
    bad = []
    for path in files:
        rel = path.relative_to(PKG).as_posix()
        if rel == "migrate.py":
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not OLD_NAME.search(line):
                continue
            if rel == "brand.py" and OLD_CONSTANTS.match(line.strip()):
                continue
            bad.append(f"{rel}:{no}: {line.strip()[:80]}")
    assert not bad, "\n".join(bad)
