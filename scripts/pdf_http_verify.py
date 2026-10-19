"""Development-side inspection of real HTTP PDFs; never copied as dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath

from pdf_native_smoke import DIGITS, inspect_pdf
from pdf_runtime_inventory import BLOCKED


def verify(root: Path, reports: Path) -> dict:
    worker = json.loads((reports / 'http-worker-proof.json').read_text(encoding='utf-8'))
    if worker['role'] != 'PRIVATE_STOCK_SDK_REAL_HTTP_NOT_INSTALLED_ACCEPTANCE':
        raise ValueError('Wrong HTTP evidence role')
    if not worker['isolated'] == worker['no_site'] == worker['utf8_mode'] == 1 or worker['windows_acp'] != 65001:
        raise ValueError('HTTP isolation flags/ACP invalid')
    if any(worker[k] is not False for k in ('new_source_build_proven', 'ordinary_launcher_changed', 'installed_acceptance', 'release_authorized')):
        raise ValueError('Private HTTP must not acquire production/source approval')
    http = worker['http']
    if (http['transport'] != 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT'
            or worker['font_adapter_scope'] != 'PROCESS_LOCAL_QA_INJECTION_NOT_PRODUCTION_DEFAULT'
            or worker['migration_status'] != 'migrated' or http['peak_concurrent_documents'] not in (1, 2) or http['parallel_http_requests'] != 2
            or http['ready']['status'] != 'ready' or not http['ready']['alembic_revision']):
        raise ValueError('Real startup/migration/concurrency evidence missing')
    for flag in ('lifespan_started', 'graceful_shutdown', 'compiled_spa_served', 'production_openapi_route',
                 'unauthorized_pdf_rejected', 'wrong_login_rejected', 'missing_csrf_rejected',
                 'authenticated_owner_session', 'route_context_from_sqlite'):
        if http[flag] is not True:
            raise ValueError('Missing real HTTP control: ' + flag)
    if not worker['development_dependencies_absent']:
        raise ValueError('Inspection packages leaked into app')
    inventory = json.loads((root / 'native/pdf/runtime-inventory.json').read_text(encoding='utf-8'))
    if inventory['distribution_status'] != BLOCKED or len(inventory['dlls']) != 27:
        raise ValueError('Only private stock SDK proof supported')
    if set(worker['loaded_dlls']) != set(inventory['dlls']):
        raise ValueError('Not all private SDK libraries actually loaded')
    app = PureWindowsPath(worker['python']).parent.parent
    for name, item in inventory['dlls'].items():
        if (hashlib.sha256((root / 'native/pdf/bin' / name).read_bytes()).hexdigest() != item['sha256']
                or PureWindowsPath(worker['loaded_dlls'][name]).parent != app / 'native/pdf/bin'):
            raise ValueError('Foreign or changed HTTP native library')
    manifest = json.loads((root / 'install_manifest.json').read_text(encoding='utf-8-sig'))
    for item in manifest['files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid payload baseline path')
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Staged HTTP app changed: ' + item['path'])
    expected = sorted(hashlib.sha256((root / 'app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    records = worker['font_documents']
    if len(records) != 4 or len({v['font_folder'] for v in records}) != 4:
        raise ValueError('Four independent HTTP document configurations required')
    for v in records:
        if not v['font_temp_cleaned'] or v['system_fonts'] != 0 or v['font_sha256'] != expected:
            raise ValueError('HTTP font configuration/cleanup failed')
    documents = {}
    for name, minimum in [('single-page', 1), ('multi-page', 2), ('parallel-single-page', 1), ('parallel-multi-page', 2)]:
        data = (reports / f'{name}.pdf').read_bytes()
        headers = http['documents'][name]
        if headers['status'] != 200 or headers['content_type'] != 'application/pdf' or headers['sha256'] != hashlib.sha256(data).hexdigest() or headers['bytes'] != len(data):
            raise ValueError('HTTP bytes differ from inspected PDF')
        documents[name] = inspect_pdf(data, expected_by_weight={400: DIGITS, 700: '۰۱۲۳۴۵۶۷۸۹'}, min_pages=minimum)
        if minimum == 1 and documents[name]['pages'] != 1:
            raise ValueError('Short real-route order must fit one page')
    return {'worker': worker, 'dll_count': 27, 'documents': documents}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.app_root, args.reports)
    (args.reports / 'http-bundled-proof.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PASS: inspected real HTTP bytes, embedded Vazirmatn, native origin, baseline and cleanup')


if __name__ == '__main__':
    main()
