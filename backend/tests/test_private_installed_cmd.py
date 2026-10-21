"""CMD quoting check; opaque batch only, NOT Source21/native/installer acceptance."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.private_installed_source import real_cmd_command


def test_installed_bridge_uses_proven_raw_cmd_quoting(tmp_path):
    root = tmp_path / "VIRA فارسی ! & path"
    root.mkdir()
    request = tmp_path / "درخواست ! & path.json"
    request.write_bytes(b"{}")
    (root / "start_vira.cmd").write_bytes(
        b"@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
        b'if /i not "%~1"=="--private-source-candidate" exit /b 91\r\n'
        b'if not exist "%~2" exit /b 92\r\nexit /b 0\r\n'
    )
    comspec = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    command = real_cmd_command(root, request, comspec)
    assert (
        command
        == f'"{comspec}" /d /s /c ""{root / "start_vira.cmd"}" --private-source-candidate "{request}""'
    )
    if os.name == "nt":
        # Real Windows CMD, but no Python subprocess or native PDF is executed.
        subprocess.run(command, cwd=root, check=True, timeout=15)
    else:
        assert Path(request).is_file()  # No simulated Windows execution claim.
