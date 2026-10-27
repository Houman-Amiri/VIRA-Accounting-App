# Historical Phase2 implementation, NOT current-runtime evidence

Phase3 explicitly extends two runtime modules and their Windows workflow. These
three files preserve the OLD LF-canonical bytes from commit
764b3b6cef9b93efd17f93ad7bacdb7b38f10192 (identical to the authenticated Phase2
proof pins). They are documentation-only and never imported/executed by CI or
the application. Historical hashes/witnesses have NOT been rewritten to pretend
that the old Windows run exercised the new contract. The other11 frozen files
remain checked against current bytes. Current Phase3 behavior needs fresh tests
and a fresh Windows witness, plus unchanged legacy-mode regression controls.

{
  "backend/app/desktop_entry.py": {
    "archive": "desktop_entry.py",
    "git_blob_sha256": "343666eb2cda73f8215bef5740f59f70b9131971008d0d11043c4befefc85cb6"
  },
  ".github/workflows/pdf-desktop-source.yml": {
    "archive": "pdf-desktop-source.yml",
    "git_blob_sha256": "504139fd70cd69e4dbfc210f99f80ad7b21fdb009420ed0fe610350b53569276"
  },
  "backend/app/private_pdf_bootstrap.py": {
    "archive": "private_pdf_bootstrap.py",
    "git_blob_sha256": "da6093cc7236223e17ceca79ccc58e695215a9b31a76b8f5a055f6ce29dba748"
  },
  "backend/app/config.py": {
    "archive": "config.py",
    "git_blob_sha256": "8f3fe3f1cc676a8bc90a5a38502e1d1058168bd4875bb6aa10dd5af9e34ebc57",
    "extended_by": "v1.0.11 bakes the update verification key into the packaged payload"
  },
  "scripts/stage_app_payload.ps1": {
    "archive": "stage_app_payload.ps1",
    "git_blob_sha256": "964c6b620799f6be881ff026070917b8586ce8a41f1a48c2b80e25e15a09cff9",
    "extended_by": "v1.0.11 stages the baked update verification key before the install manifest"
  }
}
