# Engineering Guard Factory Dashboard

## Purpose
The Engineering Guard Factory Dashboard is a real-time orchestration UI for the software factory, which automates a feature through spec → build → parallel review (security, UX, UI, code) → approval pipeline. Engineers working on code reviews and verification use it to track job progress, understand current status, and access detailed review findings.

## Users
**Primary:** Engineers conducting code reviews and verification within the factory pipeline. They need to:
- See which jobs need their attention at a glance
- Understand each job's current stage and progress through the pipeline
- Quickly jump to review findings and test results without friction
- Monitor overall factory health and pending human decisions

## The Factory Pipeline
Jobs flow through these stages, and some stages repeat in rounds:
1. **Spec** - Initial specification written
2. **Spec Review** - Human approves the specification (human stage)
3. **Build** - Code implementation
4. **Test Audit** - Behavioral tests run and audited (per-round)
5. **Review** - Parallel reviews: security, UX, UI, code (per-round)
6. **STRIDE** - Security threat modeling (once per job, after reviews finish)
7. **Approver** - Final approval
8. **Needs Human** - Requires human decision/escalation (human stage)
9. **Abandoned** - Job discarded or rejected

Jobs can loop back to Build if reviews fail (max 2 rounds). Human stages and escalations need immediate attention.

## Current State (What Works)
- Two-dashboard system: job-centric (`dashboard.html`) and centralized repo view (`central-dashboard.html`)
- Real-time polling from JSON/API
- Kanban-style layout showing pipeline stages
- Click-to-inspect job details with file viewer
- Basic markdown rendering for review findings
- Color-coded verdict chips (PASS/CHANGES/N/A/pending)
- Human-attention highlighting on cards requiring decisions

## Problems to Solve
1. **Visual overload**: Too many cards, stages, and status indicators at once; hard to prioritize
2. **Navigation friction**: Must click cards to see details; markdown content not scannable in-line
3. **Status clarity**: Unclear how to quickly assess a job's readiness or blockers
4. **Aesthetic age**: Utilitarian design feels dated; lacks hierarchy and breathing room
5. **Information density**: Small text, tight spacing, minimal contrast between states
6. **Context loss**: Switching between tabs/jobs loses scroll position and local context

## Success Criteria
- **At-a-glance understanding**: User sees factory health, pending decisions, critical blockers within 2 seconds
- **Reduced clicks**: Core information (stage, status, warnings) visible without opening modal
- **Better scanability**: Clear visual hierarchy guides eye to important items
- **Professional polish**: Modern, spacious UI with intentional typography and spacing
- **Accessible markdown**: Review findings readable and well-formatted in modal view
- **Mobile-friendly**: Works at tablet and mobile sizes, not just desktop

## Design Constraints & Anchors
- **Single HTML file**: No build step, no dependencies (inline JS/CSS only)
- **Lightweight JS**: Keep existing polling and rendering patterns
- **Data model**: Preserve job shape (id, title, stage, reviews, test_audit, stride, warnings, files, etc.)
- **Color palette**: Reuse semantic colors (pass green, changes amber, pending gray, human purple, danger red)
- **Async markdown**: Files still fetched on-demand when user opens detail view

## Scope: Redesign Dashboard(s)
We're redesigning both `dashboard.html` (job-centric) and `central-dashboard.html` (repo-grouped). May consolidate into one if it serves both use cases better. Keep the factory state and API intact; only the UI changes.
