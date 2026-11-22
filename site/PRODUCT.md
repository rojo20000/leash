# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary audience: the Tidal Byte 2026 hackathon judges, watching the team present this site live and checking its claims and limitations.

## Product Purpose

Leash is a runtime security gateway for clinical AI agents. Every tool call an agent makes passes through Leash, which checks it against a role policy, strips patient data down to what the task needs, scores it with ML, writes it to a tamper-evident audit log, and allows it, blocks it or holds it for a human.

Success for this site: an hour after the demo, a judge remembers that one hidden sentence in a referral document would have leaked a full patient record, and that Leash stopped that exact call.

## Positioning

Leash enforces safety with hard rules at the tool-call boundary. Model output can only add caution, never remove it, and nothing a model returns can unblock a call.

## Operating Context

The team presents the site live on a projector in a bright room, scrolling scene by scene and talking over each feature. It must also work as a static, offline site at 1440x900 and 390 px wide.

## Capabilities and Constraints

- Every claim, number and reason code comes from `src/content.ts`, transcribed from the repository's README, docs, metrics and scripted demo run.
- All patient data is synthetic.
- The README's limitations are stated plainly in the closing scene.
- The built site makes no requests to any outside host.

## Brand Commitments

Product name: Leash. Tagline: "A runtime security gateway for clinical AI agents." The user requires a medical palette of whites, blacks, reds and blues, with shadows and fine detail, and strong animated or zoomed emphasis on whatever is being highlighted.

## Evidence on Hand

- Scripted run: `demo/output/scripted_run.txt` (17 allowed, 3 blocked, 0 escalated).
- Metrics: `metrics/results.json`.
- Dashboard capture: `docs/img/approval-queue.png`, from a separate run on synthetic data.
- No customers, deployments, testimonials or clinical validation exist. Do not imply any.

## Product Principles

1. Show the attack being stopped, not a description of security.
2. Hard rules decide, and AI judgment only adds caution.
3. Every number is measured and traceable to a source file.
4. State the limitations as plainly as the wins.

## Accessibility & Inclusion

Honor `prefers-reduced-motion`. Never use color as the only signal for a verdict. Text must stay legible on a projector in a bright room.
