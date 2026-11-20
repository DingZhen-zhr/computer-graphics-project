"""从卡尺（第二版）升级到 Datum 时，把旧的数据目录复制过来（3.0 计划 1 Task 2，3.0 设计第 11 节）。

只有三个条件同时成立才复制：没有设置 DATUM_HOME；新目录不存在；旧目录存在。
只复制，从不删除旧目录：用户还可以接着用旧版卡尺，旧数据原样留着。
先复制到新目录旁边的临时目录（Datum.migrating），全部成功后再改名成 Datum；中途失败就删掉临时目录，
新目录不会留下半截，下次启动还能重试。文件逐字节复制，settings.toml 里提到旧名字的值（比如 CALIPER_API_KEY）原样保留。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from cad_agent import paths

TEMP_SUFFIX = ".migrating"


@dataclass(frozen=True)
class MigrationResult:
    done: bool          # 这次复制了
    reason: str         # 中文：复制了 / 新目录已存在 / 没有旧目录 / 设置了 DATUM_HOME / 复制失败（原因）


def _copy_file(src: str, dst: str) -> object:
    """复制一个文件（连同修改时间）；测试里会换掉它来模拟磁盘满、文件被占用。"""
    return shutil.copy2(src, dst)


def _remove_temp(temp: Path) -> None:
    """删掉复制用的临时目录；删不掉的文件留着，下次复制前会再删一次。"""
    if temp.exists():
        shutil.rmtree(temp, ignore_errors=True)


def _reason(e: OSError) -> str:
    """失败原因写成一句话。shutil.Error 里是 (源, 目标, 原因) 的列表：取第一个文件的名字和原因，不然原因会被一长串路径挤掉。"""
    detail = str(e)
    if isinstance(e, shutil.Error) and e.args and isinstance(e.args[0], list) and e.args[0]:
        first = e.args[0][0]
        if isinstance(first, tuple) and len(first) == 3:
            more = f"，另有 {len(e.args[0]) - 1} 个文件" if len(e.args[0]) > 1 else ""
            detail = f"{Path(str(first[0])).name}：{first[2]}{more}"
    text = " ".join(detail.split())[:160]
    return f"复制失败（{text or type(e).__name__}）"


def migrate_home() -> MigrationResult:
    """条件满足时把旧数据目录复制成新数据目录。不抛异常：失败时 done=False，原因写在 reason 里。"""
    if os.environ.get(paths.HOME_ENV, "").strip():
        return MigrationResult(False, f"设置了 {paths.HOME_ENV}")
    new = paths.app_home()
    try:
        if new.exists():
            return MigrationResult(False, "新目录已存在")
        old = paths.old_app_home()
        if not old.is_dir():
            return MigrationResult(False, "没有旧目录")
        temp = new.with_name(new.name + TEMP_SUFFIX)
        _remove_temp(temp)   # 上次复制到一半被打断留下的
        try:
            shutil.copytree(old, temp, copy_function=lambda s, d: _copy_file(s, d))
            temp.rename(new)
        except OSError as e:   # shutil.Error 也是 OSError
            _remove_temp(temp)
            return MigrationResult(False, _reason(e))
    except OSError as e:   # 查目录在不在时就出错（比如没有权限）
        return MigrationResult(False, _reason(e))
    return MigrationResult(True, "复制了")
