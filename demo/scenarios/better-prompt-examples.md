# Better Prompt scenarios

These are behavioral examples, not a required template. A useful transformation should preserve the request, add concrete engineering direction where justified, make uncertainty visible, and scale the brief to the work. The **Expected** and **Avoid** notes are review criteria: evaluate the generated instructions as a whole, not by checking for headings.

## Existing scenarios

### Vague bug report — Thorough

**Request:** “This endpoint is slow and the cache seems broken.”

**Prompt:**

> Find and fix why this endpoint is slow, and establish whether cache behavior contributes rather than assuming it does. Trace the request path, relevant cache lookup/key/invalidation behavior, and any existing timing or hit/miss evidence. Reproduce the slowdown or collect a comparable baseline with the repository's available checks before changing code. Make the smallest change supported by the evidence. Verify response correctness, including cache-key dimensions that matter to this endpoint, and compare performance under the same conditions afterward. No latency target was provided; report the measurements without inventing one and identify any decision that blocks a safe fix.

**Expected:** Treat cache failure as a hypothesis; establish a baseline; connect the fix to a demonstrated cause; verify correctness as well as speed.

**Avoid:** Claiming the cache is broken, selecting a cache design before inspection, or inventing a latency target.

### Feature request — Thorough

**Request:** “I need to add authentication to this service.”

**Prompt:**

> Add authentication to this service. First trace its request entry points, existing identity/session handling, protected operations, authorization boundaries, error conventions, and relevant tests. Follow established project or product requirements if present; do not choose a token, session, identity provider, or new dependency without evidence. If an unresolved product or security decision materially changes the design, ask me after inspecting the existing flow; otherwise state the established assumption and continue with a focused implementation. Verify the real request path for authenticated access, unauthenticated denial, and authorization of protected resources, and check that failures do not expose credentials or sensitive details. Report the design used, checks run, and any remaining security boundary that was outside the change.

**Expected:** Investigate existing identity and authorization; keep authentication distinct from resource authorization; preserve established requirements; ask only for material unresolved choices.

**Avoid:** Inventing a provider or token format, treating login as sufficient authorization, or stopping at a design proposal when implementation was requested and the needed decisions are established.

### Refactoring request — Quick

**Request:** “Can you clean up this component? It's getting complicated.”

**Prompt:**

> Simplify the relevant component where its complexity makes it harder to understand or change. Inspect its callers and current behavior, keep the refactor focused, and preserve its observable behavior. Update or run the smallest relevant existing checks, then explain what became simpler.

**Expected:** Keep it short, identify behavior preservation and a meaningful check.

**Avoid:** Turning a vague cleanup request into a broad redesign, adding abstractions without a demonstrated need, or demanding a new test suite.

### Infrastructure or architecture question — Thorough

**Request:** “Our worker backlog keeps growing during peaks. Should we move jobs to a queue?”

**Prompt:**

> Investigate why the worker backlog grows during peak load and whether moving jobs to a queue would address the cause. Inspect the current job lifecycle, arrival and processing evidence, concurrency and bottlenecks, retry/idempotency behavior, and operational constraints that are available. Compare only viable options, including simpler changes if evidence supports them, and explain the trade-offs and failure modes. Recommend a direction with the evidence and measurements still needed to choose confidently. This request asks for analysis: do not change infrastructure or select a queue product.

**Expected:** Investigate capacity and job semantics; make a recommendation tied to evidence; preserve the request's analysis-only scope.

**Avoid:** Assuming a queue is the answer, inventing throughput or availability targets, or implementing an infrastructure change.

### Existing prompt improvement — Thorough

**Request:** “Add cache to search. Make it fast. Tests.”

**Prompt:**

> Improve search performance while preserving search results and the existing freshness contract. Caching is part of the requested solution: inspect the search path, current cache conventions, result-affecting inputs, and invalidation behavior, then measure the bottleneck and baseline before choosing a focused cache design. If the repository establishes a freshness contract, preserve it; if not, identify the choice that materially affects behavior and ask me rather than inventing a duration. Add behavior coverage for cache hits, misses, relevant input variation, and invalidation at the actual boundary the project uses. Run the relevant checks and report comparable before/after measurements without inventing a target.

**Expected:** Preserve the explicit caching request; clarify freshness only if it is not established; specify useful cache behavior and comparable measurements.

**Avoid:** Silently replacing caching with another optimization, fabricating a TTL or performance target, or testing only mocked cache calls.

### Simple request — Quick

**Request:** “Change the button label from Submit to Save.”

**Prompt:**

> Change the relevant button label from “Submit” to “Save”, preserve its current behavior, and run the most relevant existing check.

**Expected:** Keep a local copy edit local and verification proportional.

**Avoid:** Adding a design investigation, broad accessibility audit, or unrelated component refactor without evidence that the requested change needs it.

## Additional judgment scenarios

### Bug with an assumed root cause — Thorough

**Request:** “The JSON parser is leaking memory. Add memoization to stop it.”

**Prompt:**

> Investigate and fix the reported memory growth. Treat both “the JSON parser is leaking” and “memoization will stop it” as hypotheses: reproduce the growth where practical, inspect object lifetimes and allocation evidence along the parse/request path, and establish whether memoization would reduce retained memory or make it worse. Preserve parsing behavior and resource limits. If evidence confirms memoization is appropriate, implement the smallest focused change; if the suspected cause is wrong, show the evidence and ask before replacing the requested approach with a materially different fix. Verify the original reproduction and representative parsing behavior, then report what was measured and what remains uncertain.

**Expected:** Test the causal claim and proposed remedy; retain the memory-growth objective; ask before a materially different solution.

**Avoid:** Adding memoization automatically, declaring an unobserved leak confirmed, or inventing a memory budget.

### Explicit architecture decision — Thorough

**Request:** “Add a filter to admin reports. Keep output server-rendered HTML; don't introduce a SPA, JSON API or new frontend framework.”

**Prompt:**

> Add the requested admin-report filter while keeping the output server-rendered HTML. Treat the prohibition on a SPA, JSON API, and new frontend framework as approved constraints. Inspect the existing report route, query/filter conventions, authorization, rendering path, and tests; implement the filter within those boundaries and preserve current report behavior when no filter is selected. Verify the rendered result for matching and non-matching filters, invalid or empty input according to existing conventions, and access control. If the existing architecture cannot satisfy the request safely, explain the evidence and ask before changing the approved boundary.

**Expected:** Preserve the explicit server-rendered decision, use observed route conventions, and verify filtered and unchanged behavior.

**Avoid:** Recasting the constraint as a tentative preference, introducing a client framework, or silently moving filtering into a new API.

### Proposed unnecessary complexity — Thorough

**Request:** “For a tiny internal status page with one value, I was thinking Redis, an event-driven invalidation service and a generic cache-provider abstraction so we can cache it.”

**Prompt:**

> Assess the need and smallest suitable way to cache the status value. Inspect where it is read, how expensive or frequent that read is, how quickly the value must reflect changes, and what cache or configuration conventions already exist. Treat Redis, event-driven invalidation, and a generic provider abstraction as proposed ideas, not approved requirements; compare their operational and maintenance cost with the simplest approach that meets the observed need. Do not add a layer without evidence it solves a real constraint. If caching or a particular technology is a firm product requirement rather than a suggestion, confirm that before discarding it. Report the evidence, recommendation, and the focused checks needed; do not implement unless asked.

**Expected:** Distinguish the caching outcome from tentative design ideas, collect evidence, and avoid needless infrastructure while retaining a human decision if the proposal was actually mandatory.

**Avoid:** Treating all named technologies as approved, or silently changing a firm requirement into “do nothing”.

### Backend feature with integration boundaries — Thorough

**Request:** “Let signed-in users export their invoices as CSV from the billing page. Use existing invoice access rules and account filters; if we already have an export job path, integrate with it. Keep it synchronous unless current limits make that unsafe. No email delivery; preserve tenant boundaries.”

**Prompt:**

> Add CSV invoice export to the billing page for signed-in users. Trace the page action through its route/controller, invoice query, account scoping, authorization checks, CSV/download conventions, and any existing export-job path before choosing the integration. Preserve tenant boundaries and the stated synchronous behavior unless repository evidence shows that it is unsafe; if changing that behavior materially, explain why and ask first. Reuse existing serialization and error conventions rather than adding a parallel export framework. Verify the real route or nearest meaningful integration boundary for an authorized account, denial or isolation from another account's invoices, empty results, and CSV values containing delimiters, quotes, or newlines. Exercise the existing job path only if inspection confirms one is relevant. Run focused checks and report the affected integration, remaining limits, and any scale or operational assumptions.

**Expected:** Follow the actual UI-to-data path; preserve authorization, tenant scoping, synchronous/no-email constraints; test integration and CSV edge cases.

**Avoid:** Inventing an export-job system, broadening delivery to email, trusting only frontend filtering, or claiming tenant safety from isolated serializer tests.

### Tightly scoped bug fix — Quick

**Request:** “The X on a toast doesn't dismiss it after the next render. Fix that only; don't refactor the toast component or change its timeout/action behavior.”

**Prompt:**

> Reproduce why clicking the toast’s X fails to keep that toast dismissed after the next render, then fix that state update only. Preserve timeout and action behavior and do not refactor the component. Add or update a focused regression check for dismissal across the rerender, and run the relevant existing check.

**Expected:** Keep the scope on the dismissal regression and preserve explicitly named behavior.

**Avoid:** General toast cleanup, changing timeout/action semantics, or expanding the work into a component redesign.

### Missing product decision — clarify before prompting

**Request:** “Add account deletion. Keep the data for a while in case users return.”

**Expected behavior:** Check whether repository policy defines retention. If not, ask the developer what retention behavior is intended before producing an actionable implementation prompt. The duration affects product and privacy behavior, and the next agent should not choose it without approval.

**Avoid:** Inventing a retention duration or hiding the unresolved decision in instructions for the next agent.
