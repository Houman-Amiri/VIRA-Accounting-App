"""Integrity of the recorded Phase 1 witness, NOT a new native pytest build."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_authenticated_phase1_source_bootstrap_witness(tmp_path):
    raw = (ROOT/'docs/dependencies/pdf-bootstrap-source-http-evidence.json').read_bytes()
    p = json.loads((ROOT/'docs/dependencies/pdf-bootstrap-source-http-proof.json').read_text())
    assert p['run_id'] == 39388243191
    assert p['head_sha'] == '88180ea9ad6027c27533b9bd87187ec63c0a3ed3'
    assert p['run_conclusion'] == p['job_conclusion'] == 'success'
    assert len(p['jobs']) == 2 and all(j['conclusion'] == 'success' for j in p['jobs'])
    assert p['job_id'] == 118514621733 and p['artifact_metadata']['id'] == 12250199759
    assert p['authenticated_annotation_parts'] == 10
    assert len(raw) == p['witness_bytes'] == 119672
    assert hashlib.sha256(raw).hexdigest() == p['witness_sha256'] == '3c134b431fe977f2937e84b6139ec3daa19517c407cf5a6de904bdbeb2043a5d'
    assert p['artifact_zip_independently_downloaded_or_hashed'] is False
    x = json.loads(raw)
    audit = tmp_path/'audit.json'
    audit.write_bytes((json.dumps(x['native_audit'], indent=2)+'\n').encode('utf-8'))
    assert hashlib.sha256(audit.read_bytes()).hexdigest() == p['native_audit_sha256']
    for name, case in x['cases'].items():
        folder = tmp_path/name
        folder.mkdir()
        for key, filename in [('launcher','launcher-proof.json'), ('http_pdf','http-bundled-proof.json'),
                              ('inventory','runtime-inventory.json')]:
            (folder/filename).write_text(json.dumps(case[key]), encoding='utf-8')
    (tmp_path/'negative-controls.json').write_text(json.dumps(x['negative_controls']), encoding='utf-8')
    spec = importlib.util.spec_from_file_location('phase1_source_record',ROOT/'scripts/pdf_bootstrap_sdk_bind.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.bind(tmp_path, audit) == x
