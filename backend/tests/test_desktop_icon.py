"""The desktop icon is the owner's own mark, not a generic .cmd glyph.

The shortcut used to point at ``start_noa.cmd`` with no ``IconFilename``, so
Windows drew its stock batch-file icon on the desktop, in the Start menu and in
Programs and Features. The mark now ships inside the payload as
``static/noa.ico`` — an allowed install root, so a later delta can refresh it
without adding a file at the installation root (which an older client would
reject).
"""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISS = ROOT / "installer" / "noa.iss"
ICON = ROOT / "installer" / "assets" / "noa.ico"
PUBLIC_ICON = ROOT / "frontend" / "public" / "noa.ico"


def _ico_sizes(path: Path) -> set[int]:
    """Widths recorded in the ICO directory (0 means 256 px)."""
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert reserved == 0 and kind == 1, "not an .ico file"
    sizes = set()
    for index in range(count):
        offset = 6 + index * 16
        width = data[offset] or 256
        sizes.add(width)
    return sizes


def test_the_setup_wizard_and_programs_list_use_the_mark() -> None:
    iss = ISS.read_text(encoding="utf-8")
    assert r"SetupIconFile=assets\noa.ico" in iss
    # public installer points Programs and Features at the mark; the isolated
    # private fixtures stage no static/ folder and keep the launcher's icon
    assert "UninstallDisplayIcon={app}\\static\\noa.ico" in iss
    assert "#ifdef PrivateSourceCI\n; The isolated private fixtures stage no static/ folder." in iss


def test_every_shortcut_carries_the_mark() -> None:
    iss = ISS.read_text(encoding="utf-8")
    icons_section = iss.split("[Icons]", 1)[1].split("[Registry]", 1)[0]
    public_lines = [
        line
        for line in icons_section.splitlines()
        if line.startswith("Name: ") and "private_installed_source.py" not in line
    ]
    # Start menu, desktop and startup — the shortcuts a normal install creates
    assert len(public_lines) == 3
    assert all(r'IconFilename: "{app}\static\noa.ico"' in line for line in public_lines)
    assert any("desktopicon" in line for line in public_lines)


def test_the_icon_ships_inside_the_payload_not_at_the_installation_root() -> None:
    """``static/`` is an install root; a new root file would break upgrades."""
    from app.services.update_staging import INSTALL_FILES, INSTALL_ROOTS

    assert "noa.ico" not in INSTALL_FILES
    assert "static" in INSTALL_ROOTS
    # the SPA build copies public/ into dist/, and dist/ becomes static/
    assert PUBLIC_ICON.is_file()
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'href="/noa.ico"' in index_html


def test_the_icon_file_holds_the_sizes_windows_asks_for() -> None:
    sizes = _ico_sizes(ICON)
    # 16 px taskbar, 32 px desktop small, 48/64 shell, 256 px large tiles
    assert {16, 32, 48, 256}.issubset(sizes)
    assert max(sizes) == 256


def test_the_icon_is_the_owner_logo_not_a_placeholder() -> None:
    """Both files must be the same artwork: the .ico is derived from the logo."""
    assert ICON.is_file() and PUBLIC_ICON.is_file()
    assert ICON.stat().st_size == PUBLIC_ICON.stat().st_size
    assert ICON.read_bytes() == PUBLIC_ICON.read_bytes()
    # the master logo is what the invoices print, and it is not a blank square
    logo = ROOT / "backend" / "app" / "assets" / "branding" / "noa-logo.png"
    assert logo.stat().st_size > 10_000
