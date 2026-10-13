# Strategy Memo: Broker Growth OS

> Synthetic data. Demonstrates the method, not Hedge's actual performance. Every number below comes from the generated synthetic outputs.

**Growth thesis.** A specialty wholesaler grows by turning more agencies into repeat submitters, not by sending more email. Our north star is weekly qualified submissions from active agencies; every lever is judged by downstream bind and repeat, never by sends or connections.

**Funnel.** Raw lead, ICP-qualified, Engaged, First submission (complete, underwriting-ready), Quoted, Bound, Repeat (another complete submission within 90 days of bind). Synthetic baseline: 1,500 leads, 1,112 ICP-qualified (74%), 797 engaged, 521 first submissions, 203 bound (13.5% of leads), 150 repeat.

**ICP.** Commercial lines with E&S or specialty exposure and at least 3 producers. A transparent fit score ranks every agency: 82 Tier 1 for immediate outbound, 610 Tier 2 to nurture, 206 dormant to reactivate. The tier ordering is a plumbing check on synthetic data, not evidence of predictive power.

**Two highest-leverage gaps (synthetic baseline).**
1. Activation: only 42% of engaged agencies send a complete submission within 14 days. Each +10 points adds about 80 first submissions on this book.
2. Source mix: linkedin supplies 32% of leads but binds 8.4% of them, versus 23.0% for referral (2.7x). Moving 10% of lead volume to referral-quality sources adds roughly 22 bound agencies (back-of-envelope; assumes that channel scales).

Watch metric: median time to quote is 35 hours; protect it while volume grows, because speed is what brokers remember.

**90-day plan.**
- Days 1-30, establish truth: join CRM and submission data at agency level, lock stage definitions, deduplicate, baseline every metric with minimum-n rules.
- Days 31-60, ship experiments: ICP-targeted outbound, submission-ready onboarding, and reactivation versus a holdout, each with a pre-registered effect size, sample size and decision rule.
- Days 61-90, prove lift: ship only what clears its rule. In simulation, ICP targeting returned SHIP (+27.3%, 95% CI +9.4% to +48.2%), onboarding was ITERATE (underpowered: 383 per arm versus 1,058 needed), reactivation was INCONCLUSIVE. Real baselines will differ.

**Assumptions to validate in the first 30 days** (about Hedge, from its public positioning as an AI-native specialty insurer serving brokers; none confirmed):
- Brokers are the main growth channel and a complete submission is the activation event.
- Submission completeness is a real bottleneck to fast quotes.
- The ICP's E&S and specialty appetite matches carrier appetite.
- Agency-level history can be joined across CRM and underwriting systems.
- A 60-day silence is the right dormancy threshold.
