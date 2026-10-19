"""Bind separately scoped SDK/source application-owned HTTP witnesses. Private QA.

No MIT grant for this file, no production/installed/distribution approval.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib
from pathlib import Path


def bind(reports: Path, source_audit: Path | None = None) -> dict:
    source = source_audit is not None
    if source:
        from pdf_source_http_bind import bind as bind_source
        result = bind_source(source_audit, reports, app_owned=True)
        cases = result.pop('source_http_cases')
    else:
        cases = {name: {kind: json.loads((reports / name / filename).read_text(encoding='utf-8'))
                       for kind, filename in [('launcher', 'launcher-proof.json'), ('http_pdf', 'http-bundled-proof.json')]}
                 for name in ('first-process', 'restarted-process')}
        result = {'schema': 1, 'new_source_build_proven': False, 'source21_http_pair_proven': False,
                  'font_adapter_is_production_default': False, 'ordinary_launcher_enabled': False,
                  'installed_user_acceptance': False, 'release_authorized': False,
                  'negative_controls': json.loads((reports / 'negative-controls.json').read_text(encoding='utf-8-sig'))}
    count = 21 if source else 27
    for name, value in cases.items():
        parent, child = value['launcher'], value['http_pdf']['worker']
        owned = child['app_owned_dispatch']
        if (parent['target_mode'] != 'PRIVATE_APP_OWNED_HTTP' or not parent['target_completed']
                or parent['pid'] != child['pid'] or child['reused_state'] != (name == 'restarted-process')
                or parent['no_site'] != 1 or parent['isolated'] != 1 or parent['utf8_mode'] != 1
                or parent['windows_acp'] != 65001 or not parent['app_and_weasyprint_absent_before_entry']
                or parent['dll_count'] != count or value['http_pdf']['dll_count'] != count or len(child['loaded_dlls']) != count
                or child['role'] != ('PRIVATE_APP_OWNED_SOURCE_HTTP_NOT_INSTALLED_ACCEPTANCE' if source else 'PRIVATE_APP_OWNED_SDK_HTTP_NOT_INSTALLED_ACCEPTANCE')
                or child['font_adapter_scope'] != 'APPLICATION_OWNED_FACTORY_POLICY_NOT_DEFAULT'
                or owned['mode'] != 'PRIVATE_EXPLICIT_FONTCONFIG' or owned['renderer_module'] != 'app.services.pdf_rendering'
                or owned['callables_unchanged'] is not True or owned['qa_renderer_replacement_used'] is not False
                or owned['configuration_factory_supplied_by_qa'] is not False or not owned['cache_root_empty']
                or owned['diagnostics'] != 'PASSIVE_PLAIN_VALUE_LOG_RECORDS_NOT_CONFIG_OBJECTS'
                or not child['http']['graceful_shutdown']):
            raise ValueError('Application-owned process/dispatch proof missing')
        documents = value['http_pdf']['documents']
        if len(documents) != 4 or len(child['font_documents']) != 4:
            raise ValueError('Four actual documents required per process')
        if len({v['font_folder'] for v in child['font_documents']}) != 4 or len({v['cache_folder'] for v in child['font_documents']}) != 4:
            raise ValueError('Independent per-document font/cache resources required')
        if any(not v['font_temp_cleaned'] or not v['cache_temp_cleaned'] or v['system_fonts'] != 0 for v in child['font_documents']):
            raise ValueError('Application-owned resource cleanup failed')
        for filename, doc in documents.items():
            response = child['http']['documents'][filename]
            if doc['pages'] != (4 if 'multi' in filename else 1) or doc['sha256'] != response['sha256'] or doc['bytes'] != response['bytes']:
                raise ValueError('Actual HTTP byte/pagination binding differs')
    first, again = [cases[n] for n in ('first-process', 'restarted-process')]
    if (first['launcher']['pid'] == again['launcher']['pid']
            or any(first['launcher'][k] != again['launcher'][k] for k in ('inventory_sha256', 'payload_manifest_sha256', 'libffi'))
            or first['http_pdf']['worker']['database'] != again['http_pdf']['worker']['database']
            or first['http_pdf']['worker']['http']['fixture_ids'] != again['http_pdf']['worker']['http']['fixture_ids']):
        raise ValueError('Fresh restart/DB/baseline identity differs')
    negatives = result['negative_controls']
    if set(negatives) != {'missing-no-site', 'early-ctypes', 'wrong-inventory-digest'} or not all(v['rejected'] and v['exit_code'] != 0 for v in negatives.values()):
        raise ValueError('Actual negative controls missing')
    result.update(role=('PRIVATE_NOTICED_SOURCE_APP_OWNED_HTTP_NOT_DISTRIBUTION' if source else 'PRIVATE_SDK_APP_OWNED_HTTP_NOT_SOURCE_OR_INSTALLED_PROOF'),
                  cases=cases, app_owned_dispatch_proven=True, http_app_startup_proven=True,
                  qa_renderer_replacement_used=False, configuration_factory_supplied_by_qa=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--source-audit', type=Path)
    parser.add_argument('--emit-group', type=int, choices=range(4))
    args = parser.parse_args()
    path = args.reports / 'verified-app-owned-http.json'
    if args.emit_group is None:
        raw = (json.dumps(bind(args.reports, args.source_audit), indent=2)+'\n').encode()
        path.write_bytes(raw)
        print('::notice title=App-owned HTTP witness digest::'+json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}))
    else:
        data = base64.b64encode(zlib.compress(path.read_bytes(), 9)).decode()
        parts = [data[n:n+3000] for n in range(0, len(data), 3000)]
        if len(parts) > 32:
            raise ValueError('Refusing to truncate app-owned witness beyond32 parts')
        for i in range(args.emit_group*8, min(len(parts), (args.emit_group+1)*8)):
            print('::notice title=App-owned HTTP evidence::'+json.dumps({'part': i, 'total': len(parts), 'data': parts[i]}))


if __name__ == '__main__':
    main()
