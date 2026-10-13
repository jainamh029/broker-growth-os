"""Static showcase page for GitHub Pages (docs/index.html), built from the generated marts. SYNTHETIC data only.

Streamlit cannot run on GitHub Pages, so this page shows the key charts and the memo statically and links to the code.
It is deterministic (fixed plotly div ids) so a test can require the committed page to equal a regenerated one.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import config
from . import docs, insights as ins
from .funnel import STAGE_BY_KEY

REPO = "https://github.com/jainamh029/broker-growth-os"
INK, ACCENT, MUTED, ALERT = "#1b2a41", "#1d4e89", "#9aa8b5", "#b5483a"


def _fig(fig: go.Figure, div_id: str, first: bool, h: int = 340) -> str:
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=30, b=10), font=dict(color=INK, size=13),
                      colorway=[ACCENT, MUTED, ALERT])
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False, div_id=div_id, config={"displayModeBar": False})


def _md(text: str) -> str:
    out, in_ul, in_ol = [], False, False
    def close():
        nonlocal in_ul, in_ol
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False
    for line in text.splitlines():
        e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line.strip(), quote=False))
        e = re.sub(r"`(.+?)`", r"<code>\1</code>", e)
        if line.startswith("# "): close(); continue
        if line.startswith("&gt;") or line.startswith(">"): close(); out.append(f"<p class='note'>{e.lstrip('&gt;').strip()}</p>")
        elif line.startswith("- "): 
            if not in_ul: close(); out.append("<ul>"); in_ul = True
            out.append(f"<li>{e[2:]}</li>")
        elif re.match(r"\d+\. ", line):
            if not in_ol: close(); out.append("<ol>"); in_ol = True
            out.append(f"<li>{re.sub(r'^[0-9]+[.] ', '', e)}</li>")
        elif line.strip(): close(); out.append(f"<p>{e}</p>")
    close()
    return "\n".join(out)


def build_site(root: Path | str | None = None) -> str:
    paths = config.get_paths(root)
    m = lambda n: pd.read_csv(paths.marts / f"{n}.csv")
    f, sq, wk, ex, tl = m("funnel_counts").sort_values("stage_order"), m("source_quality"), m("weekly_growth_review"), m("experiment_results"), m("topline").iloc[0]
    facts = docs.memo_facts(root)
    sweep = json.loads((config.ROOT / "docs" / "seed_sweep.json").read_text())["summary"]

    fig1 = go.Figure(go.Bar(y=[STAGE_BY_KEY[s].name for s in f.stage], x=f.agencies, orientation="h", marker_color=ACCENT,
                            text=[f"{int(a):,}" for a in f.agencies], textposition="auto"))
    fig1.update_yaxes(autorange="reversed")
    ok = sq[sq.suppressed == 0].sort_values("bind_rate_per_lead", ascending=False)
    fig2 = go.Figure(go.Bar(x=ok.lead_source, y=ok.bind_rate_per_lead, marker_color=ACCENT,
                            text=[ins.pct(v) for v in ok.bind_rate_per_lead], textposition="outside"))
    fig2.update_yaxes(tickformat=".0%", title="Bound agencies per lead")
    full = wk[wk.is_partial_week == 0].copy()
    full["ma4"] = full.qualified_submissions.rolling(4).mean()
    fig3 = go.Figure()
    fig3.add_bar(x=full.week_start, y=full.qualified_submissions, name="Qualified submissions", marker_color=ACCENT)
    fig3.add_scatter(x=full.week_start, y=full.ma4, name="4-week average", line=dict(color=ALERT, width=2))
    fig4 = go.Figure()
    for _, r in ex.iterrows():
        fig4.add_scatter(x=[r.rel_lift * 100], y=[f"{r.experiment_id}: {r['name']} ({r.decision})"], mode="markers", marker=dict(size=11, color=ACCENT),
                         error_x=dict(type="data", symmetric=False, array=[(r.rel_ci_high - r.rel_lift) * 100], arrayminus=[(r.rel_lift - r.rel_ci_low) * 100], color=ACCENT),
                         showlegend=False)
        if pd.notna(r.planted_true_lift):
            fig4.add_scatter(x=[r.planted_true_lift * 100], y=[f"{r.experiment_id}: {r['name']} ({r.decision})"], mode="markers",
                             marker=dict(symbol="line-ns", size=22, color=ALERT, line=dict(width=3, color=ALERT)), showlegend=False)
    fig4.add_vline(x=0, line_dash="dot", line_color=MUTED)
    fig4.update_xaxes(title="Relative lift, % (blue = estimate with 95% CI, red tick = planted truth)")

    kpis = [("Raw leads", facts["raw"]), ("ICP-qualified", facts["icp"]), ("Engaged", facts["engaged"]),
            ("First submissions", facts["first_sub"]), ("Bound", f"{facts['bound']} ({facts['bound_pct']})"), ("Active agencies (60d)", f"{int(tl.active_agencies_60d):,}")]
    kpi_html = "".join(f"<div class='kpi'><div class='v'>{v}</div><div>{k}</div></div>" for k, v in kpis)
    sweep_rows = "".join(f"<tr><td>{k}</td><td>{sweep[k]['decisions'].get('SHIP', 0)}</td><td>{sweep[k]['decisions'].get('ITERATE', 0)}</td>"
                         f"<td>{sweep[k]['decisions'].get('INCONCLUSIVE', 0)}</td><td>{sweep[k]['mean_rel_lift'] * 100:+.1f}%</td></tr>" for k in "ABC")
    memo = _md((paths.root / "STRATEGY_MEMO.md").read_text()) if (paths.root / "STRATEGY_MEMO.md").exists() else _md(docs.build_memo(facts))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Broker Growth OS</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:{INK};margin:0;background:#fff;line-height:1.55}}
main{{max-width:980px;margin:0 auto;padding:16px 20px 60px}}
.banner{{background:#fff4d6;border:1px solid #e6c667;color:#5b4500;padding:10px 14px;border-radius:6px;margin:14px 0}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}
.kpi{{background:#f3f5f8;border-radius:8px;padding:10px 12px}} .kpi .v{{font-size:1.5rem;font-weight:600}}
.take{{border-left:3px solid {ACCENT};padding:2px 12px;margin:4px 0 22px}}
h1{{margin-bottom:4px}} h2{{margin-top:34px}} table{{border-collapse:collapse}} td,th{{border:1px solid #d5dbe3;padding:5px 10px;text-align:right}}
.note{{background:#f3f5f8;padding:8px 12px;border-radius:6px}} a{{color:{ACCENT}}} code{{background:#f3f5f8;padding:1px 4px;border-radius:4px}}
</style></head><body><main>
<h1>Broker Growth OS</h1>
<p>A growth-operations system prototype for an AI-native specialty insurance wholesaler: funnel definition, dirty-data cleaning, transparent agency scoring, SQL metrics, an experiment framework and a human-in-the-loop AI layer.</p>
<div class="banner"><b>{docs.DISCLAIMER}</b> Every number on this page comes from a generated synthetic dataset; experiment results are simulated.</div>
<p><a href="{REPO}">Source code and README on GitHub</a> &middot; <a href="{REPO}/blob/main/STRATEGY_MEMO.md">Strategy memo</a> &middot; <a href="{REPO}/blob/main/AUDIT_REPORT.md">Independent audit</a> &middot; <a href="{REPO}/blob/main/DEPLOY.md">Run the interactive dashboard</a></p>
<div class="kpis">{kpi_html}</div>
<h2>Funnel</h2>{_fig(fig1, "fig-funnel", True)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_funnel(f)} The synthetic funnel is deliberately generous so Experiment A can be powered; real rates will be lower.</div>
<h2>Source quality</h2>{_fig(fig2, "fig-source", False)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_sources(sq)}</div>
<h2>North star: weekly qualified submissions</h2>{_fig(fig3, "fig-north", False)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_north_star(wk)}</div>
<h2>Experiments (simulated)</h2>{_fig(fig4, "fig-exp", False, 280)}
<div class="take"><b>Takeaway.</b> Each result is one simulated draw. Running three experiments at once carries a multiple comparisons risk; no alpha adjustment is applied.</div>
<table><tr><th>Experiment (40 seeds)</th><th>SHIP</th><th>ITERATE</th><th>INCONCLUSIVE</th><th>Mean lift</th></tr>{sweep_rows}</table>
<h2>Strategy memo</h2>{memo}
<p class="note">Tests: the repository's suite checks every SQL metric against an independent computation, and a test requires this page to match the generated outputs. See the <a href="{REPO}">README</a>.</p>
</main></body></html>
"""


def run_site(root: Path | str | None = None) -> Path:
    paths = config.get_paths(root)
    out = paths.root / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_site(root))
    return out
