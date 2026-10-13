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
from . import docs, insights as ins, theme
from .funnel import STAGE_BY_KEY

REPO = "https://github.com/jainamh029/broker-growth-os"


def _fig(fig: go.Figure, div_id: str, first: bool, h: int = 340) -> str:
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=30, b=10), font=dict(color=theme.INK, size=13),
                      colorway=theme.COLORWAY)
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


def _badge(decision: str) -> str:
    cls = {"SHIP": "ship", "ITERATE": "iter"}.get(decision, "inc")
    return f"<span class='badge {cls}'>{decision}</span>"


def build_site(root: Path | str | None = None) -> str:
    paths = config.get_paths(root)
    m = lambda n: pd.read_csv(paths.marts / f"{n}.csv")
    f, sq, wk, ex, tl = m("funnel_counts").sort_values("stage_order"), m("source_quality"), m("weekly_growth_review"), m("experiment_results"), m("topline").iloc[0]
    facts = docs.memo_facts(root)
    sweep = json.loads((config.ROOT / "docs" / "seed_sweep.json").read_text())["summary"]

    # funnel with a native Plotly toggle (counts / share of raw leads / share of previous stage)
    names = [STAGE_BY_KEY[x].name for x in f.stage]
    def labels(vals, pct):
        return [f"{v:.0%}" if pct else f"{int(v):,}" for v in vals]
    fig1 = go.Figure(go.Bar(y=names, x=f.agencies, orientation="h", marker=dict(color=list(range(len(f))), colorscale=[[0, theme.BLUE], [1, theme.GREEN]]),
                            text=labels(f.agencies, False), textposition="auto", hovertemplate="%{y}: %{text}<extra></extra>"))
    fig1.update_yaxes(autorange="reversed")
    fig1.update_layout(updatemenus=[dict(type="buttons", direction="right", x=0, y=1.18, showactive=True, buttons=[
        dict(label="Agencies", method="update", args=[{"x": [list(f.agencies)], "text": [labels(f.agencies, False)]}, {"xaxis.tickformat": ",d"}]),
        dict(label="% of raw leads", method="update", args=[{"x": [list(f.cumulative_conversion)], "text": [labels(f.cumulative_conversion, True)]}, {"xaxis.tickformat": ".0%"}]),
        dict(label="% of previous stage", method="update", args=[{"x": [list(f.step_conversion.fillna(1))], "text": [labels(f.step_conversion.fillna(1), True)]}, {"xaxis.tickformat": ".0%"}])])])

    ok = sq[sq.suppressed == 0].copy()
    metrics_ = [("bind_rate_per_lead", "Bound per lead", ".0%"), ("first_submission_rate", "First-submission rate", ".0%"),
                ("repeat_rate_of_bound", "Repeat rate of bound", ".0%"), ("commission_per_lead", "Commission per lead", "$,.0f")]
    base = ok.dropna(subset=["bind_rate_per_lead"]).sort_values("bind_rate_per_lead", ascending=False)
    fig2 = go.Figure(go.Bar(x=base.lead_source, y=base.bind_rate_per_lead, marker_color=theme.BLUE,
                            text=[ins.pct(v) for v in base.bind_rate_per_lead], textposition="outside"))
    btns = []
    for col, lab, fmt in metrics_:
        d = ok.dropna(subset=[col]).sort_values(col, ascending=False)
        txt = [ins.money(v) if col == "commission_per_lead" else ins.pct(v) for v in d[col]]
        btns.append(dict(label=lab, method="update", args=[{"x": [list(d.lead_source)], "y": [list(d[col])], "text": [txt]},
                                                           {"yaxis.tickformat": fmt, "yaxis.title.text": lab}]))
    fig2.update_layout(updatemenus=[dict(type="buttons", direction="right", x=0, y=1.18, showactive=True, buttons=btns)])
    fig2.update_yaxes(tickformat=".0%", title="Bound per lead")

    full = wk[wk.is_partial_week == 0].copy()
    full["ma4"] = full.qualified_submissions.rolling(4).mean()
    fig3 = go.Figure()
    fig3.add_bar(x=full.week_start, y=full.qualified_submissions, name="Qualified submissions", marker_color=theme.BLUE)
    fig3.add_scatter(x=full.week_start, y=full.ma4, name="4-week average", line=dict(color=theme.GREEN, width=3))
    fig3.update_xaxes(rangeslider=dict(visible=True, thickness=0.07))

    fig4 = go.Figure()
    for _, r in ex.iterrows():
        lab = f"{r.experiment_id}: {r['name']} ({r.decision})"
        fig4.add_scatter(x=[r.rel_lift * 100], y=[lab], mode="markers", marker=dict(size=11, color=theme.BLUE),
                         error_x=dict(type="data", symmetric=False, array=[(r.rel_ci_high - r.rel_lift) * 100], arrayminus=[(r.rel_lift - r.rel_ci_low) * 100], color=theme.BLUE),
                         showlegend=False, hovertemplate=f"{lab}<br>lift %{{x:.1f}}%<extra></extra>")
        if pd.notna(r.planted_true_lift):
            fig4.add_scatter(x=[r.planted_true_lift * 100], y=[lab], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(symbol="line-ns", size=22, color=theme.GREEN, line=dict(width=3, color=theme.GREEN)))
    fig4.add_vline(x=0, line_dash="dot", line_color=theme.MUTED)
    fig4.update_xaxes(title="Relative lift, % (blue = estimate with 95% CI, green tick = planted truth)")

    kp = [("Raw leads", int(f.iloc[0].agencies), ""), ("ICP-qualified", int(f[f.stage == "icp_qualified"].iloc[0].agencies), ""),
          ("Engaged", int(f[f.stage == "engaged"].iloc[0].agencies), ""), ("First submissions", int(f[f.stage == "first_submission"].iloc[0].agencies), ""),
          ("Bound", int(f[f.stage == "bound"].iloc[0].agencies), f" ({facts['bound_pct']})"), ("Active agencies (60d)", int(tl.active_agencies_60d), "")]
    kpi_html = "".join(f"<div class='kpi'><div class='v' data-target='{n}' data-suffix='{suf}'>{n:,}{suf}</div><div>{k}</div></div>" for k, n, suf in kp)
    sweep_rows = "".join(f"<tr><td>{k}</td><td>{sweep[k]['decisions'].get('SHIP', 0)}</td><td>{sweep[k]['decisions'].get('ITERATE', 0)}</td>"
                         f"<td>{sweep[k]['decisions'].get('INCONCLUSIVE', 0)}</td><td>{sweep[k]['mean_rel_lift'] * 100:+.1f}%</td></tr>" for k in "ABC")
    cards = []
    for i, (_, r) in enumerate(ex.iterrows()):
        cards.append(
            f"<div class='card exp' id='exp-{r.experiment_id}' role='tabpanel' {'hidden' if i else ''}><h3>{r['name']} {_badge(r.decision)}</h3>"
            f"<p>Control {r.rate_control:.1%} &rarr; treatment {r.rate_treatment:.1%}; relative lift <b>{r.rel_lift * 100:+.1f}%</b> "
            f"(95% CI {r.rel_ci_low * 100:+.1f}% to {r.rel_ci_high * 100:+.1f}%), p = {r.p_value:.3f}.</p>"
            f"<div class='bar'><span style='width:{min(1.0, min(r.n_control, r.n_treatment) / r.n_required_per_arm) * 100:.0f}%'></span></div>"
            f"<p class='small'>Sample: {int(min(r.n_control, r.n_treatment)):,} per arm of {int(r.n_required_per_arm):,} required. Planted truth: {r.planted_true_lift * 100:+.0f}%. Simulated.</p></div>")
    tabs = "".join(f"<button role='tab' class='tab' data-exp='{r.experiment_id}' aria-selected='{'true' if i == 0 else 'false'}'>{r.experiment_id}: {r['name']}</button>"
                   for i, (_, r) in enumerate(ex.iterrows()))
    memo = _md((paths.root / "STRATEGY_MEMO.md").read_text()) if (paths.root / "STRATEGY_MEMO.md").exists() else _md(docs.build_memo(facts))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Broker Growth OS</title><meta name="theme-color" content="{theme.BLUE_DARK}">
<style>
:root{{--ink:{theme.INK};--blue:{theme.BLUE};--green:{theme.GREEN};--surface:{theme.SURFACE};--grid:{theme.GRID}}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth;scroll-padding-top:70px}}
body{{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);margin:0;background:#fff;line-height:1.6}}
.skip{{position:absolute;left:-999px}} .skip:focus{{left:8px;top:8px;background:#fff;padding:8px;z-index:20}}
nav{{position:sticky;top:0;z-index:10;background:#ffffffee;backdrop-filter:blur(8px);border-bottom:1px solid var(--grid)}}
nav .in{{max-width:1040px;margin:0 auto;padding:0 20px;display:flex;gap:4px;align-items:center;overflow-x:auto}}
nav b{{color:{theme.BLUE_DARK};margin-right:12px;white-space:nowrap}}
nav a{{padding:14px 10px;color:{theme.MUTED};text-decoration:none;font-size:.92rem;white-space:nowrap;border-bottom:3px solid transparent;min-height:44px}}
nav a.active,nav a:hover{{color:var(--green);border-bottom-color:var(--green)}}
.hero{{background:linear-gradient(120deg,{theme.BLUE_DARK},{theme.BLUE} 50%,{theme.GREEN});color:#fff}}
.hero .in{{max-width:1040px;margin:0 auto;padding:44px 20px 36px}} .hero h1{{font-size:2.3rem;margin:0 0 8px;letter-spacing:-.02em}}
.hero p{{max-width:720px;color:#e6f4ee;margin:0 0 14px}} .pill{{display:inline-block;background:#ffffff26;border:1px solid #ffffff55;border-radius:999px;padding:3px 13px;font-size:.82rem;margin:0 6px 6px 0}}
.btn{{display:inline-block;background:#fff;color:{theme.BLUE_DARK};padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:600;margin:6px 8px 0 0;min-height:44px}}
.btn.ghost{{background:transparent;color:#fff;border:1px solid #ffffff88}} .btn:hover{{transform:translateY(-2px);box-shadow:0 8px 18px #0b2a3c40}} .btn{{transition:transform .18s,box-shadow .18s}}
main{{max-width:1040px;margin:0 auto;padding:12px 20px 60px}}
.banner{{background:#fff7e0;border:1px solid #e8c766;color:#5b4500;padding:10px 14px;border-radius:10px;margin:16px 0}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}}
.kpi{{background:#fff;border:1px solid var(--grid);border-radius:14px;padding:14px;transition:transform .18s,box-shadow .18s,border-color .18s}}
.kpi:hover{{transform:translateY(-3px);box-shadow:0 10px 22px #0b2a3c1f;border-color:var(--green)}} .kpi .v{{font-size:1.7rem;font-weight:700;color:{theme.BLUE_DARK}}}
section{{margin-top:38px}} h2{{color:{theme.BLUE_DARK};letter-spacing:-.01em;border-bottom:2px solid {theme.MINT};padding-bottom:6px;display:inline-block}}
.take{{border-left:4px solid var(--green);background:var(--surface);border-radius:0 10px 10px 0;padding:8px 14px;margin:6px 0 20px}}
.card{{border:1px solid var(--grid);border-radius:14px;padding:6px 18px 14px;background:#fff;box-shadow:0 1px 3px #0b2a3c14}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}} .tab{{border:1px solid var(--grid);background:#fff;border-radius:999px;padding:10px 16px;cursor:pointer;min-height:44px;font:inherit;color:var(--ink)}}
.tab[aria-selected=true]{{background:var(--green);color:#fff;border-color:var(--green)}} .tab:hover{{border-color:var(--green)}}
.badge{{font-size:.75rem;padding:3px 10px;border-radius:999px;vertical-align:middle;color:#fff}} .ship{{background:var(--green)}} .iter{{background:var(--blue)}} .inc{{background:{theme.MUTED}}}
.bar{{height:10px;background:var(--surface);border-radius:999px;overflow:hidden}} .bar span{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green))}}
.small{{font-size:.88rem;color:{theme.MUTED}}} table{{border-collapse:collapse;width:100%;max-width:640px}} td,th{{border:1px solid var(--grid);padding:6px 10px;text-align:right}} th{{background:var(--surface)}} td:first-child,th:first-child{{text-align:left}}
.calc{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:10px}} label{{display:block;font-size:.88rem;color:{theme.MUTED}}}
input[type=range]{{width:100%;accent-color:var(--green);min-height:32px}} select{{width:100%;min-height:44px;border-radius:8px;border:1px solid var(--grid);padding:0 8px;font:inherit}}
.result{{font-size:1.8rem;font-weight:700;color:var(--green)}}
.note{{background:var(--surface);padding:8px 12px;border-radius:8px}} a{{color:var(--blue)}} code{{background:var(--surface);padding:1px 5px;border-radius:4px}}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid var(--blue);outline-offset:2px}}
footer{{border-top:1px solid var(--grid);padding:18px 20px;text-align:center;color:{theme.MUTED};font-size:.9rem}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important;scroll-behavior:auto!important}}}}
</style></head><body>
<a class="skip" href="#funnel">Skip to content</a>
<nav aria-label="Sections"><div class="in"><b>Broker Growth OS</b><a href="#funnel">Funnel</a><a href="#sources">Sources</a><a href="#northstar">North star</a><a href="#experiments">Experiments</a><a href="#calculator">Calculator</a><a href="#memo">Memo</a></div></nav>
<header class="hero"><div class="in"><h1>Broker Growth OS</h1>
<p>A growth-operations system prototype for an AI-native specialty insurance wholesaler: funnel definition, dirty-data cleaning, transparent agency scoring, SQL metrics, an experiment framework and a human-in-the-loop AI layer.</p>
<span class="pill">Synthetic data</span><span class="pill">Simulated experiments</span><span class="pill">Automated test suite</span><span class="pill">Independently audited</span><br>
<a class="btn" href="{REPO}">View source on GitHub</a><a class="btn ghost" href="{REPO}/blob/main/AUDIT_REPORT.md">Audit report</a><a class="btn ghost" href="{REPO}/blob/main/DEPLOY.md">Run the live dashboard</a></div></header>
<main>
<div class="banner" role="note"><b>{docs.DISCLAIMER}</b> Every number on this page comes from a generated synthetic dataset; experiment results are simulated.</div>
<div class="kpis">{kpi_html}</div>
<section id="funnel"><h2>Funnel</h2><p class="small">Use the buttons above the chart to switch views; hover for details.</p>{_fig(fig1, "fig-funnel", True)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_funnel(f)} The synthetic funnel is deliberately generous so Experiment A can be powered; real rates will be lower.</div></section>
<section id="sources"><h2>Source quality</h2><p class="small">Pick a metric; sources with fewer than {config.MIN_N} agencies are suppressed.</p>{_fig(fig2, "fig-source", False)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_sources(sq)}</div></section>
<section id="northstar"><h2>North star: weekly qualified submissions</h2><p class="small">Drag the slider under the chart to zoom into a range of weeks.</p>{_fig(fig3, "fig-north", False, 400)}
<div class="take"><b>Takeaway.</b> {ins.takeaway_north_star(wk)}</div></section>
<section id="experiments"><h2>Experiments (simulated)</h2>{_fig(fig4, "fig-exp", False, 280)}
<div class="tabs" role="tablist" aria-label="Experiments">{tabs}</div>{"".join(cards)}
<div class="take"><b>Takeaway.</b> Each result is one simulated draw. Running three experiments at once carries a multiple comparisons risk; no alpha adjustment is applied.</div>
<table><tr><th>Experiment (40 seeds)</th><th>SHIP</th><th>ITERATE</th><th>INCONCLUSIVE</th><th>Mean lift</th></tr>{sweep_rows}</table></section>
<section id="calculator"><h2>Sample-size calculator</h2><p class="small">How many agencies per arm would a real test need? Same two-proportion formula as the framework.</p>
<div class="card"><div class="calc">
<div><label for="c-base">Baseline rate: <b id="o-base"></b></label><input id="c-base" type="range" min="2" max="60" value="10"></div>
<div><label for="c-lift">Relative lift to detect: <b id="o-lift"></b></label><input id="c-lift" type="range" min="5" max="60" value="20"></div>
<div><label for="c-alpha">Alpha</label><select id="c-alpha"><option value="1.6449">0.10</option><option value="1.96" selected>0.05</option><option value="2.5758">0.01</option></select></div>
<div><label for="c-power">Power</label><select id="c-power"><option value="0.8416" selected>80%</option><option value="1.2816">90%</option><option value="1.6449">95%</option></select></div></div>
<p>Required per arm: <span class="result" id="o-n" aria-live="polite"></span> &nbsp; Total: <b id="o-tot"></b></p></div></section>
<section id="memo"><h2>Strategy memo</h2><div class="card">{memo}</div></section>
<p class="note">The repository's suite checks every SQL metric against an independent computation, and a test requires this page to match the generated outputs. See the <a href="{REPO}">README</a>.</p>
</main>
<footer>Synthetic data. Demonstrates the method, not Hedge's actual performance. &middot; <a href="{REPO}">GitHub</a></footer>
<script>
(function(){{
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('.kpi .v').forEach(function(el){{
    var t = +el.dataset.target, suf = el.dataset.suffix || '';
    if (reduce) return;
    var s = null; function step(ts){{ if(!s) s = ts; var p = Math.min(1,(ts-s)/900); el.textContent = Math.round(t*(1-Math.pow(1-p,3))).toLocaleString('en-US') + (p<1?'':suf); if(p<1) requestAnimationFrame(step); }}
    requestAnimationFrame(step);
  }});
  var links = document.querySelectorAll('nav a'), secs = [].map.call(links, function(a){{ return document.querySelector(a.getAttribute('href')); }});
  var io = new IntersectionObserver(function(es){{ es.forEach(function(e){{ if(e.isIntersecting){{ links.forEach(function(l){{ l.classList.toggle('active', l.getAttribute('href') === '#'+e.target.id); }}); }} }}); }}, {{rootMargin:'-40% 0px -55% 0px'}});
  secs.forEach(function(s){{ if(s) io.observe(s); }});
  document.querySelectorAll('.tab').forEach(function(b){{ b.addEventListener('click', function(){{
    document.querySelectorAll('.tab').forEach(function(x){{ x.setAttribute('aria-selected', x===b ? 'true':'false'); }});
    document.querySelectorAll('.exp').forEach(function(c){{ c.hidden = c.id !== 'exp-'+b.dataset.exp; }}); }}); }});
  function z(id){{ return parseFloat(document.getElementById(id).value); }}
  function calc(){{
    var p1 = z('c-base')/100, lift = z('c-lift')/100, p2 = Math.min(0.99, p1*(1+lift)), za = z('c-alpha'), zb = z('c-power'), pb = (p1+p2)/2;
    var n = Math.ceil(Math.pow(za*Math.sqrt(2*pb*(1-pb)) + zb*Math.sqrt(p1*(1-p1)+p2*(1-p2)), 2) / Math.pow(p1-p2, 2));
    document.getElementById('o-base').textContent = (p1*100).toFixed(0)+'%'; document.getElementById('o-lift').textContent = '+'+(lift*100).toFixed(0)+'%';
    document.getElementById('o-n').textContent = n.toLocaleString('en-US'); document.getElementById('o-tot').textContent = (2*n).toLocaleString('en-US');
  }}
  ['c-base','c-lift','c-alpha','c-power'].forEach(function(id){{ document.getElementById(id).addEventListener('input', calc); }}); calc();
}})();
</script></body></html>
"""


def run_site(root: Path | str | None = None) -> Path:
    paths = config.get_paths(root)
    out = paths.root / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_site(root))
    return out
