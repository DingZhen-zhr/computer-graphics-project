"""从二进制 STL 算外形尺寸和体积，给版本列表用（版本目录里没有单独存这两个数）。

只读文件，不用 SCA；按（路径、修改时间、大小）缓存，同一个文件只算一次。文件不是合法的二进制 STL 时返回 (None, None)。
"""

from __future__ import annotations

import struct
import threading
from pathlib import Path

_HEADER = 80
_TRI = struct.Struct("<12fH")
_cache: dict[tuple[str, int, int], tuple[list[float] | None, float | None]] = {}
_lock = threading.Lock()


def _compute(data: bytes) -> tuple[list[float] | None, float | None]:
    if len(data) < _HEADER + 4:
        return None, None
    (n,) = struct.unpack_from("<I", data, _HEADER)
    if n == 0 or len(data) != _HEADER + 4 + n * _TRI.size:
        return None, None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    volume = 0.0
    for t in _TRI.iter_unpack(memoryview(data)[_HEADER + 4:]):
        a, b, c = t[3:6], t[6:9], t[9:12]
        for p in (a, b, c):
            for i in range(3):
                if p[i] < lo[i]:
                    lo[i] = p[i]
                if p[i] > hi[i]:
                    hi[i] = p[i]
        # 有向四面体体积之和（三角形和原点组成的四面体）
        volume += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    size = [round(hi[i] - lo[i], 3) for i in range(3)]
    return size, round(abs(volume), 3)


def stl_facts(path: Path) -> tuple[list[float] | None, float | None]:
    """(外形尺寸 [x, y, z], 体积)；文件不存在或格式不对时是 (None, None)。"""
    path = Path(path)
    try:
        st = path.stat()
    except OSError:
        return None, None
    key = (str(path), st.st_mtime_ns, st.st_size)
    with _lock:
        if key in _cache:
            return _cache[key]
    try:
        facts = _compute(path.read_bytes())
    except OSError:
        return None, None
    with _lock:
        _cache[key] = facts
    return facts
