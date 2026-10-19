"""Offline binding of actual launcher proof; not a replacement for Windows QA."""
import hashlib
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
DEPS = ROOT / 'docs/dependencies'


def load(name):
    return json.loads((DEPS / name).read_text(encoding='utf-8'))


def test_launcher_witness_is_bound_to_successful_stock_sdk_job_not_prior_source_build():
    p = load('pdf-private-launcher-proof.json')
    raw = (ROOT / p['witness']['path']).read_bytes()
    assert len(raw) == p['witness']['bytes'] == 37306
    assert hashlib.sha256(raw).hexdigest() == p['witness']['sha256'] == '12e65fb720f6096495d43822504b3e605d74eba1af6842256ef9ca95ac216d79'
    assert p['run_id'] == 39182480848 and p['job_id'] == p['job']['id'] == 117837988270
    assert p['conclusion'] == p['job']['conclusion'] == 'success'
    assert p['head_sha'] == p['job']['head_sha'] == '81180987bd1a44e18697829d4d3e2704ff577f1f'
    assert p['artifact']['id'] == 12156887183
    assert p['artifact']['name'] == 'private-pre-import-launcher-pdf-evidence-no-dlls-not-source-proof'
    assert p['artifact']['workflow_run']['head_sha'] == p['head_sha']
    assert p['sdk_archive_sha256'] == 'ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53'
    assert p['dll_count'] == 27 and p['new_source_build_proven'] is False
    assert p['prior_source_proof_applies_to_this_launcher'] is False
    assert p['http_app_startup_proven'] is p['ordinary_launcher_changed'] is p['installed_user_acceptance'] is p['release_authorized'] is False
    assert p['licensed_build_files'] == 14 and p['application_license_changed'] is False
    prior = load('pdf-unicode-bootstrap-proof.json')
    assert prior['run_id'] == p['prior_noticed_source_run_id'] == 39175100427
    assert prior['witness']['sha256'] == '5396a1431461249a6c1b21832553cf1dc6ac0c96034e569728a99e7aec71abf0'
    assert hashlib.sha256((ROOT / prior['witness']['path']).read_bytes()).hexdigest() == prior['witness']['sha256']
    assert prior['verified']['dlls_built_and_loaded_per_process'] == 21
    policy = load('pdf-runtime-license-policy.json')
    assert len(policy['open_gates']) == 6 and all(g['progress']['gate_closed'] is False for g in policy['open_gates'])


def test_launcher_bootstrap_order_no_site_fresh_pids_fonts_and_negative_guards():
    x = load('pdf-private-launcher-evidence.json')
    assert x['private_pre_import_launcher'] == 'SUCCESS'
    assert x['engine_role'] == 'PINNED_STOCK_SDK_NOT_SOURCE_PROVENANCE'
    assert x['new_source_build_proven'] is x['ordinary_launcher_enabled'] is x['http_app_startup_proven'] is False
    assert x['installed_user_acceptance'] is x['release_authorized'] is False
    assert set(x['negative_controls']) == {'missing-no-site', 'early-ctypes', 'wrong-inventory-digest'}
    assert all(v['rejected'] and v['exit_code'] != 0 for v in x['negative_controls'].values())
    a, b = [x['cases'][n] for n in ('first-process', 'restarted-process')]
    assert a['launcher']['pid'] != b['launcher']['pid']
    assert all(a['launcher'][k] == b['launcher'][k] for k in ('inventory_sha256', 'payload_manifest_sha256', 'libffi', 'bootstrap_temp'))
    assert a['pdf']['worker']['unicode_state'] == b['pdf']['worker']['unicode_state']
    hashes = sorted(hashlib.sha256((ROOT / 'backend/app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    for name, case in x['cases'].items():
        p, c = case['launcher'], case['pdf']
        w = c['worker']
        assert p['no_site'] == p['isolated'] == p['utf8_mode'] == 1 and p['windows_acp'] == 65001
        assert p['app_and_weasyprint_absent_before_entry'] and p['target_completed']
        assert not p['release_authorized'] and not p['new_source_build_proven'] and not p['ordinary_launcher_changed']
        assert p['dll_count'] == c['dll_count'] == len(w['loaded_dlls']) == 27
        assert p['libffi'] == w['loaded_dlls']['libffi-8.dll']
        assert w['reused_state'] == (name == 'restarted-process')
        assert w['pango_version_string'] == '1.58.2' and w['expected_pango_version_string'] is None
        assert w['ctypes_callbacks_verified'] and w['development_dependencies_absent']
        assert w['fontconfig_file'] is None and w['fontconfig_mode'] == 'EXPLICIT_UTF8_MEMORY_NO_SYSTEM_FONTS'
        app = PureWindowsPath(w['python']).parent.parent
        assert all(PureWindowsPath(file).parent == app / 'native/pdf/bin' for file in w['loaded_dlls'].values())
        assert all(not w[k].isascii() and ' ' in w[k] for k in ('python', 'unicode_temp', 'unicode_state', 'localappdata', 'working_directory'))
        assert {v['pages'] for v in c['documents'].values()} == {1, 4}
        for v in c['documents'].values():
            assert {f['weight'] for f in v['fonts']} == {400, 700}
            assert all(f['digits'] == '0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩' for f in v['fonts'])
        assert all(v['font_temp_cleaned'] and v['system_fonts'] == 0 and v['font_sha256'] == hashes for v in w['font_documents'].values())
