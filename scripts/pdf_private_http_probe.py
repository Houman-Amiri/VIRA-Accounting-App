"""CI-only real loopback HTTP/app-factory proof, not installed startup or MIT recipe.

Only the fixed private launcher may enter: fresh no-site bundled interpreter,
verified payload and preloaded audited libffi. No production route is changed.
The font adapter is injected only into this ephemeral QA process.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import logging
import os
import runpy
import secrets
import socket
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

DIGITS = "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"


def isolated_state(root: Path, state: Path, reuse: bool) -> tuple[Path, Path]:
    runner = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    profile = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
    state = state.resolve()
    if (not root.is_relative_to(runner) or not profile.is_relative_to(runner)
            or not state.is_relative_to(profile) or state == profile
            or any(str(p).isascii() or " " not in str(p) for p in (root, state, profile, Path.cwd()))):
        raise ValueError("Private Unicode/spaced app, profile, state and unrelated CWD required")
    if state.exists() != reuse:
        raise ValueError("Fresh state or explicit existing restart state required")
    state.mkdir(parents=True, exist_ok=reuse)
    data = state / "داده آزمایشی HTTP"
    temp = state / "قلم موقت HTTP"
    data.mkdir(exist_ok=reuse)
    temp.mkdir(exist_ok=reuse)
    if any(temp.iterdir()):
        raise ValueError("Inherited HTTP temporary fonts")
    return data, temp


@contextmanager
def environment(values):
    before = {k: os.environ.get(k) for k in values}
    old_temp = tempfile.tempdir
    try:
        os.environ.update(values)
        tempfile.tempdir = None
        yield
    finally:
        for k, v in before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tempfile.tempdir = old_temp


@contextmanager
def loopback_server(app):
    """Real TCP socket and real ASGI lifespan; no TestClient/ASGITransport."""
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))  # CI-local QA only, never a browser preview/service
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, loop="asyncio",
                                         lifespan="on", access_log=False, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 45
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError("Real HTTP startup/lifespan did not complete")
            time.sleep(0.05)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}", server
    finally:
        server.should_exit = True
        if thread.ident is not None:
            thread.join(timeout=30)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("HTTP server failed graceful shutdown")


class FontAudit:
    """Per-document configuration injection, not a production renderer change."""
    def __init__(self, root, temp, cache, render, configuration):
        self.root, self.temp, self.cache = root, temp, cache
        # The existing adapter deliberately requires an already-created cache.
        cache.mkdir(parents=True, exist_ok=True)
        self.render, self.configuration = render, configuration
        self.records = []
        self.lock = threading.Lock()
        self.active = self.peak = 0

    def __call__(self, template, context, **kwargs):
        if template != "proforma.html" or kwargs:
            raise ValueError("Only the unmodified production proforma route is audited")
        from weasyprint.text import fonts

        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            with self.configuration(self.cache) as config:
                data = self.render(template, context, font_configuration=config)
                folder = Path(config._folder)
                if folder.parent.resolve() != self.temp or str(folder).isascii():
                    raise ValueError("HTTP font TEMP escaped private state")
                hashes = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file())
                expected = sorted(hashlib.sha256((self.root / 'app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
                if hashes != expected or fonts.fontconfig.FcConfigGetFonts(config._config, fonts.fontconfig.FcSetSystem).nfont != 0:
                    raise ValueError("HTTP fonts are not exclusively the two bundled TTFs")
                if fonts.PREFERRED_ENCODING.lower().replace('_', '-') != 'utf-8':
                    raise ValueError("Native HTTP font encoding is not UTF-8")
            if folder.exists() or not data.startswith(b'%PDF-'):
                raise ValueError("HTTP native render or strict temporary cleanup failed")
            with self.lock:
                self.records.append({'font_folder': str(folder), 'font_sha256': hashes,
                                     'system_fonts': 0, 'font_temp_cleaned': True,
                                     'lines': len(context['order']['lines'])})
            return data
        except Exception:
            # The real route deliberately catches native failures for HTML fallback.
            # Preserve only a traceback (no locals/credentials/context) in CI stderr.
            import traceback
            traceback.print_exc()
            raise
        finally:
            with self.lock:
                self.active -= 1


class OwnedFontObserver(logging.Handler):
    """Passive plain-value event collector. Never replaces a rendering callable."""
    def __init__(self, root, temp, cache):
        super().__init__()
        self.root, self.temp, self.cache = root, temp, cache
        self.records, self.errors = [], []
        self.active_ids, self.seen = set(), set()
        self.peak = 0

    @property
    def active(self):
        return len(self.active_ids)

    def emit(self, record):
        event = getattr(record, 'pdf_document', None)
        if not isinstance(event, dict):
            return
        key, action = event.get('id'), event.get('event')
        if action == 'started':
            if not isinstance(key, str) or key in self.seen:
                self.errors.append('Duplicate/missing lifecycle ID')
            self.seen.add(key)
            self.active_ids.add(key)
            self.peak = max(self.peak, len(self.active_ids))
        elif action in ('completed', 'failed'):
            if key not in self.active_ids:
                self.errors.append('Completion without matching start')
            self.active_ids.discard(key)
            if action == 'completed':
                self.records.append(dict(event))
            else:
                self.errors.append('Application-owned render failed')
                if record.exc_info:
                    import traceback
                    # Traceback only, no frame locals/context/cookies.
                    traceback.print_exception(*record.exc_info)
        else:
            self.errors.append('Unknown lifecycle event')

    def verify(self):
        expected = sorted(hashlib.sha256((self.root / 'app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
        if self.errors or self.active_ids or len(self.records) != len(self.seen) or len(self.records) != 4:
            raise ValueError('Application-owned lifecycle events missing or failed')
        for value in self.records:
            folder = Path(value['font_folder'])
            cache = Path(value['cache_folder'])
            if (folder.parent.resolve() != self.temp or str(folder).isascii()
                    or cache.parent.resolve() != self.cache or cache.exists() or folder.exists()
                    or not value['cache_temp_cleaned'] or not value['font_temp_cleaned']
                    or value['font_sha256'] != expected or value['system_fonts'] != 0
                    or value['preferred_encoding'].lower().replace('_', '-') != 'utf-8'):
                raise ValueError('Application-owned fonts/cache/UTF-8 cleanup invalid')


def owned_fingerprint(root):
    from inspect import unwrap

    from app.services import pdf, pdf_fontconfig, pdf_rendering

    values = {'render_pdf': pdf.render_pdf,
              'private_font_configuration': pdf_fontconfig.private_font_configuration,
              'renderer_call': pdf_rendering.PdfRenderer.__call__}
    paths = {'render_pdf': 'pdf.py', 'private_font_configuration': 'pdf_fontconfig.py', 'renderer_call': 'pdf_rendering.py'}
    for name, function in values.items():
        if Path(unwrap(function).__code__.co_filename).resolve() != root / 'app/services' / paths[name]:
            raise ValueError('Foreign/replaced application PDF implementation')
    return values


def checked(response, status):
    if response.status_code != status:
        # Do not dump login bodies, cookies, credentials or arbitrary response text.
        raise ValueError(f"HTTP {response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}")
    return response


def exercise_http(app, state, out, password, reuse, audit):
    import httpx

    manifest = state / 'http-fixtures.json'
    with loopback_server(app) as (url, server), httpx.Client(base_url=url, timeout=120, trust_env=False) as client:
        live = checked(client.get('/api/v1/health/live'), 200).json()
        ready = checked(client.get('/api/v1/health/ready'), 200).json()
        if live != {'status': 'alive'} or ready['status'] != 'ready' or not ready['alembic_revision']:
            raise ValueError("Production health/readiness/migration gate failed")
        spa = checked(client.get('/'), 200)
        if 'name="vira-build"' not in spa.text:
            raise ValueError("Staged compiled SPA is not served by the real factory")
        schema = checked(client.get('/api/openapi.json'), 200).json()
        if '/api/v1/orders/{order_id}/proforma.pdf' not in schema['paths']:
            raise ValueError("Actual production PDF route missing")
        checked(client.get('/api/v1/orders/not-an-order/proforma.pdf'), 401)
        checked(client.post('/api/v1/auth/login', json={'username': 'owner', 'password': 'intentionally-wrong-private-password'}), 401)
        login = checked(client.post('/api/v1/auth/login', json={'username': 'owner', 'password': password}), 200)
        if not any('httponly' in v.lower() for v in login.headers.get_list('set-cookie')):
            raise ValueError("Real session cookie was not issued")
        checked(client.post('/api/v1/orders', json={}), 403)
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        client.headers['Origin'] = url
        if reuse:
            fixtures = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            fixtures = {}
            for name, count in [('single-page', 1), ('multi-page', 100)]:
                payload = {'order_date': '2026-10-19', 'customer_name': 'آزمایش خصوصی ' + DIGITS,
                           'customer_phone': DIGITS, 'customer_address': 'فقط داده ساختگی تهران',
                           'items': [{'product_name': 'مدل ' + DIGITS, 'quantity': '1',
                                      'unit_price': '1234567890.1', 'unit_cost': '10'} for _ in range(count)]}
                order = checked(client.post('/api/v1/orders', json=payload), 201).json()
                fixtures[name] = order['id']
            manifest.write_text(json.dumps(fixtures), encoding='utf-8')
        if set(fixtures) != {'single-page', 'multi-page'}:
            raise ValueError("Unexpected persistent HTTP fixture IDs")
        for name, count in [('single-page', 1), ('multi-page', 100)]:
            order = checked(client.get('/api/v1/orders/' + fixtures[name]), 200).json()
            if len(order['items']) != count or Decimal(order['total']) != count * Decimal('1234567890.1'):
                raise ValueError("Persisted real-route order changed across restart")
        documents = {}
        request_barrier = threading.Barrier(2)

        def download(name, filename):
            if filename.startswith("parallel-"):
                request_barrier.wait(timeout=15)
            response = checked(client.get(f'/api/v1/orders/{fixtures[name]}/proforma.pdf'), 200)
            if response.headers.get('content-type') != 'application/pdf' or not response.content.startswith(b'%PDF-'):
                raise ValueError("HTTP HTML fallback is NOT native PDF proof")
            if not response.headers.get('content-disposition', '').endswith('.pdf"'):
                raise ValueError("HTTP PDF disposition is incorrect")
            (out / f'{filename}.pdf').write_bytes(response.content)
            return {'status': 200, 'content_type': 'application/pdf', 'bytes': len(response.content),
                    'sha256': hashlib.sha256(response.content).hexdigest()}

        for name in fixtures:
            documents[name] = download(name, name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = {name: pool.submit(download, name, 'parallel-' + name) for name in fixtures}
            for name, task in pending.items():
                documents['parallel-' + name] = task.result(timeout=150)
        if audit.peak not in (1, 2) or len(audit.records) != 4:
            raise ValueError("Parallel HTTP requests did not complete four document lifecycles")
    if not server.should_exit:
        raise ValueError("Server did not shut down normally")
    return {'transport': 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT', 'lifespan_started': True,
            'graceful_shutdown': True, 'live': live, 'ready': ready,
            'compiled_spa_served': True, 'production_openapi_route': True,
            'unauthorized_pdf_rejected': True, 'wrong_login_rejected': True,
            'missing_csrf_rejected': True, 'authenticated_owner_session': True,
            'route_context_from_sqlite': True, 'fixture_ids': fixtures,
            'parallel_http_requests': 2, 'peak_concurrent_documents': audit.peak,
            'existing_db_session_serialization_preserved': True, 'documents': documents}


def native_state(root, inventory):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetACP.restype = ctypes.c_uint
    if kernel.GetACP() != 65001:
        raise ValueError("HTTP process ACP is not UTF-8")
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    loaded = {}
    for name in inventory['dlls']:
        handle = kernel.GetModuleHandleW(name)
        buffer = ctypes.create_unicode_buffer(32768)
        if not handle or not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
            raise ValueError(f"Audited native library was not loaded by HTTP: {name}")
        if Path(buffer.value).resolve().parent != root / 'native/pdf/bin':
            raise ValueError("Foreign HTTP native dependency")
        loaded[name] = buffer.value
    for kind, value in ((ctypes.c_int, 41), (ctypes.c_double, 41.0)):
        callback = ctypes.CFUNCTYPE(kind, kind)(lambda n: n + 1)
        if callback(value) != 42:
            raise ValueError("HTTP ctypes callback ABI failure")
    pango_name = 'pango-1.0-0.dll' if inventory.get('origin') == 'LOCAL_PINNED_VCPKG_SOURCE_BUILD' else 'libpango-1.0-0.dll'
    pango = ctypes.CDLL(str(root / 'native/pdf/bin' / pango_name))
    pango.pango_version_string.restype = ctypes.c_char_p
    return loaded, pango.pango_version_string().decode('ascii')


def main():
    if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true' or not sys.flags.no_site or not sys.flags.isolated or not sys.flags.utf8_mode:
        raise RuntimeError('Only the private no-site Windows CI launcher may enter HTTP QA')
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('app-root', 'contexts', 'state-root', 'out-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--reuse-state', action='store_true')
    parser.add_argument('--source-audit-sha256')
    parser.add_argument('--app-owned-fonts', action='store_true')
    args = parser.parse_args()
    root = args.app_root.resolve(strict=True)
    if Path(sys.executable).resolve() != root / 'python/python.exe' or Path(sys.base_prefix).resolve() != root / 'python':
        raise ValueError('Foreign HTTP interpreter')
    # Enforce entry provenance even if someone invokes this worker directly.
    if not {'cffi', 'ctypes'} <= sys.modules.keys() or any(n in sys.modules for n in ('app.main', 'uvicorn', 'weasyprint')):
        raise ValueError('HTTP worker requires pre-import launcher order')
    data, temp = isolated_state(root, args.state_root, args.reuse_state)
    state = args.state_root.resolve()
    password = os.environ['VIRA_PRIVATE_HTTP_PASSWORD']
    if len(password) < 32:
        raise ValueError('Ephemeral CI credential required')
    if any(importlib.util.find_spec(n) is not None for n in ('pypdf', 'pefile')):
        raise ValueError('Development inspection packages leaked into HTTP app')
    database = data / 'data/خصوصی.sqlite3'
    values = {'TEMP': str(temp), 'TMP': str(temp), 'DATA_DIR': str(data),
              'SQLITE_DATABASE_PATH': str(database), 'RECEIPT_DIR': str(data / 'receipts'),
              'ENVIRONMENT': 'development', 'STRICT_SECRETS': 'false', 'SCHEDULER_ENABLED': 'false',
              'SESSION_SECRET': secrets.token_urlsafe(48),
              'FONTCONFIG_FILE': str(state / 'تنظیم ناموجود fonts.conf'), 'FONTCONFIG_PATH': str(state)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with environment(values):
        migrate = runpy.run_path(str(root / 'scripts/migrate_vira.py'))
        migration = migrate['run_migration'](database, None)
        from app.config import load_settings
        from app.db import Database
        from app.seed import seed_owner_user
        from app.services import pdf
        from app.services.pdf_fontconfig import private_font_configuration

        settings = load_settings(_env_file=None, **{k.lower(): v for k, v in values.items() if k in ('DATA_DIR', 'SQLITE_DATABASE_PATH', 'RECEIPT_DIR', 'ENVIRONMENT', 'STRICT_SECRETS', 'SCHEDULER_ENABLED', 'SESSION_SECRET')})
        seed_db = Database(settings)
        try:
            with seed_db.session() as session:
                seed_owner_user(session, password=password)
        finally:
            seed_db.dispose()
        dispatch = None
        if args.app_owned_fonts:
            from app.main import create_app
            from app.services.pdf_rendering import PdfRenderer, PrivatePdfPolicy

            fingerprints = owned_fingerprint(root)
            cache = state / 'حافظه قلم متعلق به برنامه'
            audit = OwnedFontObserver(root, temp, cache)
            logger = logging.getLogger('app.services.pdf_rendering')
            level, disabled = logger.level, logger.disabled
            logger.disabled = False  # migration fileConfig may disable pre-existing loggers
            logger.setLevel(logging.INFO)
            logger.addHandler(audit)
            try:
                app = create_app(settings, private_pdf_policy=PrivatePdfPolicy(cache))
                renderer = app.state.pdf_renderer
                if type(renderer) is not PdfRenderer or renderer.mode != 'PRIVATE_EXPLICIT_FONTCONFIG':
                    raise ValueError('Factory did not select its own private PDF service')
                http = exercise_http(app, state, args.out_dir, password, args.reuse_state, audit)
                audit.verify()
                after = owned_fingerprint(root)
                if any(after[k] is not v for k, v in fingerprints.items()) or app.state.pdf_renderer is not renderer:
                    raise ValueError('Application PDF implementation was replaced during HTTP')
                dispatch = {'mode': renderer.mode, 'renderer_module': type(renderer).__module__,
                            'callables_unchanged': True, 'qa_renderer_replacement_used': False,
                            'configuration_factory_supplied_by_qa': False,
                            'diagnostics': 'PASSIVE_PLAIN_VALUE_LOG_RECORDS_NOT_CONFIG_OBJECTS',
                            'cache_root': str(cache), 'cache_root_empty': not any(cache.iterdir())}
            finally:
                logger.removeHandler(audit)
                logger.setLevel(level)
                logger.disabled = disabled
        else:
            original = pdf.render_pdf
            audit = FontAudit(root, temp, state / 'حافظه قلم HTTP', original, private_font_configuration)
            pdf.render_pdf = audit
            try:
                from app.main import create_app

                app = create_app(settings)
                http = exercise_http(app, state, args.out_dir, password, args.reuse_state, audit)
            finally:
                pdf.render_pdf = original
        inventory = json.loads((root / 'native/pdf/runtime-inventory.json').read_text())
        loaded, version = native_state(root, inventory)
        source = args.source_audit_sha256 is not None
        expected_version = '1.58.0-vira-local-source' if source else '1.58.2'
        if version != expected_version:
            raise ValueError('HTTP executed an unexpected Pango function')
        if any(temp.iterdir()) or audit.active:
            raise ValueError('HTTP temporary resources leaked')
        result = {'schema': 1, 'role': 'PRIVATE_STOCK_SDK_REAL_HTTP_NOT_INSTALLED_ACCEPTANCE',
                  'pid': os.getpid(), 'python': str(Path(sys.executable)), 'isolated': sys.flags.isolated,
                  'no_site': sys.flags.no_site, 'utf8_mode': sys.flags.utf8_mode, 'windows_acp': 65001,
                  'state': str(state), 'database': str(database), 'temp': str(temp),
                  'reused_state': args.reuse_state, 'migration_status': migration['status'],
                  'font_adapter_scope': 'PROCESS_LOCAL_QA_INJECTION_NOT_PRODUCTION_DEFAULT',
                  'font_documents': audit.records, 'loaded_dlls': loaded, 'pango_version': version,
                  'development_dependencies_absent': True, 'http': http,
                  'new_source_build_proven': False, 'ordinary_launcher_changed': False,
                  'installed_acceptance': False, 'release_authorized': False}
        result['source_audit_sha256'] = args.source_audit_sha256
        result['source_audit_bound'] = source
        if source:
            result['role'] = 'PRIVATE_NOTICED_SOURCE_REAL_HTTP_NOT_INSTALLED_ACCEPTANCE'
        if args.app_owned_fonts:
            result['role'] = ('PRIVATE_APP_OWNED_SOURCE_HTTP_NOT_INSTALLED_ACCEPTANCE' if source else
                              'PRIVATE_APP_OWNED_SDK_HTTP_NOT_INSTALLED_ACCEPTANCE')
            result['font_adapter_scope'] = 'APPLICATION_OWNED_FACTORY_POLICY_NOT_DEFAULT'
            result['app_owned_dispatch'] = dispatch
        (args.out_dir / 'http-worker-proof.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('PASS: real private HTTP startup, authenticated PDF, parallel document cleanup and graceful shutdown')


if __name__ == '__main__':
    main()
