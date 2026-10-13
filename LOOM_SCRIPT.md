# Loom Script (5-8 minutes)

> Synthetic data. Demonstrates the method, not Hedge's actual performance. Say this in the first ten seconds and keep the dashboard banner visible.

## Do these yourself before recording
- [ ] Run `make setup && make all && make test`; confirm everything is green on your machine.
- [ ] Open `make dashboard` and click through every view once so nothing loads for the first time on camera.
- [ ] Re-read the numbers you will quote against the dashboard; they come from a synthetic dataset. Never present them as Hedge's.
- [ ] Decide what you will NOT claim: no real conversion rates, customers, carriers, funding or headcount for Hedge.
- [ ] Keep the "Assumptions to validate" list from `STRATEGY_MEMO.md` handy for the close.

## Timeline

| Time | Screen / click | Say |
|---|---|---|
| 0:00-0:30 | Dashboard, banner visible | "This is a growth-ops prototype for an AI-native specialty wholesaler. Everything is synthetic: it demonstrates how I would measure and run the broker funnel, not Hedge's real performance." |
| 0:30-1:30 | `src/bgos/funnel.py`, then the Monday Morning view | "I encoded the funnel as code: lead, ICP, engaged, first complete submission, quoted, bound, repeat. In the synthetic baseline 1,500 leads become 209 bound agencies (13.9%). Stages are strictly nested so the funnel can only taper." |
| 1:30-2:30 | `outputs/data_quality_report.md` | "The raw data is deliberately dirty: duplicates, mixed source labels, impossible dates. Every defect is injected and counted, and cleaning reconciles to the exact injected counts. Tiny sources that show 100% are suppressed, not celebrated." |
| 2:30-3:30 | Ranked Accounts view | "The fit score is a transparent weighted sum, and every row says why. 83 Tier 1 accounts, 193 dormant ones to win back. The tier ordering check is a plumbing test: the generator makes conversion depend on fit, so I do not call it predictive." |
| 3:30-4:30 | Weekly Growth Review, then Source Quality | "North star is qualified submissions from active agencies. Source quality is judged on bind, not lead count: linkedin gives the volume but partner binds 2.7x better. Activation is 39% within 14 days, the first gap I would attack." |
| 4:30-5:30 | Experiments view | "Three experiments with pre-registered rules. ICP targeting: SHIP on a simulated +37.5% lift. Onboarding looks positive but is underpowered, so the framework says INCONCLUSIVE, not ship. Say plainly that this is one simulated draw: across 40 seeds A ships in 32. Reactivation is a planted null and returns INCONCLUSIVE. These are simulated results that demonstrate the method." |
| 5:30-6:30 | `outputs/ai_demo.md` | "The AI layer is human-in-the-loop: research, a deterministic submission-quality score, next-best-action, and email first lines. Drafts always require review and there is no send function anywhere in the code." |
| 6:30-7:30 | `STRATEGY_MEMO.md` | "First 30 days: establish truth. Join the real CRM and submission data, validate these assumptions about Hedge, lock definitions, baseline every metric. Days 31-60 ship the three experiments; days 61-90 prove lift." |

## Close
"I would start by validating the assumptions on the last page against real data, because everything here is only as good as those definitions."
