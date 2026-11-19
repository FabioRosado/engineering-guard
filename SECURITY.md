# Security policy

## Reporting a security concern

Use the [Security concern issue form](https://github.com/FabioRosado/engineering-guard/issues/new?template=security_concern.md). If it does not load, open a [new issue](https://github.com/FabioRosado/engineering-guard/issues/new) and title it `Security concern: <affected area>`.

**Issues are public.** Do not put exploit details, proof-of-concept code, credentials, tokens or other secrets in the issue. Name only the affected area (for example "the factory dashboard server" or "the policy hook") and ask for a way to discuss it. Do not use the bug report form, which asks for logs and steps. Details can be shared once a way to discuss them has been agreed.

This is a personal project and makes no commitment on response or fix times.

## Supported versions

Only the latest `main` is covered. Older commits and forks are not.

## What is in scope

- **Factory dashboard** (`npm run dashboard`): it is local-only and binds to `127.0.0.1`. It is not hardened for network exposure, so do not expose it to a network or the internet. Specs and security reviews shown in it can describe unfixed vulnerabilities, which is why it should stay local.
- **Skills, policies and the hook** are advisory. They deliver guidance to agents and are not a security boundary; the hook never approves a write and can be bypassed (see the README, "Policy delivery").
- **`demo/` fixtures** are deliberately defective or vulnerable (for example `demo/security/vulnerable` and `demo/src`). They exist to demonstrate the skills. Findings in them are not vulnerabilities in Engineering Guard.

`policies/security-policy.md` is guidance for agents performing security reviews. It is not a vulnerability-reporting policy.
