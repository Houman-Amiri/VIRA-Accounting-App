"""Workflow trust/order contracts; actual noticed archive build/PDF is separate Windows evidence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_noticed_archive_is_produced_before_native_build_and_never_edited_after_extract():
    s = (ROOT / '.github/workflows/pdf-noticed-archive-consumer.yml').read_text()
    assert '--inline-notice' in s and '--change-date 2026-10-19' in s
    assert 'needs: source-assembly' in s
    assert 'needs.source-assembly.outputs.manifest_sha256' in s
    assert 'needs.source-assembly.outputs.archive_sha256' in s
    windows = s[s.index('  noticed-consumer:'):]
    assert 'old.replace(' not in windows and 'p.write_bytes(' not in windows
    assert windows.index('--extract-sources') < windows.index('Compile all target libraries')
    assert windows.index('Compile all target libraries') < windows.index('Prepare locked application')
    assert windows.index('Prepare locked application') < windows.index('Real PDF and modified Pango')
    assert 'x[\'preferred_source_trees\']==rec[\'archive_source_trees\']' in windows
    assert 'compiled_from_noticed_archive=True' in windows
    assert 'inline_change_date_notice_present_in_compiled_source=True' in windows
    assert 'Reverify the exact source envelope after native compilation and rendering' in windows
    assert 'private-noticed-archive-build-pdf-evidence-no-dlls' in windows
    assert 'include-hidden-files: true' in s


def test_packaging_does_not_claim_future_build_or_legal_approval():
    s = (ROOT / 'scripts/pdf_source_kit.py').read_text()
    assert 'prior_build_witness_applies_to_archive_sources=False' in s
    assert '"new_native_build_from_this_envelope_proven": False' in s
    assert '"legal_notice_completeness_approved": False' in s
