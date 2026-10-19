"""Synthetic binding tests: combining old schemas here is NOT new source evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def binder(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('source_bind', ROOT / 'scripts/pdf_source_http_bind.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def synthetic_binding(tmp_path):
    old_source = json.loads((ROOT / 'docs/dependencies/pdf-unicode-bootstrap-evidence.json').read_text())
    old_http = json.loads((ROOT / 'docs/dependencies/pdf-private-http-evidence.json').read_text())
    audit_path = tmp_path / 'synthetic-audit.json'
    audit_path.write_text(json.dumps(old_source))
    digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    inventory = {'origin': 'LOCAL_PINNED_VCPKG_SOURCE_BUILD', 'private_consumption_only': True,
                 'modified_build_is_distribution_candidate': False, 'source_archive': None,
                 'binary_cache': 'DISABLED', 'distribution_status': old_source['distribution_status'],
                 'native_audit_sha256': digest, 'expected_pango_version_string': '1.58.0-vira-local-source',
                 'preload_dlls': ['ffi-8.dll'], 'dlls': copy.deepcopy(old_source['dlls']),
                 'source_packages': {n: {'patched_source_tree_sha256': p['tree_sha256'],
                                         'patched_source_files': p['source_entries']}
                                     for n, p in old_source['preferred_source_trees'].items()}}
    for name, values in old_http['cases'].items():
        folder = tmp_path / name
        folder.mkdir()
        p, c = values['launcher'], values['http_pdf']
        p.update(role='PRIVATE_NOTICED_SOURCE_HTTP_LAUNCHER_NOT_DISTRIBUTION', source_audit_sha256=digest, source_audit_bound=True)
        w = c['worker']
        w.update(source_audit_sha256=digest, source_audit_bound=True, pango_version='1.58.0-vira-local-source', loaded_dlls=copy.deepcopy(old_source['dlls']))
        c['dll_count'] = 21
        for filename, data in [('launcher-proof.json', p), ('http-bundled-proof.json', c), ('runtime-inventory.json', inventory)]:
            (folder / filename).write_text(json.dumps(data))
    (tmp_path / 'negative-controls.json').write_text(json.dumps(old_http['negative_controls']))
    return audit_path, tmp_path


def test_synthetic_complete_binding_shape_only(monkeypatch, synthetic_binding):
    x = binder(monkeypatch).bind(*synthetic_binding)
    assert x['source21_http_pair_proven'] and x['new_source_build_proven']
    assert x['stock_sdk_used_in_source_job'] is False and x['release_authorized'] is False
    assert len(x['source_http_cases']) == 2
    assert 'distinct bundled libffi-8.dll' in x['cpython_ctypes_ffi_note']


@pytest.mark.parametrize('kind', ['digest', 'version', 'pid', 'restart', 'database', 'pages', 'negative'])
def test_binding_rejects_mismatched_halves(monkeypatch, synthetic_binding, kind):
    audit_path, reports = synthetic_binding
    name = 'restarted-process' if kind == 'database' else 'first-process'
    folder = reports / name
    filename = 'launcher-proof.json' if kind in ('digest', 'pid') else 'http-bundled-proof.json'
    file = folder / filename
    x = json.loads(file.read_text())
    if kind == 'digest':
        x['source_audit_sha256'] = '0'*64
    if kind == 'pid':
        x['pid'] = -1
    if kind == 'version':
        x['worker']['pango_version'] = '1.58.2'
    if kind == 'restart':
        x['worker']['reused_state'] = True
    if kind == 'database':
        x['worker']['database'] = 'unrelated.sqlite3'
    if kind == 'pages':
        x['documents']['single-page']['pages'] = 4
    file.write_text(json.dumps(x))
    if kind == 'negative':
        (reports / 'negative-controls.json').write_text('{}')
    with pytest.raises(ValueError):
        binder(monkeypatch).bind(audit_path, reports)


def test_full_upstream_inventory_is_projected_without_losing_audit_bindings(monkeypatch, synthetic_binding):
    import base64
    import zlib
    module = binder(monkeypatch)
    audit_path, reports = synthetic_binding
    full = json.loads((ROOT / 'docs/dependencies/pdf-runtime-win64-source-inventory.json').read_text())
    for name in ('first-process', 'restarted-process'):
        file = reports / name / 'runtime-inventory.json'
        inv = json.loads(file.read_text())
        # Use full upstream receipt/copyright volume; preserve synthetic audit pins.
        for pkg, entry in inv['source_packages'].items():
            inv['source_packages'][pkg] = {**full['source_packages'][pkg], **entry}
        file.write_text(json.dumps(inv))
    result = module.bind(audit_path, reports)
    assert result['inventory_representation'].startswith('VALIDATED_BINDING_PROJECTION')
    for case in result['source_http_cases'].values():
        inv = case['inventory']
        assert all(set(v) == {'sha256', 'source_package'} for v in inv['dlls'].values())
        assert all(set(v) == {'patched_source_tree_sha256', 'patched_source_files'} for v in inv['source_packages'].values())
    encoded = base64.b64encode(zlib.compress((json.dumps(result, indent=2)+'\n').encode()))
    assert len(encoded) <= 32 * 3000  # existing four groups, no truncation or cap weakening
