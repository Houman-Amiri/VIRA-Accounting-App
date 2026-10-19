"""Synthetic activation/cleanup/binding controls; NOT native or Windows evidence."""
import ctypes
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import private_pdf_bootstrap as boot

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fn:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args):
        return self.fn(*args)


@pytest.fixture()
def simulated(tmp_path, monkeypatch):
    root = tmp_path/'FAKE برنامه با فاصله'
    root.mkdir()
    plan = boot.PrivateBootstrapPlan(root, tmp_path/'FAKE bootstrap state', 'a'*64, 'b'*64)
    verified = boot.VerifiedPrivatePlan(plan, (('libffi-8.dll', 'c'*64),),
                                       root/'native/pdf/bin/libffi-8.dll', plan.state_root/'cache', 55)
    calls = []
    monkeypatch.setattr(boot, 'prepare_private_plan', lambda p: calls.append('prepare') or verified)
    monkeypatch.setattr(boot, 'verify_private_plan', lambda p: calls.append('reverify') or verified)
    handle = SimpleNamespace(close=lambda: calls.append('close'))
    monkeypatch.setattr(os, 'add_dll_directory', lambda p: calls.append(('directory', p)) or handle, raising=False)
    def load(path, flags):
        assert calls[:2] == ['prepare', 'reverify']
        assert path == str(verified.preload) and flags == 0x1000
        calls.append('pin')
        return object()
    monkeypatch.setitem(sys.modules, 'cffi', SimpleNamespace(FFI=lambda: SimpleNamespace(dlopen=load)))
    kernel = SimpleNamespace(GetACP=Fn(lambda: 65001), GetModuleHandleW=Fn(lambda name: name))
    def filename(name, buffer, length):
        buffer.value = str(root/'native/pdf/bin'/name)
        return len(buffer.value)
    kernel.GetModuleFileNameW = Fn(filename)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: kernel, raising=False)
    return plan, calls, kernel, handle


def process_state():
    return dict(os.environ), sys.path[:], tempfile.tempdir


def test_native_scope_pins_before_body_and_restores_plain_diagnostics(simulated):
    plan, calls, _, _ = simulated
    before = process_state()
    with boot.activate_private_sdk(plan) as active:
        assert calls[:2] == ['prepare', 'reverify'] and calls[-1] == 'pin'
        assert Path(tempfile.gettempdir()).is_relative_to(plan.state_root)
        assert Path(active.bootstrap_temp).is_dir()
        assert sys.path[:2] == [str(plan.payload_root/'site-packages'), str(plan.payload_root)]
        assert active.windows_acp == 65001
        json.dumps(asdict(active))  # plain data only, no C object or loader handle
    assert calls[-1] == 'close' and process_state() == before
    assert not plan.state_root.exists() and not Path(active.bootstrap_temp).exists()


@pytest.mark.parametrize('fault', ['body', 'interrupt', 'acp', 'foreign-module', 'missing-module', 'leak', 'close'])
def test_failure_and_interrupt_restore_scope_without_success(simulated, fault):
    plan, calls, kernel, handle = simulated
    before = process_state()
    if fault == 'acp':
        kernel.GetACP.fn = lambda: 1252
    elif fault == 'missing-module':
        kernel.GetModuleHandleW.fn = lambda _: None
    elif fault == 'foreign-module':
        def foreign(name, buffer, length):
            buffer.value = str(plan.payload_root/'foreign.dll')
            return len(buffer.value)
        kernel.GetModuleFileNameW.fn = foreign
    elif fault == 'close':
        def failed_close():
            calls.append('close')
            raise RuntimeError('synthetic close failure')
        handle.close = failed_close
    expected = KeyboardInterrupt if fault == 'interrupt' else (RuntimeError, ValueError)
    with pytest.raises(expected), boot.activate_private_sdk(plan) as active:
        if fault == 'body':
            raise RuntimeError('synthetic body failure')
        if fault == 'interrupt':
            raise KeyboardInterrupt()
        if fault == 'leak':
            (Path(active.bootstrap_temp)/'fake-leak').write_bytes(b'FAKE')
    assert calls[-1] == 'close' and process_state() == before and not plan.state_root.exists()


def test_reverification_failure_never_loads_native(simulated, monkeypatch):
    plan, calls, _, _ = simulated
    before = process_state()
    def fail(_):
        raise ValueError('snapshot changed')
    monkeypatch.setattr(boot, 'verify_private_plan', fail)
    with pytest.raises(ValueError, match='snapshot changed'), boot.activate_private_sdk(plan):
        raise AssertionError('must not enter body')
    assert calls == ['prepare'] and process_state() == before and not plan.state_root.exists()


def test_cached_verified_snapshot_is_not_activation_input(tmp_path):
    plan = boot.PrivateBootstrapPlan(tmp_path/'app', tmp_path/'state', 'a'*64, 'b'*64)
    cached = boot.VerifiedPrivatePlan(plan, (), tmp_path/'fake.dll', tmp_path/'cache', 0)
    with pytest.raises(TypeError), boot.activate_private_sdk(cached):
        raise AssertionError('cached data cannot bypass verification')


def test_private_entry_authenticates_app_code_before_execution(tmp_path):
    root = tmp_path/'payload'
    (root/'scripts').mkdir(parents=True)
    (root/'app').mkdir()
    entry = root/'scripts/pdf_bootstrap_http_entry.py'
    entry.write_bytes((ROOT/'scripts/pdf_bootstrap_http_entry.py').read_bytes())
    marker = tmp_path/'must-not-execute'
    module = root/'app/private_pdf_bootstrap.py'
    module.write_bytes(b'original-not-executed')
    manifest = {'files': [{'path': 'app/private_pdf_bootstrap.py', 'sha256': hashlib.sha256(module.read_bytes()).hexdigest(), 'size': module.stat().st_size}]}
    raw = json.dumps(manifest).encode()
    (root/'install_manifest.json').write_bytes(raw)
    module.write_text(f'from pathlib import Path;Path({str(marker)!r}).touch()')
    args = [sys.executable, '-I', '-S', '-B', '-X', 'utf8', str(entry), '--app-root', str(root),
            '--payload-manifest-sha256', hashlib.sha256(raw).hexdigest(), '--inventory-sha256', 'b'*64]
    for key in ('state-root', 'bootstrap-state-root', 'contexts', 'out-dir'):
        args += ['--'+key, str(tmp_path/key)]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0 and 'code differs before execution' in result.stderr
    assert not marker.exists()


@pytest.fixture()
def synthetic_bound(tmp_path):
    # Historical witness adapted ONLY for a synthetic binder contract test.
    original = json.loads((ROOT/'docs/dependencies/pdf-app-owned-sdk-http-evidence.json').read_text())
    for name, case in original['cases'].items():
        p = case['launcher']
        p.update(role='PRIVATE_APP_BOOTSTRAP_SDK_HTTP_NOT_INSTALLED', target_mode='PRIVATE_APP_BOOTSTRAP_HTTP',
                 preflight_and_activation_module='app/private_pdf_bootstrap.py', activation_scope_restored=True,
                 bootstrap_temp_cleaned=True)
        p['activation'] = {'pid': p['pid'], 'windows_acp': 65001, 'dll_count': 27,
                           'manifest_sha256': p['payload_manifest_sha256'], 'inventory_sha256': p['inventory_sha256'],
                           'libffi': p['libffi'], 'payload_files': 1234, 'bootstrap_temp': f'FAKE/{name}',
                           'role': 'APP_OWNED_PRIVATE_SDK_ACTIVATION_NOT_INSTALLED'}
        folder = tmp_path/name
        folder.mkdir()
        for filename, value in [('launcher-proof.json', p), ('http-bundled-proof.json', case['http_pdf'])]:
            (folder/filename).write_text(json.dumps(value))
    negatives = original['negative_controls']
    negatives['unmanifested-code'] = {'rejected': True, 'exit_code': 1}
    (tmp_path/'negative-controls.json').write_text(json.dumps(negatives))
    return tmp_path


def test_synthetic_distinct_bootstrap_binding(synthetic_bound):
    result = script('pdf_bootstrap_sdk_bind').bind(synthetic_bound)
    assert result['role'] == 'APP_OWNED_SDK_BOOTSTRAP_AND_HTTP_NOT_SOURCE_OR_INSTALLED'
    assert result['source21_activation_proven'] is False


@pytest.mark.parametrize('fault', ['old-role', 'no-restore', 'pid', 'acp', 'manifest', 'source', 'qa', 'cleanup'])
def test_synthetic_missing_binding_is_rejected(synthetic_bound, fault):
    file = synthetic_bound/'first-process/launcher-proof.json'
    p = json.loads(file.read_text())
    if fault == 'old-role':
        p['role'] = 'PRIVATE_APP_OWNED_HTTP'
    elif fault == 'no-restore':
        p['activation_scope_restored'] = False
    elif fault in ('pid', 'acp', 'manifest'):
        key = {'pid': 'pid', 'acp': 'windows_acp', 'manifest': 'manifest_sha256'}[fault]
        p['activation'][key] = 0
    elif fault == 'source':
        p['source_audit_bound'] = True
    elif fault == 'qa':
        wfile = synthetic_bound/'first-process/http-bundled-proof.json'
        w = json.loads(wfile.read_text())
        w['worker']['app_owned_dispatch']['qa_renderer_replacement_used'] = True
        wfile.write_text(json.dumps(w))
    else:
        p['bootstrap_temp_cleaned'] = False
    file.write_text(json.dumps(p))
    with pytest.raises(ValueError):
        script('pdf_bootstrap_sdk_bind').bind(synthetic_bound)


def test_recorded_native_bootstrap_witness_matches_authenticated_digest(tmp_path):
    """Recorded-proof integrity check, not a fresh native run inside pytest."""
    raw = (ROOT/'docs/dependencies/pdf-bootstrap-sdk-http-evidence.json').read_bytes()
    proof = json.loads((ROOT/'docs/dependencies/pdf-bootstrap-sdk-http-proof.json').read_text())
    assert proof['run_id'] == 39286484245
    assert proof['head_sha'] == 'd5e5f57c55d38bbb24f6df04634c846c901e54a9'
    assert proof['run_conclusion'] == proof['job_conclusion'] == 'success'
    assert proof['authenticated_annotation_parts'] == 2
    assert len(raw) == proof['witness_bytes'] == 45583
    assert hashlib.sha256(raw).hexdigest() == proof['witness_sha256'] == 'ac0aa31d6854c541bbaba6be52e3865da9d1a4d77f25b84cab2a77a97857813d'
    assert proof['artifact_zip_independently_downloaded_or_hashed'] is False
    witness = json.loads(raw)
    for name, case in witness['cases'].items():
        folder = tmp_path/name
        folder.mkdir()
        for key, filename in [('launcher', 'launcher-proof.json'), ('http_pdf', 'http-bundled-proof.json')]:
            (folder/filename).write_text(json.dumps(case[key]))
    (tmp_path/'negative-controls.json').write_text(json.dumps(witness['negative_controls']))
    assert script('pdf_bootstrap_sdk_bind').bind(tmp_path) == witness
