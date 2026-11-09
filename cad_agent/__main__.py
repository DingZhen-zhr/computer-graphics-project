"""python -m cad_agent [--config config.toml]"""

import sys

from cad_agent.cli import main

if __name__ == "__main__":
    # 输出里有中文和特殊符号；控制台不认的字符用 ? 代替，不要让程序崩溃
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    raise SystemExit(main())
