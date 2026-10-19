"""Private SDK QA entry using APPLICATION-owned activation, not installed launcher.

No native setup here. Fixed app module/worker only, never a supplied code callback.
Bootstrap workspace is fresh per process; HTTP business state restarts separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('app-root', 'state-root', 'bootstrap-state-root', 'contexts', 'out-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--payload-manifest-sha256', required=True)
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--reuse-state', action='store_true')
    args = parser.parse_args()
    root = args.app_root.resolve(strict=True)
    if Path(__file__).resolve() != root/'scripts/pdf_bootstrap_http_entry.py':
        raise ValueError('Entry must be the private payload copy')
    module = root/'app/private_pdf_bootstrap.py'
    # Authenticate the app-owned executable module BEFORE runpy executes it.
    # Remaining complete-payload/process validation belongs to that module.
    raw = (root/'install_manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.payload_manifest_sha256:
        raise ValueError('Independent manifest digest mismatch before app module')
    manifest = json.loads(raw.decode('utf-8-sig'))
    entries = [e for e in manifest['files'] if e['path'] == 'app/private_pdf_bootstrap.py']
    if (len(entries) != 1 or module.stat().st_size != entries[0]['size']
            or hashlib.sha256(module.read_bytes()).hexdigest() != entries[0]['sha256']):
        raise ValueError('Application bootstrap code differs before execution')
    bootstrap = runpy.run_path(str(module))
    plan = bootstrap['PrivateBootstrapPlan'](root, args.bootstrap_state_root,
                                             args.payload_manifest_sha256, args.inventory_sha256)
    names = ('PATH', 'TEMP', 'TMP', 'WEASYPRINT_DLL_DIRECTORIES', 'FONTCONFIG_FILE', 'FONTCONFIG_PATH')
    before = {name: os.environ.get(name) for name in names}, sys.path[:], tempfile.tempdir
    old_argv = sys.argv[:]
    try:
        with bootstrap['activate_private_sdk'](plan) as active:
            if any(n == p or n.startswith(p+'.') for n in sys.modules for p in ('app', 'weasyprint', 'uvicorn')):
                raise ValueError('Application imported before private SDK entry')
            parent = {'schema': 1, 'role': 'PRIVATE_APP_BOOTSTRAP_SDK_HTTP_NOT_INSTALLED',
                      'pid': os.getpid(), 'no_site': sys.flags.no_site, 'isolated': sys.flags.isolated,
                      'utf8_mode': sys.flags.utf8_mode, 'windows_acp': active.windows_acp,
                      'payload_manifest_sha256': plan.manifest_sha256, 'inventory_sha256': plan.inventory_sha256,
                      'libffi': active.libffi, 'dll_count': active.dll_count,
                      'app_and_weasyprint_absent_before_entry': True, 'activation': asdict(active),
                      'target_mode': 'PRIVATE_APP_BOOTSTRAP_HTTP', 'source_audit_bound': False,
                      'source_audit_sha256': None, 'new_source_build_proven': False,
                      'ordinary_launcher_changed': False, 'release_authorized': False}
            worker = root/'scripts/pdf_private_http_probe.py'
            sys.argv = [str(worker), '--app-root', str(root), '--state-root', str(args.state_root),
                        '--contexts', str(args.contexts), '--out-dir', str(args.out_dir), '--app-owned-fonts']
            if args.reuse_state:
                sys.argv.append('--reuse-state')
            runpy.run_path(str(worker), run_name='__main__')
        after = {name: os.environ.get(name) for name in names}, sys.path[:], tempfile.tempdir
        if before != after or Path(active.bootstrap_temp).exists():
            raise ValueError('Application bootstrap settings/temp not restored')
        parent.update(target_completed=True, activation_scope_restored=True, bootstrap_temp_cleaned=True,
                      preflight_and_activation_module='app/private_pdf_bootstrap.py')
        (args.out_dir/'launcher-proof.json').write_text(json.dumps(parent, indent=2)+'\n', encoding='utf-8')
    finally:
        sys.argv[:] = old_argv


if __name__ == '__main__':
    main()
