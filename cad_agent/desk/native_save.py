"""桌面窗口（pywebview）里的原生保存，绕开 macOS WKDownloadDelegate 的上游缺陷。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from cad_agent.desk.hub import Hub
from cad_agent.desk.routes import version_file


class DesktopApi:
    """暴露给 pywebview 页面的本机能力：通过系统“存储为”对话框复制白名单版本文件。"""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub
        self.window: Any = None

    def save_file(self, sid: str, version: str, rel: str, filename: str) -> dict:
        try:
            src = version_file(self._hub, sid, [version, *rel.split("/")])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": getattr(e, "message", str(e)) or "没有这个文件"}
        if self.window is None:
            return {"ok": False, "error": "窗口没有准备好"}
        import webview

        downloads = Path.home() / "Downloads"
        save_type = getattr(getattr(webview, "FileDialog", None), "SAVE", getattr(webview, "SAVE_DIALOG", 30))
        chosen = self.window.create_file_dialog(
            save_type, directory=str(downloads) if downloads.is_dir() else "", save_filename=Path(filename).name
        )
        if not chosen:
            return {"ok": False, "cancelled": True}
        dest = Path(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)
        try:
            shutil.copyfile(src, dest)
        except OSError as e:
            return {"ok": False, "error": f"保存失败：{e.strerror or type(e).__name__}"}
        return {"ok": True, "name": dest.name}
