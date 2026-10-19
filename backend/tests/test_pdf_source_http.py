"""Offline source/SDK separation and binding guards, never new compilation proof."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('source_launcher', ROOT / 'scripts/pdf_private_launcher.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


@pytest.fixture()
def source_pair():
    # Previously authenticated audit supplies schema only; cannot prove this phase.
    audit = json.loads((ROOT / 'docs/dependencies/pdf-unicode-bootstrap-evidence.json').read_text())
    inventory = {'origin': 'LOCAL_PINNED_VCPKG_SOURCE_BUILD', 'private_consumption_only': True,
                 'modified_build_is_distribution_candidate': False, 'source_archive': None,
                 'binary_cache': 'DISABLED', 'distribution_status': launcher.BLOCKED,
                 'native_audit_sha256': 'a' * 64, 'expected_pango_version_string': launcher.SOURCE_VERSION,
                 'preload_dlls': ['ffi-8.dll'], 'dlls': copy.deepcopy(audit['dlls']),
                 'source_packages': {n: {'patched_source_tree_sha256': p['tree_sha256'],
                                         'patched_source_files': p['source_entries']}
                                     for n, p in audit['preferred_source_trees'].items()}}
    return inventory, audit


def test_explicit_source_audit_validates_without_importing_native(source_pair):
    before = set(sys.modules)
    launcher.validate_source_inventory(*source_pair, 'a' * 64)
    assert not (set(sys.modules) - before) & {'cffi', 'ctypes', 'weasyprint', 'app', 'uvicorn'}


@pytest.mark.parametrize('key,value', [('origin', 'SDK'), ('private_consumption_only', False),
    ('modified_build_is_distribution_candidate', True), ('binary_cache', 'ENABLED'),
    ('source_archive', 'public-source-claim'), ('native_audit_sha256', 'b'*64),
    ('preload_dlls', ['libffi-8.dll']), ('expected_pango_version_string', '1.58.2')])
def test_source_inventory_rejects_wrong_role_origin_or_pin(source_pair, key, value):
    inv, audit = source_pair
    inv[key] = value
    with pytest.raises(ValueError):
        launcher.validate_source_inventory(inv, audit, 'a'*64)


@pytest.mark.parametrize('key,value', [('compiled_from_noticed_archive', False),
    ('inline_change_date_notice_present_in_compiled_source', False),
    ('input_source_trees_unchanged_during_compilation', False), ('native_compilation', 'NOT_RUN'),
    ('application_present', True), ('noticed_source_archive_sha256', '0'*64),
    ('noticed_source_file_sha256', '0'*64), ('changed_packages', []),
    ('actual_pango_version_string', '1.58.2')])
def test_source_audit_cannot_be_old_sdk_or_different_archive(source_pair, key, value):
    inv, audit = source_pair
    audit[key] = value
    with pytest.raises(ValueError):
        launcher.validate_source_inventory(inv, audit, 'a'*64)


@pytest.mark.parametrize('kind', ['dll-hash', 'dll-owner', 'dll-set', 'tree-hash', 'tree-count', 'receipt'])
def test_source_tree_dll_and_receipt_substitution_is_rejected(source_pair, kind):
    inv, audit = source_pair
    if kind == 'dll-hash':
        inv['dlls']['ffi-8.dll']['sha256'] = '0'*64
    if kind == 'dll-owner':
        inv['dlls']['ffi-8.dll']['source_package'] = 'pango'
    if kind == 'dll-set':
        inv['dlls'].pop('ffi-8.dll')
    if kind == 'tree-hash':
        inv['source_packages']['pango']['patched_source_tree_sha256'] = '0'*64
    if kind == 'tree-count':
        inv['source_packages']['pango']['patched_source_files'] = 1
    if kind == 'receipt':
        audit['noticed_source_kit_receipt']['modified_kit_manifest_sha256'] = '0'*64
    with pytest.raises(ValueError):
        launcher.validate_source_inventory(inv, audit, 'a'*64)


def test_stock_payload_never_auto_accepts_source_or_non_http(tmp_path):
    spec = importlib.util.spec_from_file_location('legacy_test', ROOT/'backend/tests/test_pdf_private_launcher.py')
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    root = legacy.payload.__wrapped__(tmp_path)
    with pytest.raises(ValueError, match='Source mode requires explicit'):
        launcher.validate_payload(root, *legacy.stamp(root), source_audit_digest='a'*64)
    inv = json.loads((root/'native/pdf/runtime-inventory.json').read_text())
    inv['origin'] = 'LOCAL_PINNED_VCPKG_SOURCE_BUILD'
    legacy.put(root/'native/pdf/runtime-inventory.json', inv)
    with pytest.raises(ValueError, match='stock SDK'):
        launcher.validate_payload(root, *legacy.stamp(root))


def test_cold_build_workflow_authenticates_archive_before_compile_and_binds_http():
    import yaml
    x = yaml.safe_load((ROOT/'.github/workflows/pdf-source-http.yml').read_text())
    job = x['jobs']['source-http-consumer']
    assert job['needs'] == 'stock-http-preflight'
    steps = job['steps']
    positions = {text: next(i for i, v in enumerate(steps) if text in v.get('name', '')) for text in (
        'Authenticate the exact prior', 'Compile all target', 'Verify twenty actual', 'Fresh no-site source HTTP', 'Bind this fresh', 'Reverify the exact source')}
    assert list(positions.values()) == sorted(positions.values())
    compile_step = next(v for v in steps if 'Compile all target' in v.get('name', ''))
    assert 'local-overlay' in compile_step['run']
    call = next(v['run'] for v in steps if 'Fresh no-site source HTTP' in v.get('name', ''))
    assert '-HttpProof -SourceAudit' in call and 'prepare_pdf_consumer_candidate.py' in call
    assert 'prepare_pdf_native_fixture' not in '\n'.join(v.get('run','') for v in steps)
    assert sum('Source HTTP evidence group' in v.get('name','') for v in steps) == 4
    for filename in ('pdf-private-http-evidence.json','pdf-unicode-bootstrap-evidence.json'):
        raw = (ROOT/'docs/dependencies'/filename).read_bytes()
        assert len(raw) > 30000 and hashlib.sha256(raw).digest()
