"""Offline guards and real local TCP app tests. Fake PDF bytes are NOT native proof."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


http = script('pdf_private_http_probe')
launcher = script('pdf_private_launcher')


def test_http_worker_import_is_stdlib_only():
    code = f"import runpy,sys;runpy.run_path({str(ROOT / 'scripts/pdf_private_http_probe.py')!r});assert not any(n in sys.modules for n in ('app','uvicorn','cffi','ctypes','weasyprint','httpx'))"
    subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], check=True)


def test_direct_worker_cannot_start_service_outside_private_windows():
    with pytest.raises(RuntimeError, match='private no-site Windows'):
        http.main()


def paths(tmp_path, monkeypatch):
    runner = tmp_path / 'runner'
    profile = runner / 'کاربر با فاصله'
    app = runner / 'برنامه با فاصله'
    cwd = profile / 'جای دیگر'
    cwd.mkdir(parents=True)
    app.mkdir()
    monkeypatch.setenv('RUNNER_TEMP', str(runner))
    monkeypatch.setenv('LOCALAPPDATA', str(profile))
    monkeypatch.chdir(cwd)
    return app, profile / 'حالت خصوصی'


def test_first_state_restart_and_inherited_font_rejection(tmp_path, monkeypatch):
    root, state = paths(tmp_path, monkeypatch)
    data, temp = http.isolated_state(root, state, False)
    assert data.parent == temp.parent == state
    with pytest.raises(ValueError, match='Fresh state'):
        http.isolated_state(root, state, False)
    assert http.isolated_state(root, state, True) == (data, temp)
    (temp / 'leak.ttf').write_bytes(b'not-a-font')
    with pytest.raises(ValueError, match='Inherited HTTP'):
        http.isolated_state(root, state, True)


def test_restart_requires_existing_state(tmp_path, monkeypatch):
    root, state = paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='Fresh state'):
        http.isolated_state(root, state, True)


@pytest.mark.parametrize('escape', ['outside', 'profile', 'ascii'])
def test_state_refuses_nonprivate_paths(tmp_path, monkeypatch, escape):
    root, state = paths(tmp_path, monkeypatch)
    if escape == 'outside':
        state = tmp_path / 'حالت بیرون'
    elif escape == 'profile':
        state = state.parent
    else:
        root = tmp_path / 'runner' / 'ascii'
    with pytest.raises(ValueError, match='Private Unicode'):
        http.isolated_state(root, state, False)


def test_environment_restores_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('TEMP', 'original')
    monkeypatch.delenv('PRIVATE_MISSING', raising=False)
    with pytest.raises(RuntimeError), http.environment({'TEMP': str(tmp_path), 'PRIVATE_MISSING': 'set'}):
        raise RuntimeError('simulated HTTP failure')
    import os
    assert os.environ['TEMP'] == 'original' and 'PRIVATE_MISSING' not in os.environ


def test_http_required_target_cannot_be_missing_from_baseline(tmp_path):
    # Reuse the prior synthetic guard fixture builder, never a native payload.
    legacy = script_test_fixture()
    root = legacy.payload.__wrapped__(tmp_path)
    hashes = legacy.stamp(root)
    with pytest.raises(ValueError, match='Required bootstrap files'):
        launcher.validate_payload(root, *hashes, http_proof=True)
    for name in ('scripts/pdf_private_http_probe.py', 'app/main.py', 'scripts/migrate_vira.py', 'backend/alembic.ini'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'only a unit fixture')
    hashes = legacy.stamp(root)
    assert len(launcher.validate_payload(root, *hashes, http_proof=True)['dlls']) == 27
    (root / 'scripts/pdf_private_http_probe.py').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Baseline file changed'):
        launcher.validate_payload(root, *hashes, http_proof=True)


def script_test_fixture():
    spec = importlib.util.spec_from_file_location('legacy_launcher_test', ROOT / 'backend/tests/test_pdf_private_launcher.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAudit:
    """Only HTTP routing/lifespan/SQLite tested here; external PDF inspection rejects these bytes."""
    def __init__(self, html=False):
        self.active = self.peak = 0
        self.barrier = None
        self.records = []
        self.lock = threading.Lock()
        self.html = html

    def __call__(self, template, context):
        if self.html:
            raise RuntimeError('simulated native engine failure')
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.barrier:
                self.barrier.wait(5)
            self.records.append({'unit_test_fake_bytes': True})
            return b'%PDF-THIS-IS-NOT-A-VALID-PDF-UNIT-TEST-ONLY'
        finally:
            with self.lock:
                self.active -= 1


def make_app(database, tmp_path, monkeypatch):
    static = tmp_path / 'unit-static'
    static.mkdir()
    (static / 'index.html').write_text('<meta name="vira-build" content="UNIT-FAKE-NOT-COMPILED-SPA">')
    monkeypatch.setenv('VIRA_STATIC_DIR', str(static))
    from app.main import create_app
    return create_app(database.settings)


def test_real_tcp_factory_auth_csrf_orders_restart_and_shutdown(database, tmp_path, monkeypatch):
    from app.services import pdf

    state, out = tmp_path / 'state', tmp_path / 'reports'
    state.mkdir()
    out.mkdir()
    first = None
    for reuse in (False, True):
        # Each create_app gets its own DB engine; never reuse a disposed lifespan engine.
        static = tmp_path / ('static-' + str(reuse))
        static.mkdir()
        (static / 'index.html').write_text('<meta name="vira-build" content="UNIT-FAKE-NOT-COMPILED">')
        monkeypatch.setenv('VIRA_STATIC_DIR', str(static))
        from app.main import create_app
        app = create_app(database.settings)
        audit = FakeAudit()
        monkeypatch.setattr(pdf, 'render_pdf', audit)
        result = http.exercise_http(app, state, out, 'test-password-1', reuse, audit)
        assert result['transport'] == 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT'
        assert result['graceful_shutdown'] and result['missing_csrf_rejected']
        assert result['parallel_http_requests'] == 2 and result['peak_concurrent_documents'] in (1, 2) and len(result['documents']) == 4
        if first:
            assert result['fixture_ids'] == first['fixture_ids']
        first = result
    assert len(list(out.glob('*.pdf'))) == 4
    assert json.loads((state / 'http-fixtures.json').read_text()) == first['fixture_ids']


def test_real_tcp_html_fallback_is_failure_not_success(database, tmp_path, monkeypatch):
    from app.services import pdf
    app = make_app(database, tmp_path, monkeypatch)
    audit = FakeAudit(html=True)
    monkeypatch.setattr(pdf, 'render_pdf', audit)
    state, out = tmp_path / 'state', tmp_path / 'out'
    state.mkdir()
    out.mkdir()
    with pytest.raises(ValueError, match='HTML fallback'):
        http.exercise_http(app, state, out, 'test-password-1', False, audit)
    assert not list(out.glob('*.pdf'))


def test_workflow_exports_fixture_before_consumer_and_runs_http_mode():
    import yaml
    workflow = yaml.safe_load((ROOT / '.github/workflows/pdf-private-http.yml').read_text())
    steps = workflow['jobs']['launcher']['steps']
    producer = next(i for i, x in enumerate(steps) if 'prepare_pdf_native_fixture.ps1' in x.get('run', ''))
    consumer = next(i for i, x in enumerate(steps) if 'pdf_runtime_inventory.py' in x.get('run', ''))
    assert producer < consumer
    assert '-HttpProof' in next(x['run'] for x in steps if 'pdf_launcher_smoke.ps1 -Candidate' in x.get('run', ''))
    assert "sha256" in next(x['run'] for x in steps if 'combined-http-proof.json' in x.get('run', ''))
    artifact = next(x for x in steps if x.get('uses') == 'actions/upload-artifact@v4')
    assert artifact['with']['path'] == 'reports/private-http/'
    assert 'no-app-db-dlls' in artifact['with']['name']


def test_old_native_witness_bytes_are_immutable():
    p = json.loads((ROOT / 'docs/dependencies/pdf-private-launcher-proof.json').read_text())
    assert hashlib.sha256((ROOT / p['witness']['path']).read_bytes()).hexdigest() == p['witness']['sha256']
    assert p['http_app_startup_proven'] is False  # historical proof is NOT relabelled


def test_auditor_creates_cache_required_by_existing_adapter(tmp_path):
    from app.services.pdf_fontconfig import configuration_xml

    cache = tmp_path / 'حافظه قلم HTTP'
    assert not cache.exists()
    http.FontAudit(tmp_path, tmp_path, cache, None, None)
    assert cache.is_dir() and b'fontconfig' in configuration_xml(cache)


def test_actual_http_witness_is_bound_to_successful_windows_job_not_old_proofs():
    deps = ROOT / 'docs/dependencies'
    proof = json.loads((deps / 'pdf-private-http-proof.json').read_text())
    raw = (ROOT / proof['witness']['path']).read_bytes()
    assert len(raw) == proof['witness']['bytes'] == 37611
    assert hashlib.sha256(raw).hexdigest() == proof['witness']['sha256'] == '5d083bc6072a8bdd40b67bb5360f3751879cedffda7f385845353d785056518b'
    assert proof['run_id'] == 39215968473 and proof['job_id'] == proof['job']['id'] == 117939764052
    assert proof['conclusion'] == proof['job']['conclusion'] == 'success'
    assert proof['head_sha'] == proof['job']['head_sha'] == proof['artifact']['workflow_run']['head_sha'] == '7634e93e08c901246e7c08fd06777795bae6e7f9'
    assert proof['artifact']['id'] == 12169508388
    assert proof['witness']['authenticated_annotation_parts'] == 2
    assert proof['http_app_startup_proven'] is True and proof['licensed_build_files'] == 14
    for key in ('source21_launcher_pair_proven', 'new_source_build_proven', 'ordinary_launcher_changed', 'font_adapter_is_production_default', 'installed_user_acceptance', 'release_authorized', 'application_license_changed', 'prior_evidence_relabelled'):
        assert proof[key] is False
    prior = json.loads((deps / 'pdf-private-launcher-proof.json').read_text())
    assert prior['run_id'] == proof['prior_launcher_run_id'] == 39182480848
    assert prior['http_app_startup_proven'] is False
    gates = json.loads((deps / 'pdf-runtime-license-policy.json').read_text())['open_gates']
    assert len(gates) == 6 and all(g['progress']['gate_closed'] is False for g in gates)


def test_actual_http_restart_native_fonts_security_and_serialization_scope():
    from pathlib import PureWindowsPath
    x = json.loads((ROOT / 'docs/dependencies/pdf-private-http-evidence.json').read_text())
    assert x['http_app_startup_proven'] is True and x['font_adapter_is_production_default'] is False
    a, b = [x['cases'][key] for key in ('first-process', 'restarted-process')]
    assert a['launcher']['pid'] != b['launcher']['pid']
    assert a['http_pdf']['worker']['database'] == b['http_pdf']['worker']['database']
    assert a['http_pdf']['worker']['http']['fixture_ids'] == b['http_pdf']['worker']['http']['fixture_ids']
    hashes = sorted(hashlib.sha256((ROOT / 'backend/app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    for name, case in x['cases'].items():
        p, c = case['launcher'], case['http_pdf']
        w, h = c['worker'], c['worker']['http']
        assert p['target_mode'] == 'PRIVATE_HTTP_QA' and p['target_completed'] and p['app_and_weasyprint_absent_before_entry']
        assert p['no_site'] == p['isolated'] == p['utf8_mode'] == 1 and p['windows_acp'] == 65001
        assert w['reused_state'] == (name == 'restarted-process') and w['pango_version'] == '1.58.2'
        assert h['transport'] == 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT'
        assert h['parallel_http_requests'] == 2 and h['peak_concurrent_documents'] == 1  # observed, not two concurrent native renders
        assert h['ready']['alembic_revision'] == '0006_item_catalog' and h['ready']['status'] == 'ready'
        assert all(h[k] is True for k in ('lifespan_started', 'graceful_shutdown', 'compiled_spa_served', 'production_openapi_route', 'unauthorized_pdf_rejected', 'wrong_login_rejected', 'missing_csrf_rejected', 'authenticated_owner_session', 'route_context_from_sqlite'))
        assert len(w['loaded_dlls']) == c['dll_count'] == 27
        app = PureWindowsPath(w['python']).parent.parent
        assert all(PureWindowsPath(v).parent == app / 'native/pdf/bin' for v in w['loaded_dlls'].values())
        assert len({v['font_folder'] for v in w['font_documents']}) == 4
        assert all(v['font_temp_cleaned'] and v['system_fonts'] == 0 and v['font_sha256'] == hashes for v in w['font_documents'])
        for filename, d in c['documents'].items():
            assert d['pages'] == (4 if 'multi' in filename else 1)
            assert d['sha256'] == h['documents'][filename]['sha256'] and d['bytes'] == h['documents'][filename]['bytes']
            assert all(f['digits'] == (http.DIGITS if f['weight'] == 400 else '۰۱۲۳۴۵۶۷۸۹') for f in d['fonts'])
    assert all(v['rejected'] and v['exit_code'] != 0 for v in x['negative_controls'].values())
