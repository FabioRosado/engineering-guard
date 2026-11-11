# Security companion: AI, LLM and agent code

Load this only when a language model takes part in a trust decision: prompts built from untrusted input, tool or function calling, MCP clients and servers, agent memory, retrieval pipelines, or code that acts on model output. This repository ships skills, prompts and hooks, so it applies here too. It supports `../SKILL.md`; the evidence bar (§5) and severity rules (§7) there still apply.

Ideas adapted, in our own words, from `cloudflare/security-audit-skill` (MIT licence, Copyright (c) 2025-2026 Cloudflare, Inc.).

## Core discipline

- The flow to trace is untrusted content, then model or memory, then a capability or sink. Ordinary boundaries (transport, access control, queries, filesystem, output encoding) still apply on each hop.
- Showing that a model can be talked into something is not a finding. The report needs a failure in code: text lands in a different principal's context, acts with authority the requester does not hold, exposes data the requester may not read, or reaches a sink the requester cannot use directly.
- Model output, memory, retrieved text, tool descriptions and MCP replies are all untrusted input. Find the line of code that lets any of them confer authority.
- A guardrail written in a prompt is not a control. Count only deterministic checks: resource-level authorization, isolation, binding of an action to what the user approved, and narrowly scoped credentials.
- Name the attacker, the affected principal, the identity that executes, the resource, the exact action and the visible result. A user who intentionally asks for something their own account may do is not a delegation defect just because a model ran it.

## Where to look

**Context and memory.** Who can write each retrieved source or memory record, and whose session reads it? Confirm tenant and permission filters sit inside the query and every cache key, not only on the stored object. Check whether prompt assembly lets untrusted text pose as a system message, earlier turn or tool result.

**Tool calls.** Treat a tool schema as input parsing. Follow each model-supplied argument into SQL, shell, file, URL fetch or privileged API, and re-validate where it selects a resource. Check that a service credential is paired with a per-request check of the requesting user. Compare the schema with what the handler really accepts (aliases, extra fields, coercions).

**Approval and action binding.** If a user approves one action, can arguments, target or requester change before it runs? Can text an attacker wrote trigger an effect using the victim's own legitimate permissions, though the victim never requested it? Check retries, resumed sessions and batches.

**Agents, MCP and loops.** A delegated task should get the least authority, not the whole session. Routing by tool name or server name that a peer can choose is a confusion risk. Peer metadata can guide a model but cannot grant capability. A bounded request that can queue unbounded spend or sends needs a per-request budget.

**Output and disclosure.** Model output reaching HTML, Markdown, a URL or a command needs the sink's own encoding. Revealing generic instructions is not a finding; revealing another user's data or a credential-bearing value is.

## Validation rules

Before reporting anything here:

1. State which boundary was crossed and what happened: the attacker, who or what was affected, the identity that executed, the target, and the unauthorized or unrequested action or disclosure.
2. For confused-deputy claims, show the handler lacks a requester-and-resource check and the attacker could not do this normally. For action binding, show attacker content caused an action the principal did not ask for or approve.
3. For memory or retrieval claims, cite the attacker's write and the separate later read or decision by another principal; a stored record with no consumer is not enough.
4. For approval binding, compare the approved object with the one the handler runs.
5. If the result depends on a provider, model, deployment or identity behaviour you cannot observe, report `needs_validation` with that exact fact and a safe local or owner check. Never give it a severity.
