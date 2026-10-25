"""Synthetic PE-parser and audit consistency tests, NEVER native execution proof."""

from __future__ import annotations

import copy
import json
import runpy
import struct
from pathlib import Path

import pefile
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/phase3_native_codegen.py"))
AUDIT = json.loads(
    (ROOT / "docs/dependencies/phase3-installed-source21-evidence.json").read_bytes()
)["native_audit"]
NINJA = [
    (
        "vcpkg/buildtrees/pango/x64-vira-pdf-rel/build.ninja",
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG\n",
    )
]


def synthetic_pe(text=0x90, timestamp=1):
    # Parser-only container: no imports/exports or runnable Windows application.
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, timestamp, 0, 0, 240, 0x2022)
    opt = 0x98
    struct.pack_into("<H", data, opt, 0x20B)
    struct.pack_into("<II", data, opt + 32, 4096, 512)
    struct.pack_into("<II", data, opt + 56, 8192, 512)
    section = opt + 240
    data[section : section + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", data, section + 8, 512, 4096, 512, 512)
    struct.pack_into("<I", data, section + 36, 0x60000020)
    data[512:] = bytes([text]) * 512
    return bytes(data)


def test_codegen_parser_requires_actual_text_difference_not_header_timestamp():
    with pytest.raises(ValueError, match="timestamps/metadata"):
        MODULE["codegen_evidence"](synthetic_pe(timestamp=1), synthetic_pe(timestamp=2), NINJA)
    result = MODULE["codegen_evidence"](synthetic_pe(0x90), synthetic_pe(0xCC), NINJA)
    assert result["native_executable_text_changed"]
    assert result["before_text_sha256"] != result["after_text_sha256"]
    assert result["phase3_complete"] is False and result["release_authorized"] is False


@pytest.mark.parametrize(
    "instructions",
    [
        [],
        [("recipe", b"/Od /Ob0 /DNDEBUG")],
        [("build.ninja", b"pango-utils.c /O2")],
        [("build.ninja", b"pango-utils.c /Od /Ob0")],
    ],
)
def test_missing_actual_selected_compiler_instructions_rejected(instructions):
    with pytest.raises(ValueError, match="compiler instructions"):
        MODULE["codegen_evidence"](synthetic_pe(0x90), synthetic_pe(0xCC), instructions)


def test_opaque_bytes_never_qualify_as_native_target():
    with pytest.raises(pefile.PEFormatError):
        MODULE["codegen_evidence"](b"OPAQUE NOT A DLL", b"OTHER OPAQUE BYTES", NINJA)


def test_independent_audit_enrichment_preserves_preferred_source_receipts_without_mutation():
    old, fresh = copy.deepcopy(AUDIT), copy.deepcopy(AUDIT)
    fresh["dlls"]["pango-1.0-0.dll"]["sha256"] = "a" * 64
    merged = MODULE["merge_audits"](old, fresh)
    assert merged["dlls"] == fresh["dlls"]
    assert old == AUDIT
    assert merged["noticed_source_kit_receipt"] == AUDIT["noticed_source_kit_receipt"]


@pytest.mark.parametrize(
    "kind",
    ["failed", "app-present", "sources", "dll-owner", "dll-count", "missing-dll", "legal-gate"],
)
def test_independent_target_cannot_relax_source_closure_or_legal_gate(kind):
    fresh = copy.deepcopy(AUDIT)
    if kind == "failed":
        fresh["native_compilation"] = "FAILED"
    elif kind == "app-present":
        fresh["application_present"] = True
    elif kind == "sources":
        fresh["preferred_source_trees"]["pango"]["tree_sha256"] = "b" * 64
    elif kind == "dll-owner":
        fresh["dlls"]["pango-1.0-0.dll"]["source_package"] = "foreign"
    elif kind == "dll-count":
        fresh["dll_count"] = 27
    elif kind == "missing-dll":
        del fresh["dlls"]["pango-1.0-0.dll"]
    else:
        fresh["distribution_status"] = "CLEARED"
    with pytest.raises(ValueError):
        MODULE["merge_audits"](AUDIT, fresh)


@pytest.mark.parametrize(
    "args",
    [
        '"-O2" "-Oi" "-Gy" "-Z7" "-Od" "-Ob0" "-DNDEBUG"',
        "/O2 /Ob2 /Od /Ob0 /DNDEBUG",
        '/Od "-Ob0" /DNDEBUG',
    ],
)
def test_real_meson_dash_msvc_options_are_bound_to_effective_translation_unit(args):
    ninja = [
        (
            NINJA[0][0],
            (
                "build pango/pango-1.0-0.dll.p/pango-utils.c.obj: c_COMPILER ../src/pango/pango-utils.c || pango/types.h\n ARGS = "
                + args
                + "\n"
            ).encode(),
        )
    ]
    proof = MODULE["codegen_evidence"](synthetic_pe(0x90), synthetic_pe(0xCC), ninja)
    command = proof["compiler_instruction_files"][0]
    assert command["translation_unit"] == "pango-utils.c"
    assert command["effective_msvc_options"] == ["/Od", "/Ob0", "/DNDEBUG"]
    assert command["actual_args_sha256"]


@pytest.mark.parametrize(
    "instructions",
    [
        b"# pango-utils.c /Od /Ob0 /DNDEBUG\n",
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /O2 /Ob2 /DNDEBUG\n# /Od /Ob0 /DNDEBUG\n",
        b"build other.c.obj: c_COMPILER other.c\n ARGS = /Od /Ob0 /DNDEBUG\nbuild pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /O2 /DNDEBUG\n",
        b"build pango-utils.c.obj: CUSTOM_COMMAND pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG\n",
        b'build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = "-Dfake=/Od /Ob0 /DNDEBUG"\n',
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG /O2\n",
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG -Ob2\n",
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG -UNDEBUG\n",
        b"build pango-utils.c.obj: c_COMPILER pango-utils.c\n ARGS = /Od /Ob0 /DNDEBUG\n ARGS = /Od /Ob0 /DNDEBUG\n",
    ],
)
def test_recipe_markers_unrelated_rules_quoted_defines_and_later_overrides_are_rejected(
    instructions,
):
    with pytest.raises(ValueError, match="compiler instructions"):
        MODULE["codegen_evidence"](
            synthetic_pe(0x90), synthetic_pe(0xCC), [(NINJA[0][0], instructions)]
        )


def test_authenticated_actual_failed_producer_command_passes_only_corrected_effective_flags():
    import hashlib

    recorded = json.loads(
        (ROOT / "docs/dependencies/phase3-codegen-failed-native-diagnostics.json").read_bytes()
    )
    block = recorded["compile_block"].encode()
    assert hashlib.sha256(block).hexdigest() == recorded["excerpt_sha256"]
    assert recorded["full_codegen_target_admission"] is False
    assert recorded["source_run"] == 40183092030
    proof = MODULE["codegen_evidence"](
        synthetic_pe(0x90), synthetic_pe(0xCC), [(recorded["source_ninja_member"], block)]
    )
    assert proof["compiler_instruction_files"][0]["effective_msvc_options"] == [
        "/Od",
        "/Ob0",
        "/DNDEBUG",
    ]
    # The real producer's complete C_COMPILER block is preserved, not a synthetic
    # flags marker. PE containers here remain parser-only and NEVER native proof.
    changed = block.replace(b'"-Od"', b'"-Od" "-O2"')
    with pytest.raises(ValueError, match="compiler instructions"):
        MODULE["codegen_evidence"](
            synthetic_pe(0x90), synthetic_pe(0xCC), [(recorded["source_ninja_member"], changed)]
        )
