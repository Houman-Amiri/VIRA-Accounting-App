"""Distinct app-owned SDK bootstrap witness. No source/installed/license approval."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib
from pathlib import Path


def bind(reports: Path) -> dict:
    cases = {n: {k: json.loads((reports/n/f).read_text(encoding='utf-8'))
                 for k, f in [('launcher', 'launcher-proof.json'), ('http_pdf', 'http-bundled-proof.json')]}
             for n in ('first-process', 'restarted-process')}
    for name, case in cases.items():
        p, c = case['launcher'], case['http_pdf']
        w, a = c['worker'], p['activation']
        if (p['role'] != 'PRIVATE_APP_BOOTSTRAP_SDK_HTTP_NOT_INSTALLED'
                or p['target_mode'] != 'PRIVATE_APP_BOOTSTRAP_HTTP'
                or p['preflight_and_activation_module'] != 'app/private_pdf_bootstrap.py'
                or not all(p[k] is True for k in ('target_completed', 'activation_scope_restored',
                                                  'bootstrap_temp_cleaned', 'app_and_weasyprint_absent_before_entry'))
                or p['pid'] != w['pid'] or p['pid'] != a['pid']
                or w['reused_state'] != (name == 'restarted-process')
                or not p['no_site'] == p['isolated'] == p['utf8_mode'] == 1
                or p['windows_acp'] != 65001 or a['windows_acp'] != 65001
                or a['role'] != 'APP_OWNED_PRIVATE_SDK_ACTIVATION_NOT_INSTALLED'
                or a['dll_count'] != 27 or p['dll_count'] != 27 or c['dll_count'] != 27
                or len(w['loaded_dlls']) != 27 or a['payload_files'] <= 27
                or a['manifest_sha256'] != p['payload_manifest_sha256']
                or a['inventory_sha256'] != p['inventory_sha256'] or a['libffi'] != p['libffi']
                or any(p[k] is not False for k in ('source_audit_bound', 'new_source_build_proven',
                                                   'ordinary_launcher_changed', 'release_authorized'))):
            raise ValueError('App-owned bootstrap/activation proof missing')
        d = w['app_owned_dispatch']
        if (w['role'] != 'PRIVATE_APP_OWNED_SDK_HTTP_NOT_INSTALLED_ACCEPTANCE'
                or w['font_adapter_scope'] != 'APPLICATION_OWNED_FACTORY_POLICY_NOT_DEFAULT'
                or d['mode'] != 'PRIVATE_EXPLICIT_FONTCONFIG' or d['renderer_module'] != 'app.services.pdf_rendering'
                or not d['callables_unchanged'] or d['qa_renderer_replacement_used'] is not False
                or d['configuration_factory_supplied_by_qa'] is not False or not d['cache_root_empty']
                or not w['http']['graceful_shutdown'] or w['pango_version'] != '1.58.2'
                or len(w['font_documents']) != 4 or len(c['documents']) != 4):
            raise ValueError('Application-owned HTTP/fonts proof missing')
        if (len({v['font_folder'] for v in w['font_documents']}) != 4
                or len({v['cache_folder'] for v in w['font_documents']}) != 4
                or any(not v['font_temp_cleaned'] or not v['cache_temp_cleaned'] or v['system_fonts'] != 0
                       for v in w['font_documents'])):
            raise ValueError('Document lifetimes/cleanup missing')
        for filename, doc in c['documents'].items():
            response = w['http']['documents'][filename]
            if (doc['pages'] != (4 if 'multi' in filename else 1)
                    or doc['sha256'] != response['sha256'] or doc['bytes'] != response['bytes']):
                raise ValueError('External PDF/HTTP binding differs')
    first, again = [cases[n] for n in ('first-process', 'restarted-process')]
    if (first['launcher']['pid'] == again['launcher']['pid']
            or first['launcher']['activation']['bootstrap_temp'] == again['launcher']['activation']['bootstrap_temp']
            or any(first['launcher'][k] != again['launcher'][k] for k in ('inventory_sha256', 'payload_manifest_sha256', 'libffi'))
            or first['http_pdf']['worker']['database'] != again['http_pdf']['worker']['database']
            or first['http_pdf']['worker']['http']['fixture_ids'] != again['http_pdf']['worker']['http']['fixture_ids']):
        raise ValueError('Distinct workspace/restart/same DB identity missing')
    negatives = json.loads((reports/'negative-controls.json').read_text(encoding='utf-8-sig'))
    if (set(negatives) != {'missing-no-site', 'early-ctypes', 'wrong-inventory-digest', 'unmanifested-code'}
            or not all(v['rejected'] is True and v['exit_code'] != 0 for v in negatives.values())):
        raise ValueError('Actual bootstrap negative controls missing')
    return {'schema': 1, 'role': 'APP_OWNED_SDK_BOOTSTRAP_AND_HTTP_NOT_SOURCE_OR_INSTALLED',
            'cases': cases, 'negative_controls': negatives, 'app_owned_native_activation_proven': True,
            'qa_renderer_replacement_used': False, 'source21_activation_proven': False,
            'ordinary_launcher_enabled': False, 'installed_user_acceptance': False, 'release_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--emit-group', type=int, choices=range(4))
    args = parser.parse_args()
    path = args.reports/'verified-bootstrap-sdk-http.json'
    if args.emit_group is None:
        raw = (json.dumps(bind(args.reports), indent=2)+'\n').encode()
        path.write_bytes(raw)
        print('::notice title=App bootstrap witness digest::'+json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}))
    else:
        encoded = base64.b64encode(zlib.compress(path.read_bytes(), 9)).decode()
        parts = [encoded[n:n+3000] for n in range(0, len(encoded), 3000)]
        if len(parts) > 32:
            raise ValueError('Refuse truncated bootstrap witness')
        for i in range(args.emit_group*8, min(len(parts), (args.emit_group+1)*8)):
            print('::notice title=App bootstrap evidence::'+json.dumps({'part': i, 'total': len(parts), 'data': parts[i]}))


if __name__ == '__main__':
    main()
