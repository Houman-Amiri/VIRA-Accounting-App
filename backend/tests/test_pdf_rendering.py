"""App-owned dispatch/lifecycle controls; ALL renderer bytes here are synthetic.

No native Windows/source-build, embedded-font or installed acceptance claims.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import httpx
import pytest

from app.services import pdf, pdf_fontconfig
from app.services.pdf_rendering import PdfRenderer, PrivatePdfPolicy


@pytest.fixture()
def configured(tmp_path, monkeypatch):
    root = tmp_path / 'حافظه & قلم'
    records = []

    @contextmanager
    def configuration(cache):
        assert cache.is_dir()
        marker = cache / 'fake-cache-not-native'
        marker.write_bytes(b'FAKE')
        record = {'cache': cache, 'exited': False}
        records.append(record)
        try:
            yield SimpleNamespace(cache=cache)
        finally:
            record['exited'] = True

    def render(template, context, *, font_configuration):
        assert template == 'proforma.html' and context == {'synthetic': True}
        assert font_configuration.cache.is_dir()
        return b'%PDF-FAKE-UNIT-TEST-NOT-NATIVE'

    monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', configuration)
    monkeypatch.setattr(pdf, 'render_pdf', render)
    return PdfRenderer(PrivatePdfPolicy(root)), root, records


@pytest.mark.parametrize('path', ['relative', '../escape', '/'])
def test_policy_rejects_ambiguous_or_root_paths(path):
    with pytest.raises(ValueError, match='absolute path'):
        PrivatePdfPolicy(Path(path))


def test_policy_rejects_absolute_traversal(tmp_path):
    with pytest.raises(ValueError):
        PrivatePdfPolicy(tmp_path / '..' / 'escape')


def test_policy_is_immutable_and_renderer_rejects_executable_hooks(tmp_path):
    policy = PrivatePdfPolicy(tmp_path / 'cache')
    with pytest.raises(FrozenInstanceError):
        policy.cache_root = tmp_path / 'other'
    with pytest.raises(TypeError):
        PdfRenderer(lambda: None)


def test_default_uses_exact_legacy_call_without_config_or_side_effects(tmp_path, monkeypatch):
    def unexpected(*_):
        raise AssertionError('Legacy must not allocate native configurations')
    monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', unexpected)
    seen = []
    monkeypatch.setattr(pdf, 'render_pdf', lambda *a, **k: seen.append((a, k)) or b'legacy bytes unchanged')
    renderer = PdfRenderer()
    assert renderer.mode == 'LEGACY_DEFAULT'
    assert renderer('template', {'value': 1}) == b'legacy bytes unchanged'
    assert seen == [(('template', {'value': 1}), {})]
    assert not list(tmp_path.iterdir())


def test_each_document_owns_its_cache_and_preserves_unrelated_files(configured):
    renderer, root, records = configured
    root.mkdir()
    sentinel = root / 'do-not-delete'
    sentinel.write_text('unchanged')
    for _ in range(2):
        assert renderer('proforma.html', {'synthetic': True}).startswith(b'%PDF-FAKE')
    assert renderer.mode == 'PRIVATE_EXPLICIT_FONTCONFIG'
    assert len({r['cache'] for r in records}) == 2
    assert all(r['exited'] and not r['cache'].exists() for r in records)
    assert list(root.iterdir()) == [sentinel] and sentinel.read_text() == 'unchanged'


@pytest.mark.parametrize('fault', ['render', 'enter', 'cleanup', 'html', 'not-bytes'])
def test_explicit_failure_never_retries_legacy_and_always_cleans_cache(configured, monkeypatch, fault):
    renderer, root, records = configured
    calls = []

    def render(*args, **kwargs):
        assert set(kwargs) == {'font_configuration'}  # no legacy retry
        calls.append(True)
        if fault == 'render':
            raise RuntimeError('render error')
        return '<html>fake</html>' if fault == 'not-bytes' else (b'<html>fake</html>' if fault == 'html' else b'%PDF-FAKE')

    if fault in ('enter', 'cleanup'):
        @contextmanager
        def configuration(cache):
            if fault == 'enter':
                raise RuntimeError('config error')
            yield object()
            raise RuntimeError('cleanup error')
        monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', configuration)
    monkeypatch.setattr(pdf, 'render_pdf', render)
    with pytest.raises(RuntimeError):
        renderer('proforma.html', {'synthetic': True})
    assert len(calls) == (0 if fault == 'enter' else 1)
    assert root.is_dir() and not list(root.iterdir())
    assert all(r['exited'] for r in records)


@pytest.mark.parametrize('kind', ['root-link', 'ancestor-link', 'file'])
def test_cache_rejects_symlink_or_file_without_deleting_target(tmp_path, kind):
    target = tmp_path / 'target'
    target.mkdir()
    sentinel = target / 'keep'
    sentinel.write_bytes(b'keep')
    cache = tmp_path / 'cache'
    if kind == 'file':
        cache.write_bytes(b'not a directory')
    else:
        cache.symlink_to(target, target_is_directory=True)
        if kind == 'ancestor-link':
            cache /= 'child'
    with pytest.raises(ValueError):
        PdfRenderer(PrivatePdfPolicy(cache))('proforma.html', {})
    assert sentinel.read_bytes() == b'keep'
    assert list(target.iterdir()) == [sentinel]


def test_parallel_synthetic_calls_have_distinct_resources_not_native_throughput(configured, monkeypatch):
    renderer, root, records = configured
    barrier = Barrier(2)

    def render(*args, font_configuration):
        barrier.wait(timeout=10)  # service only, NO database/native renderer
        assert font_configuration.cache.is_dir()
        return b'%PDF-FAKE'

    monkeypatch.setattr(pdf, 'render_pdf', render)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: renderer('proforma.html', {'synthetic': True}), range(2))) == [b'%PDF-FAKE'] * 2
    assert len({r['cache'] for r in records}) == 2
    assert all(r['exited'] for r in records) and not list(root.iterdir())


def test_factory_opt_in_is_per_app_not_env_and_openapi_unchanged(database, tmp_path, monkeypatch):
    from app.main import create_app

    monkeypatch.setenv('PDF_FONT_MODE', 'PRIVATE_EXPLICIT_FONTCONFIG')
    monkeypatch.setenv('PRIVATE_PDF_POLICY', str(tmp_path))
    legacy = create_app(database.settings)
    explicit = create_app(database.settings, private_pdf_policy=PrivatePdfPolicy(tmp_path / 'not-created'))
    try:
        assert legacy.state.pdf_renderer.mode == 'LEGACY_DEFAULT'
        assert explicit.state.pdf_renderer.mode == 'PRIVATE_EXPLICIT_FONTCONFIG'
        assert legacy.state.pdf_renderer is not explicit.state.pdf_renderer
        assert not (tmp_path / 'not-created').exists()
        assert legacy.openapi() == explicit.openapi()
    finally:
        legacy.state.database.dispose()
        explicit.state.database.dispose()


@pytest.fixture()
def owned_app(database, tmp_path):
    from app.main import create_app

    app = create_app(database.settings, private_pdf_policy=PrivatePdfPolicy(tmp_path / 'route-cache'))
    yield app
    app.state.database.dispose()


@pytest.mark.parametrize('failure', [False, True])
async def test_real_route_uses_app_owned_lifecycle_auth_and_unchanged_fallback(owned_app, monkeypatch, failure):
    from .test_operations import _order

    seen = []

    @contextmanager
    def configuration(cache):
        assert cache.is_dir()
        try:
            yield object()
        finally:
            seen.append(cache)

    def render(*args, **kwargs):
        assert set(kwargs) == {'font_configuration'}
        if failure:
            raise RuntimeError('synthetic native failure')
        return b'%PDF-FAKE-API-NOT-WINDOWS-PROOF'

    monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', configuration)
    monkeypatch.setattr(pdf, 'render_pdf', render)
    # Explicitly ASGI + fake bytes: verifies dispatch, not real TCP/native/SPA.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=owned_app), base_url='http://test') as client:
        assert (await client.get('/api/v1/orders/no-order/proforma.pdf')).status_code == 401
        assert not seen
        login = await client.post('/api/v1/auth/login', json={'username': 'owner', 'password': 'test-password-1'})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        order = await _order(client)
        result = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
        assert result.status_code == 200
        if failure:
            assert result.headers['content-type'].startswith('text/html')
            assert result.text.count('data:font/ttf;base64,') == 2
            assert '۲٬۷۶۰٬۷۴۸٫۵' in result.text
            assert "default-src 'none'" in result.headers['content-security-policy']
            assert result.headers['content-disposition'].endswith('.html"')
        else:
            assert result.headers['content-type'] == 'application/pdf'
            assert result.content == b'%PDF-FAKE-API-NOT-WINDOWS-PROOF'
            assert result.headers['content-disposition'].endswith('.pdf"')
    assert len(seen) == 1 and not seen[0].exists()


def test_interrupt_does_not_leak_document_cache(configured, monkeypatch):
    renderer, root, records = configured

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt('synthetic cancellation')

    monkeypatch.setattr(pdf, 'render_pdf', interrupted)
    with pytest.raises(KeyboardInterrupt):
        renderer('proforma.html', {'synthetic': True})
    assert all(r['exited'] for r in records) and not list(root.iterdir())


def test_factory_rejects_non_policy_before_settings_or_database(monkeypatch):
    from app import main

    def forbidden():
        raise AssertionError('Bad policy must fail before loading settings')

    monkeypatch.setattr(main, 'load_settings', forbidden)
    with pytest.raises(TypeError):
        main.create_app(private_pdf_policy=lambda: None)


def test_new_dispatch_module_imports_under_no_site_without_native_or_qa():
    import subprocess
    import sys

    backend = Path(__file__).resolve().parents[1]
    program = f"""
import sys
sys.path.insert(0, {str(backend)!r})
from app.services.pdf_rendering import PdfRenderer, PrivatePdfPolicy
assert PdfRenderer().mode == 'LEGACY_DEFAULT'
assert not any(n == p or n.startswith(p+'.') for n in sys.modules
               for p in ('weasyprint', 'cffi', 'ctypes', 'uvicorn', 'app.services.pdf', 'app.services.pdf_fontconfig'))
assert not any(n.startswith('pdf_private_') for n in sys.modules)
print('PASS: stdlib-only dispatch import, not native proof')
"""
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', program], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS: stdlib-only dispatch import, not native proof'
