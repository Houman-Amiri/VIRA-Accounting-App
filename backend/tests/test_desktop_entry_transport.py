"""Lossless transport only: no native/app execution claim from this replay."""

from __future__ import annotations

import base64
import json
import runpy
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_full_source_inventory_transport_never_truncates(tmp_path, monkeypatch, capsys):
    # Conservative budget fixture: prior whole witness PLUS full source inventory.
    # This intentionally retains all license/copyright fields, not a projection.
    prior = json.loads(
        (ROOT / "docs/dependencies/pdf-bootstrap-source-http-evidence.json").read_bytes()
    )
    prior["inventory"] = json.loads(
        (ROOT / "docs/dependencies/pdf-runtime-win64-source-inventory.json").read_bytes()
    )
    raw = (json.dumps(prior, indent=2) + "\n").encode()
    path = tmp_path / "verified-desktop-source.json"
    path.write_bytes(raw)
    main = runpy.run_path(str(ROOT / "scripts/desktop_launcher_bind.py"))["main"]
    parts = {}
    for group in range(8):
        monkeypatch.setattr(
            sys, "argv", ["transport-only", "--reports", str(tmp_path), "--emit-group", str(group)]
        )
        main()
        lines = capsys.readouterr().out.splitlines()
        assert len(lines) <= 8  # below GitHub's per-step annotation cap
        for line in lines:
            prefix = "::notice title=Phase 2 real CMD evidence::"
            assert line.startswith(prefix)
            record = json.loads(line[len(prefix) :])
            assert record["part"] not in parts
            parts[record["part"]] = record
    assert 32 < len(parts) <= 64  # original 32-part budget demonstrably insufficient
    assert set(parts) == set(range(len(parts)))
    assert all(record["total"] == len(parts) for record in parts.values())
    encoded = "".join(parts[i]["data"] for i in range(len(parts)))
    assert zlib.decompress(base64.b64decode(encoded)) == raw
    assert path.read_bytes() == raw
