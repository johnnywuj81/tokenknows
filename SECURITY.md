# Security Policy

TokenKnows is a local-first product — privacy and data-residency are core features, and we treat security reports accordingly.

## Supported versions

| Version | Supported |
|---|---|
| latest `0.x` release / `main` | ✅ |
| older tags | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

1. Preferred: GitHub **Private Vulnerability Reporting** — [Security → Report a vulnerability](https://github.com/johnnywuj81/tokenknows/security/advisories/new)
2. Fallback: email **john.wuj@outlook.com** with subject `[SECURITY] tokenknows`

You can expect an acknowledgement within **7 days**. Please include reproduction steps and affected component (api / web / collector plugin / Claude plugin / Codex plugin / VS Code extension).

## Scope notes

- The backend is designed to run on localhost / private networks. Reports assuming a hostile public-internet deployment of the dev server are out of scope.
- LLM egress behavior (the three-layer gate) is in scope — anything that causes data to leave the machine while the gates are off is a vulnerability.
