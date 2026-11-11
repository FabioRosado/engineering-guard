# Security companion: client-side and browser code

Load this only when the change touches browser-side trust decisions: rendering untrusted content, DOM sinks, `postMessage`, service workers, browser storage, cross-origin requests, or client-side navigation. It supports `../SKILL.md`; the evidence bar (§5) and severity rules (§7) there still apply.

Ideas adapted, in our own words, from `cloudflare/security-audit-skill` (MIT licence, Copyright (c) 2025-2026 Cloudflare, Inc.).

## Core discipline

- A client-side finding needs a source an attacker controls and a sink that runs or discloses. Name both and show the data travelling between them.
- The victim must be someone else: another user's session, another origin, or storage shared across accounts. Injecting into your own page, or reading your own data, is not a finding.
- Treat framework escaping, the same-origin policy, CSP, cross-origin isolation headers, worker scope and implicit `noopener` as genuine defences. Verify what they do on this path before you rate impact.
- Storage and caches belong to the origin, not the login, and can survive a logout. For each record ask who wrote it, who reads it, and what removes it when the account changes.

## Where to look

**DOM XSS.** Trace URL parts, the referrer, `window.name`, message payloads and stored values into `innerHTML`, `document.write`, string-evaluating calls, executable URLs, or a framework's raw-HTML escape hatch. Ordinary escaped interpolation is safe.

**DOM clobbering and prototype pollution.** Clobbering needs markup that keeps an attacker's `id` or `name` plus code that trusts the shadowed value. Pollution needs a recursive write from an attacker key plus a reachable gadget that changes a decision; pollution with no gadget is not enough.

**Messaging and origins.** A `message` handler that acts on `event.data` without an exact origin match (and `event.source` where frames share an origin) is the risk. Substring, prefix and loose regex checks are not origin checks. Sending sensitive data to `*` is the mirror problem. Treat WebSocket upgrades and credentialed CORS the same way: the question is whether an untrusted origin can ride the victim's cookies to read data or change state.

**Service workers and storage.** Look for attacker-influenced script URLs or imports, over-broad scope, and caches that serve one account's personalised response to another. Storing a token is not a finding by itself; you need a less-trusted reader, or use after revocation.

**Cross-site leaks and UI redress.** A leak needs a concrete secret predicate (does this private object exist?) that an attacker page can observe. A clickjackable state-changing action matters; missing frame headers on read-only pages are hardening. A client-controlled redirect matters only when no scheme or destination policy constrains it and it reaches a victim; a constrained one is a hardening note.

## Validation rules

Before reporting anything here:

1. Record the source, the sink, the policy that ought to stop the path, whose origin or session is hit, and what an attacker gains.
2. For pollution, show the recursive write and the gadget. For clobbering, show the markup survives and the value is used.
3. For workers and storage, show an attacker-controlled write that a different account, tenant or post-revocation state later consumes.
4. For messaging, CORS, WebSocket and leaks, quote the origin check, name the protected state exposed, and confirm CSP, isolation headers, cookies and `SameSite` do not already close the path.
5. If the answer depends on a deployed header, extension permission or browser version you cannot see, report `needs_validation` with that exact fact and a safe owner check. Never give it a severity.
