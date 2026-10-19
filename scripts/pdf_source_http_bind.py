"""Bind this run's audited noticed-source compilation to real HTTP PDF bytes.

Private QA only; outside the limited MIT build-script grant. No distribution rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pdf_private_launcher import SOURCE_VERSION, validate_source_inventory


def compact_inventory(inventory: dict) -> dict:
    """Validated binding fields only; full inventory remains in the artifact.

    Repeating upstream copyright/receipt text twice can exceed Actions annotation
    limits. This is a declared projection, NOT the byte-hashed full inventory.
    """
    result = {k: inventory[k] for k in ('origin', 'private_consumption_only',
        'modified_build_is_distribution_candidate', 'source_archive', 'binary_cache',
        'distribution_status', 'native_audit_sha256', 'expected_pango_version_string', 'preload_dlls')}
    result['dlls'] = {n: {k: v[k] for k in ('sha256', 'source_package')} for n, v in inventory['dlls'].items()}
    result['source_packages'] = {n: {k: v[k] for k in ('patched_source_tree_sha256', 'patched_source_files')}
                                 for n, v in inventory['source_packages'].items()}
    return result


def bind(audit_path: Path, reports: Path) -> dict:
    raw = audit_path.read_bytes()
    audit = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    cases = {}
    for name in ('first-process', 'restarted-process'):
        folder = reports / name
        p = json.loads((folder / 'launcher-proof.json').read_text(encoding='utf-8'))
        c = json.loads((folder / 'http-bundled-proof.json').read_text(encoding='utf-8'))
        inv = json.loads((folder / 'runtime-inventory.json').read_text(encoding='utf-8'))
        validate_source_inventory(inv, audit, digest)
        w = c['worker']
        if (p['role'] != 'PRIVATE_NOTICED_SOURCE_HTTP_LAUNCHER_NOT_DISTRIBUTION'
                or p['source_audit_sha256'] != digest or w['source_audit_sha256'] != digest
                or not p['source_audit_bound'] or not w['source_audit_bound']
                or p['target_mode'] != 'PRIVATE_HTTP_QA' or not p['target_completed']
                or p['no_site'] != 1 or p['isolated'] != 1 or p['utf8_mode'] != 1
                or p['windows_acp'] != 65001 or not p['app_and_weasyprint_absent_before_entry']
                or p['pid'] != w['pid'] or w['reused_state'] != (name == 'restarted-process')
                or c['dll_count'] != 21 or set(w['loaded_dlls']) != set(audit['dlls'])
                or w['pango_version'] != SOURCE_VERSION
                or not w['http']['graceful_shutdown']):
            raise ValueError('Fresh source audit, bootstrap and HTTP process are not bound')
        for filename, doc in c['documents'].items():
            if doc['pages'] != (4 if 'multi' in filename else 1):
                raise ValueError('Actual source HTTP PDF pagination differs')
        if len(c['documents']) != 4 or len(w['font_documents']) != 4:
            raise ValueError('Four inspected HTTP PDFs per process required')
        cases[name] = {'launcher': p, 'http_pdf': c, 'inventory': compact_inventory(inv)}
    a, b = [cases[k] for k in ('first-process', 'restarted-process')]
    if (a['launcher']['pid'] == b['launcher']['pid']
            or any(a['launcher'][k] != b['launcher'][k] for k in ('inventory_sha256', 'payload_manifest_sha256', 'libffi', 'source_audit_sha256'))
            or a['http_pdf']['worker']['database'] != b['http_pdf']['worker']['database']
            or a['http_pdf']['worker']['http']['fixture_ids'] != b['http_pdf']['worker']['http']['fixture_ids']):
        raise ValueError('Source HTTP restart changed baseline/DB/fixture identity')
    negatives = json.loads((reports / 'negative-controls.json').read_text(encoding='utf-8-sig'))
    if set(negatives) != {'missing-no-site', 'early-ctypes', 'wrong-inventory-digest'} or not all(v['rejected'] and v['exit_code'] != 0 for v in negatives.values()):
        raise ValueError('Actual source HTTP negative controls missing')
    return {'schema': 1, 'role': 'PRIVATE_NOTICED_SOURCE_BUILD_AND_REAL_HTTP_NOT_DISTRIBUTION',
            'native_audit': audit, 'native_audit_sha256': digest, 'source_http_cases': cases,
            'negative_controls': negatives,
            'inventory_representation': 'VALIDATED_BINDING_PROJECTION_FULL_BYTE_HASHED_INVENTORY_IN_ARTIFACT',
            'source21_http_pair_proven': True,
            'new_source_build_proven': True, 'http_app_startup_proven': True,
            'stock_sdk_used_in_source_job': False, 'font_adapter_is_production_default': False,
            'ordinary_launcher_enabled': False, 'installed_user_acceptance': False,
            'release_authorized': False,
            'not_proven': ['Full component/CRT rights and recipient rebuild/toolchain review',
                           'Durable anonymous corresponding-source delivery',
                           'Ordinary production startup, signing and minimum OS matrix',
                           'Inno/native delta/rollback and installed LGPL replacement/EULA',
                           'Installed user or visual acceptance', 'Offline/bitwise rebuild'],
            'cpython_ctypes_ffi_note': 'Source closure pins ffi-8.dll. CPython _ctypes may use its distinct bundled libffi-8.dll; no rename/alias or claim it uses the source-built FFI.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--reports', type=Path, required=True)
    args = p.parse_args()
    raw = (json.dumps(bind(args.audit, args.reports), indent=2) + '\n').encode('utf-8')
    (args.reports / 'verified-source-http.json').write_bytes(raw)
    print('::notice title=Source HTTP witness digest::' + json.dumps({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
