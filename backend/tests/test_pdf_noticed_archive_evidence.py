"""Check the pinned, actually completed noticed-archive build/PDF witness offline."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPS = ROOT / 'docs/dependencies'


def test_completed_archive_build_is_bound_to_compiled_bytes_and_candidate_audit():
    proof = json.loads((DEPS / 'pdf-noticed-archive-build-proof.json').read_text())
    raw = (ROOT / proof['witness']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == proof['witness']['sha256'] == '80c0d38278902dd3602043182dfa487249c7673cca30003db36f657489b2df4e'
    assert len(raw) == proof['witness']['size'] == 66283
    x = json.loads(raw)
    assert proof['run_id'] == 39165372821 and proof['conclusion'] == 'success'
    assert proof['head_sha'] == '84c20ac0d47bc956da63a44d0b82b81fc0410bbb'
    assert len(proof['jobs']) == 2 and all(j['conclusion'] == 'success' for j in proof['jobs'])
    assert x['private_noticed_archive_build_and_pdf'] == 'SUCCESS'
    assert x['compiled_from_noticed_archive'] and x['inline_change_date_notice_present_in_compiled_source']
    assert x['noticed_source_archive_sha256'] == proof['source_archive']['sha256'] == 'b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2'
    assert hashlib.sha256(x['explicit_edit']['modified_source_file'].encode()).hexdigest() == proof['source_archive']['modified_file_sha256']
    assert x['explicit_edit']['modified_source_file'].startswith('/* VIRA modification notice - 2026-10-19\n')
    old = json.loads((DEPS / 'pdf-local-source-app-consumer-evidence.json').read_text())
    assert len(x['preferred_source_trees']) == 20
    assert x['preferred_source_trees']['pango'] != old['preferred_source_trees']['pango']
    assert all(t == old['preferred_source_trees'][n] for n, t in x['preferred_source_trees'].items() if n != 'pango')
    native = dict(x)
    for k in ['consumer', 'consumer_candidate_audit_sha256', 'consumer_inventory_sha256', 'private_noticed_archive_build_and_pdf', 'private_local_source_payload_pdf', 'installed_app_replacement_proven', 'production_fontconfig_unicode_environment_proven', 'native_only_not_proven']:
        native.pop(k)
    native['not_proven'] = x['native_only_not_proven']
    assert hashlib.sha256((json.dumps(native, indent=2) + '\n').encode()).hexdigest() == x['consumer_candidate_audit_sha256']
    assert proof['actual_compiled_source_trees'] == x['preferred_source_trees']
    assert proof['consumer'] == x['consumer'] and all(proof['checks'].values())
    assert proof['witness']['native_audit_sha256_bound_to_candidate'] == x['consumer_candidate_audit_sha256']
    assert x['dll_count'] == x['consumer']['dll_count'] == len(x['consumer']['worker']['loaded_dlls']) == 21
    assert {d['pages'] for d in x['consumer']['documents'].values()} == {1, 4}
    assert all({f['weight'] for f in d['fonts']} == {400, 700} for d in x['consumer']['documents'].values())


def test_completed_private_build_does_not_relabel_prior_witness_or_close_release_gates():
    proof = json.loads((DEPS / 'pdf-noticed-archive-build-proof.json').read_text())
    packaging = proof['source_package_receipt_at_packaging_time']
    assert proof['new_native_build_from_this_noticed_envelope_proven'] is True
    assert packaging['new_native_build_from_this_envelope_proven'] is False
    assert packaging['prior_build_witness_applies_to_archive_sources'] is False
    assert packaging['native_build_witness_sha256'] == 'eb275260c533e1572a3a8a31fc445e8af92353aaa88e6255da61c9b8127b464b'
    assert proof['release_authorized'] is proof['ordinary_runtime_payload_changed'] is proof['application_license_changed'] is False
    assert proof['legal_notice_completeness_approved'] is proof['modified_build_is_distribution_candidate'] is False
    assert packaging['recipient_source_delivery'] is False and packaging['licensed_files'] == 14
    policy = json.loads((DEPS / 'pdf-runtime-license-policy.json').read_text())
    assert len(policy['open_gates']) == 6
    assert all(g.get('progress', {}).get('gate_closed', False) is False for g in policy['open_gates'])
