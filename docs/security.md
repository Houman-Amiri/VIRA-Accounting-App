# V.I.R.A Security Architecture (Phase 5)

این سند معماری امنیتی ویرا را پس از فاز ۵ (یکپارچه‌سازی، احراز هویت و امنیت) شرح
می‌دهد. تهدید مدل: اپ دسکتاپ ویندوز، تک‌کاربره/چندکاربره داخلی، داده‌های مالی حساس.

## 1. Authentication & Sessions

- **Argon2id** (pwdlib) for password hashing; minimum 8 characters.
- **Session cookies**: HttpOnly + SameSite=Lax, 12-hour TTL, HMAC-signed
  (`itsdangerous`), `Secure` automatically in production. Sliding **silent
  refresh** via `POST /api/v1/auth/refresh` (cookie-only; the token is never
  exposed to JS). On 401 the SPA snapshots unsaved form drafts in memory →
  redirects to `/login` via TanStack Router and restores drafts afterwards.
- **CSRF**: double-submit (`vira_csrf` readable cookie + `X-CSRF-Token` header)
  on every mutation. API-key calls are exempt (custom header, no ambient auth).

## 2. MFA (TOTP) + Recovery Codes

- pyotp TOTP with QR provisioning URI; secret is **envelope-encrypted at rest**.
- **10 single-use recovery codes** shown exactly once at enrollment; only
  Argon2id hashes are stored (`mfa_recovery_codes`); `used_at` enforces
  single-use; regeneration replaces the set.

## 3. RBAC + Scoped API Keys + Sudo

| Role | Journal | Reports | Config/API-keys |
|------|---------|---------|-----------------|
| OWNER | full | full | full (sudo for high-risk) |
| BOOKKEEPER | create/post | read | none |
| AUDITOR | **read-only** (mutations 403) | read | none |
| INGEST_API (key) | create DRAFT + receipts only | none | none |

- Auditor read-only enforcement is global (every mutating router).
- `ingest_api` keys: `vira_sk_<prefix>_<secret>`, SHA-256 hashed, shown once,
  revocable; valid only for `POST /journal-entries` and `POST /receipts`.
- **Sudo step-up**: password or TOTP → HMAC token with **5-minute TTL**
  (`X-Sudo-Token`), required for: fiscal-period reopen, un-reconciling a
  completed session, unencrypted database-dump export, API-key CRUD.

## 4. Secrets & Envelope Encryption

- `APP_ENCRYPTION_KEY` — one or more Fernet (AES-128-CBC+HMAC, key=32B) keys,
  comma-separated; **first key encrypts**, all keys decrypt → zero-downtime
  rotation (`Envelope.rotate()` re-wraps under the primary key).
- Protected fields: bank/OB tokens, webhook secrets, IBANs, TOTP secrets
  (`external_credentials` table stores ciphertext + `key_id`).
- **Production boot refusal** (`strict_secrets`/`environment=production`):
  weak `SESSION_SECRET`, missing/invalid `APP_ENCRYPTION_KEY`, or wildcard
  `FRONTEND_ORIGIN` abort startup.

## 5. Transport, Headers, CORS, Rate Limits

- Bind default **127.0.0.1** (`start_vira.ps1`); CORS allowlist = exactly
  `FRONTEND_ORIGIN` with credentials.
- Security headers on every response: `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `CSP` (`frame-ancestors 'none'; object-src 'none'`), HSTS when HTTPS.
- Token-bucket rate limiting (in-process): login 5/min + **exponential lockout**,
  throttling for imports/upload/OCR endpoints.

## 6. Data Handling

- Uploads: magic-bytes sniffing (pdf/png/jpg/webp), EXIF stripping, receipts
  10 MB / statements 25 MB caps; content-addressed (sha256) storage; served
  authenticated with `nosniff` + `CSP: sandbox`.
- CSV export sanitizes formula injection (`=`, `+`, `-`, `@`, tab, CR → `'`
  prefix).
- Bank statements parsed with **defusedxml** (XXE hardening).
- Money: scaled integers only (×10 000 IRR; FX ×1e8) end-to-end.

## 7. External Calls & Webhooks

- All outbound HTTP via `httpx` + tenacity adapters (`services/external.py`):
  connect/read timeouts, exponential backoff + jitter, `Retry-After` respected.
- Inbound webhooks: `X-VIRA-Signature` (HMAC-SHA256, constant-time compare),
  ±5-minute timestamp freshness, `event_id` dedup in `webhook_events`.

## 8. Audit & Logging

- `security_audit_logs` — append-only (SQLite triggers reject UPDATE/DELETE):
  LOGIN_SUCCESS/FAILED/LOCKED_OUT, MFA_CHALLENGE_FAILED, SUDO_ELEVATION,
  PERIOD_UNLOCKED, BACKUP_EXPORTED, API_KEY_CREATED/REVOKED, WEBHOOK_*,
  RECOVERY_CODE_USED — each with UTC timestamp, actor, IP, user-agent.
- structlog pipeline with mandatory **redaction** (password, token,
  authorization, cookie, secret, IBAN-shaped strings, account_number…).

## 9. Windows Hardening

1. **Keep the default bind** `127.0.0.1:8787` — the app is per-machine. Never
   expose 0.0.0.0 directly.
2. **NTFS ACLs** on data:
   ```powershell
   icacls "$env:LOCALAPPDATA\VIRA" /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F" "SYSTEM:(OI)(CI)F"
   ```
3. **Firewall** (only if deliberately binding a LAN address):
   ```powershell
   New-NetFirewallRule -DisplayName VIRA -Direction Inbound -LocalPort 8787 -Protocol TCP -Action Allow -Profile Private
   ```
4. **Remote access** — prefer **Tailscale** (or any WireGuard VPN): install on
   both machines, then serve on the Tailscale IP only. No public port, no port
   forwarding; HTTPS end-to-end via Tailscale (MagicDNS + certificates).
5. Backups: `scripts/backup_vira.ps1` (scheduled task + passphrase-encrypted
   bundles); keep the passphrase OUTSIDE the repo (`-PassphraseFile`).

## 10. Key Rotation Runbook

1. `python -c "from app.security.envelope import generate_key; print(generate_key())"`
2. Set `APP_ENCRYPTION_KEY="<new>,<old>"` (new first) → restart →
   `Envelope.rotate()` over `external_credentials`/TOTP secrets.
3. Remove the old key after re-encryption; keep `SESSION_SECRET` unchanged
   (it invalidates sessions if rotated).

## 11. Verification

- `pytest backend/tests/test_security_phase5.py` — RBAC 403s, sudo gates,
  recovery single-use, lockout, webhook signature/freshness/dedup, envelope
  rotation, redaction, CSV injection, security headers, immutable audit rows.
- `bandit -r backend/app -ll` → 0 medium/high (defusedxml for XML).
- `pip-audit` → clean. `pnpm audit` → 1 high (braces DoS, **no upstream fix**;
  dev-only transitive via Tailwind — accepted and tracked).
