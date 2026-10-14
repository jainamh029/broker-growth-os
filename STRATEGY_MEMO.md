# Strategy Memo: Broker Growth OS

> Synthetic data. Demonstrates the method, not Hedge's actual performance. Every number below comes from the generated synthetic outputs.

**Growth thesis.** A specialty wholesaler grows by turning more agencies into repeat submitters, not by sending more email. Our north star is weekly qualified submissions from active agencies; every lever is judged by downstream bind and repeat, never by sends or connections.

**Funnel.** Raw lead, ICP-qualified, Engaged, First submission (complete, underwriting-ready), Quoted, Bound, Repeat (another complete submission within 90 days of bind). Synthetic baseline: 3,000 leads, 2,282 ICP-qualified (76%), 1,695 engaged, 1,077 first submissions, 466 bound, 343 repeat. Counting only leads old enough to have converted, 21.7% reach a bind (15.5% raw, which understates it). The funnel is deliberately generous, and real rates will be lower.

**ICP.** Commercial lines with E&S or specialty exposure and at least 3 producers. A transparent fit score ranks every agency: 672 are active customers to expand, 405 dormant to reactivate, and among prospects 24 are Tier 1 (immediate outbound) and 706 Tier 2 (nurture). Scored 90 days before the as-of date using only data available then, Tier 1 prospects converted at 28% versus 1% for Tier 3. On synthetic data this checks plumbing, not real predictive power.

**Two highest-leverage gaps (synthetic baseline).**
1. Activation: only 38% of engaged agencies send a complete submission within 14 days. Each +10 points adds about 170 first submissions on this book.
2. Source mix: linkedin supplies 30% of leads but binds 11.7% of them, versus 35.6% for referral (3.1x). Moving 10% of lead volume to referral-quality sources adds roughly 72 bound agencies (back-of-envelope; assumes that channel scales).


**90-day plan.**
- Days 1-30, establish truth: join CRM and submission data at agency level, lock stage definitions, deduplicate, baseline every metric with minimum-n rules.
- Days 31-60, ship experiments: ICP-targeted outbound, submission-ready onboarding, and reactivation versus a holdout, each with a pre-registered effect size, sample size and decision rule.
- Days 61-90, prove lift: ship only what clears its rule. In simulation, ICP targeting returned SHIP (+25.5%, 95% CI +12.9% to +39.4%), onboarding was ITERATE (underpowered: 801 per arm versus 2,744 needed), reactivation (C) INCONCLUSIVE: it cannot be powered at this size, so INCONCLUSIVE is expected. This is one simulated draw: across 40 simulated seeds, A ships in 37, B in 0, and C shows a spurious significant result in 3. Running three experiments at once raises false-positive risk (multiple comparisons); a real programme would pre-register one primary. The dataset was enlarged from about 1,500 to 3,000 agencies so the 20% ship rule could be powered: A ships in 0 of 20 simulated seeds at 1,500 agencies, 2 at 2,000 and 19 at 3,000. In a real launch, the number of agencies is the binding constraint on what can be proven.

**Assumptions to validate in the first 30 days** (about Hedge, from its public positioning as an AI-native specialty insurer serving brokers; none confirmed):
- Brokers are the main growth channel and a complete submission is the activation event.
- Submission completeness is a real bottleneck to fast quotes.
- The ICP's E&S and specialty appetite matches carrier appetite.
- Agency-level history can be joined across CRM and underwriting systems.
- A 60-day silence is the right dormancy threshold.
