# Security companion: supply chain, CI and release

Load this only when the change touches dependency manifests or lockfiles, CI workflows, build or release scripts, install hooks, or plugin and updater code. It supports `../SKILL.md`; the evidence bar (§5) and severity rules (§7) there still apply.

Ideas adapted, in our own words, from `cloudflare/security-audit-skill` (MIT licence, Copyright (c) 2025-2026 Cloudflare, Inc.).

## Core discipline

- An unpinned or outdated dependency is only a lead. The finding is the path: who can change what gets resolved, which build picks it up, and what code runs or ships as a result.
- Follow integrity across every handoff: source, resolved inputs, build worker, artifact, test result, signature or attestation, promotion, and the consumer that installs it.
- Read CI configuration as access-control code: which event starts it, whose code it executes, which secrets and tokens it holds, and what it may publish or change.
- A checksum downloaded from the same place as the artifact adds no independent assurance. Find the root of trust and the behaviour when verification fails.

## Where to look

**Dependencies and build inputs.** Look for resolver settings that can pick an unintended registry or namespace, manifests without lockfile or hash use, floating tags, branches, actions or container images, downloaded tools, and generated or vendored content that skips the review given to source. A reproducible build is not thereby an authentic one: you need a lower-trust writer and a route into trusted output. Check that build contexts do not sweep secrets or private files into a package.

**CI and automation.** Look for contributor-controlled code (pull request, fork, comment, dependency bump) running with secrets, write tokens or a trusted runner. Compare the trigger, the checked-out ref, any approval gate and the permission scope. Branch names, commit messages and issue text placed in a shell command or expression are injection sinks. A cache or artifact that a lower-trust job fills and a higher-trust job restores is a trust crossing. Broad token permissions alone are hardening; you need a reachable privileged action.

**Release and update.** Check that testing, signing and publishing refer to the same immutable digest, not a mutable tag or filename. Check that a consumer verifies who signed and for what (workflow, branch, product, platform, channel, expiry), not only that a signature exists, and that failure, revocation and rollback fail closed.

**Plugins and hooks.** Installing a plugin the user chose to install is intended same-user authority, not a boundary. The risk is a package gaining more authority than it declared, another publisher's identity being replaceable, or install and update code running before authenticity checks.

## Validation rules

Before reporting anything here:

1. Identify the lower-trust actor, what they control (source, cache, artifact or metadata), the trusted job or updater that takes it in, and the outcome: unauthorized publication, injected code, leaked secret or privileged execution.
2. Follow the artifact's identity through the weak handoff; the mutable name or unbound digest has to arrive at a real consumer.
3. Check the defaults of the package manager, repository host, registry and signing tool at the pinned version. Do not assume either way about hosted settings you cannot see, such as branch protection, runner policy or registry rules.
4. Keep any local check small and safe: a harmless fixture repository, a dummy credential marker, a local registry, no real publish.
5. If the answer depends on a hosted-runner, registry, signing-service or promotion fact you cannot observe, report `needs_validation` with that exact fact and a safe owner check. Never give it a severity.
