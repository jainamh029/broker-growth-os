"""Static showcase page for GitHub Pages (docs/index.html), built from the generated marts. SYNTHETIC data only.

Streamlit cannot run on GitHub Pages, so the home page is a static, fully client-side interactive dashboard (all nine views,
data embedded as JSON, charts drawn by Plotly in the browser) and the strategy memo lives on its own page (memo.html).
Output is deterministic so a test can require the committed pages to equal regenerated ones.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

import config
from . import docs, insights as ins, theme
from .rounding import round_obj
from .funnel import STAGE_BY_KEY

REPO = "https://github.com/jainamh029/broker-growth-os"


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


CSS = """
:root{--ink:__INK__;--blue:__BLUE__;--green:__GREEN__;--surface:__SURFACE__;--grid:__GRID__;--muted:__MUTED__;--dark:__DARK__;--card:__CARD__;--bg:__BG__}
*{box-sizing:border-box} html{scroll-behavior:smooth;scroll-padding-top:120px}
body{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);margin:0;background:linear-gradient(160deg,var(--bg),__BG2__) fixed;line-height:1.55}
.skip{position:absolute;left:-999px} .skip:focus{left:8px;top:8px;background:#fff;padding:8px;z-index:30}
header.top{background:linear-gradient(120deg,#0b1b33,#10294d 60%,#134e4a);color:#fff}
header.top .in{max-width:1180px;margin:0 auto;padding:18px 20px 12px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
header.top h1{margin:0;font-size:1.5rem;letter-spacing:-.01em} header.top p{margin:2px 0 0;color:#e6f4ee;font-size:.92rem}
.links a{color:#fff;text-decoration:none;border:1px solid #ffffff88;border-radius:10px;padding:9px 14px;margin-left:8px;font-size:.9rem;display:inline-block;min-height:44px;line-height:24px}
.links a:hover{background:#ffffff26}
nav{position:sticky;top:0;z-index:10;background:#ffffffee;backdrop-filter:blur(8px);border-bottom:1px solid var(--grid)}
nav .in{max-width:1180px;margin:0 auto;padding:0 12px;display:flex;gap:2px;overflow-x:auto}
nav a{padding:13px 12px;color:var(--muted);text-decoration:none;font-size:.92rem;white-space:nowrap;border-bottom:3px solid transparent;min-height:44px}
nav a.active,nav a:hover{color:var(--green);border-bottom-color:var(--green)}
main{max-width:1180px;margin:0 auto;padding:14px 20px 50px}
.banner{background:#fff7e0;border:1px solid #e8c766;color:#5b4500;padding:10px 14px;border-radius:10px;margin:6px 0 14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:10px 0 14px}
.kpi{background:var(--card);border:1px solid var(--grid);border-radius:14px;padding:12px 14px;transition:transform .18s,box-shadow .18s,border-color .18s}
.kpi:hover{transform:translateY(-3px);box-shadow:0 10px 22px #0f172a1f;border-color:var(--green)}
.kpi .v{font-size:1.65rem;font-weight:700;color:var(--dark)} .kpi .l{font-size:.85rem;color:var(--muted)} .kpi .d{font-size:.8rem;color:var(--green)}
h2{color:var(--dark);margin:6px 0 4px} h3{color:var(--dark);margin:20px 0 6px}
.take{border-left:4px solid var(--green);background:var(--surface);border-radius:0 10px 10px 0;padding:8px 14px;margin:6px 0 16px}
.card{border:1px solid var(--grid);border-radius:14px;padding:8px 18px 14px;background:var(--card);box-shadow:0 1px 3px #0f172a14;margin:10px 0}
.ctl{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:8px 0;font-size:.92rem}
.ctl label{display:flex;gap:8px;align-items:center;color:var(--ink)} select,input[type=search]{min-height:40px;border-radius:8px;border:1px solid var(--grid);padding:0 10px;font:inherit;background:var(--card)}
input[type=range]{accent-color:var(--green);min-height:32px} input[type=checkbox]{accent-color:var(--green);width:18px;height:18px}
.seg{display:inline-flex;border:1px solid var(--grid);border-radius:10px;overflow:hidden;background:var(--card)}
.seg button{border:0;background:var(--card);padding:10px 14px;cursor:pointer;font:inherit;min-height:44px;color:var(--ink)} .seg button[aria-pressed=true]{background:var(--green);color:#fff}
.btn{border:1px solid var(--green);color:#0a5c40;background:var(--card);border-radius:10px;padding:9px 14px;cursor:pointer;font:inherit;min-height:44px}
.btn:hover{background:var(--green);color:#fff}
.tw{overflow-x:auto;border:1px solid var(--grid);border-radius:12px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:.86rem} th{background:var(--surface);text-align:left;position:sticky;top:0;cursor:default}
td,th{padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top} tr:hover td{background:#f1f8f5}
.badge{font-size:.75rem;padding:3px 10px;border-radius:999px;color:#fff;vertical-align:middle} .ship{background:var(--green)} .iter{background:var(--blue)} .inc{background:var(--muted)}
.bar{height:10px;background:var(--surface);border-radius:999px;overflow:hidden} .bar span{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green))}
.small{font-size:.86rem;color:var(--muted)} .pg{display:flex;gap:8px;align-items:center;margin:8px 0}
.calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px} .result{font-size:1.8rem;font-weight:700;color:var(--green)}
a{color:var(--blue)} code{background:var(--surface);padding:1px 5px;border-radius:4px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--blue);outline-offset:2px}
footer .fp{font-size:.8rem;font-family:ui-monospace,Menlo,monospace}
footer{border-top:1px solid var(--grid);padding:18px 20px;text-align:center;color:var(--muted);font-size:.9rem}
.memo p,.memo li{max-width:820px} .memo .note{background:var(--surface);padding:8px 12px;border-radius:8px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
""".replace("__INK__", theme.INK).replace("__BLUE__", theme.BLUE).replace("__GREEN__", theme.GREEN).replace("__SURFACE__", theme.SURFACE).replace("__GRID__", theme.GRID).replace("__MUTED__", theme.MUTED).replace("__DARK__", theme.BLUE_DARK).replace("__CARD__", theme.CARD).replace("__BG__", theme.BG).replace("__BG2__", theme.BG2)

JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const C = {blue:'#2563eb', green:'#0f766e', teal:'#0891b2', sky:'#93c5fd', mint:'#99d9cf', amber:'#b45309', ink:'#0f172a', muted:'#475569', grid:'#e2e8f0', dark:'#0b1b33'};
const $ = (s, r) => (r || document).querySelector(s);
const fmt = n => Math.round(n).toLocaleString('en-US');
const pct = (x, d) => (x == null || isNaN(x)) ? 'n/a' : (x * 100).toFixed(d == null ? 1 : d) + '%';
const money = x => x == null ? 'n/a' : (Math.abs(x) >= 1e6 ? '$' + (x / 1e6).toFixed(2) + 'M' : Math.abs(x) >= 1e4 ? '$' + fmt(x / 1e3) + 'K' : '$' + fmt(x));
const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const view = $('#view');
function lay(h, extra) { return Object.assign({height: h, margin: {l: 55, r: 12, t: 34, b: 44}, font: {color: C.ink, size: 13}, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  xaxis: {gridcolor: C.grid}, yaxis: {gridcolor: C.grid}, legend: {orientation: 'h', y: -0.22}, hoverlabel: {bgcolor: '#fff'}}, extra || {}); }
function plot(id, traces, l) { Plotly.react(id, traces, l, {displayModeBar: false, responsive: true}); }
const take = t => `<div class="take"><b>Takeaway.</b> ${esc(t)}</div>`;
const kpi = (l, v, d) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div>${d ? `<div class="d">${d}</div>` : ''}</div>`;
const badge = d => `<span class="badge ${d === 'SHIP' ? 'ship' : d === 'ITERATE' ? 'iter' : 'inc'}">${d}</span>`;
function table(rows, cols) {
  return `<div class="tw"><table><thead><tr>${cols.map(c => `<th>${c.l}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(r => `<tr>${cols.map(c => `<td>${c.f ? c.f(r[c.k], r) : esc(r[c.k])}</td>`).join('')}</tr>`).join('') + `</tbody></table></div>`;
}
function download(name, rows, cols) {
  const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
  const t = [cols.map(c => q(c.l)).join(',')].concat(rows.map(r => cols.map(c => q(r[c.k])).join(','))).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([t], {type: 'text/csv'})); a.download = name; a.click();
}
function seg(id, opts, cur) { return `<div class="seg" id="${id}" role="group">${opts.map(o => `<button type="button" data-v="${o[0]}" aria-pressed="${o[0] === cur}">${o[1]}</button>`).join('')}</div>`; }
function onSeg(id, cb) { const g = $('#' + id); g.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { g.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false')); cb(b.dataset.v); })); }
const stageName = k => D.stage_names[k];

const V = {};
V.monday = function () {
  const t = D.topline, f = D.funnel;
  view.innerHTML = `<h2>Monday Morning</h2><div class="kpis">${kpi('New ICP agencies (7d)', fmt(t.new_icp_7d), (t.new_icp_7d - t.new_icp_prev_7d >= 0 ? '+' : '') + (t.new_icp_7d - t.new_icp_prev_7d) + ' vs prior 7d')}
  ${kpi('New activations (7d)', fmt(t.new_activations_7d))}${kpi('Complete submissions (7d)', fmt(t.complete_submissions_7d), (t.complete_submissions_7d - t.complete_submissions_prev_7d >= 0 ? '+' : '') + (t.complete_submissions_7d - t.complete_submissions_prev_7d) + ' vs prior 7d')}
  ${kpi('Active agencies (60d)', fmt(t.active_agencies_60d))}${kpi('Dormant agencies', fmt(t.dormant_agencies))}
  ${kpi('Commission, last 90d', money(t.commission_last_90d))}${kpi('Bound premium, last 90d', money(t.bound_premium_last_90d))}</div>
  <div class="ctl">${seg('fm', [['step', 'Mature % of previous stage'], ['cum', 'Mature % of raw leads'], ['obs', 'Observed % of raw leads (understates)']], 'step')}</div><div id="fig-funnel"></div>${take(D.takeaways.funnel)}
  <p class="small">Mature rates measure each step only on agencies that reached the previous stage long enough ago to have converted (windows set from the observed lags). The synthetic funnel is deliberately generous so Experiment A can be statistically powered; real conversion rates will be lower.</p>
  <h3>Work first this week: highest-fit prospects that are not yet submitting</h3>
  <div class="ctl"><label>Accounts <input type="range" id="nn" min="3" max="25" value="8"> <b id="nv">8</b></label></div><div id="tb"></div>`;
  const lab = (r, m) => m === 'step' ? r.mature_step_conversion : m === 'cum' ? r.mature_cumulative_conversion : r.observed_cumulative_conversion;
  const draw = m => plot('fig-funnel', [{type: 'bar', orientation: 'h', y: f.map(r => stageName(r.stage)), x: f.map(r => r.agencies),
    marker: {color: f.map((r, i) => i), colorscale: [[0, C.blue], [1, C.green]]},
    text: f.map(r => fmt(r.agencies) + (lab(r, m) == null ? '' : '  (' + pct(lab(r, m), 0) + ')')), textposition: 'auto',
    hovertemplate: '%{y}: %{x} agencies<extra></extra>'}], lay(360, {yaxis: {autorange: 'reversed'}, margin: {l: 150, r: 12, t: 10, b: 30}}));
  draw('step'); onSeg('fm', draw);
  const rows = () => D.ranked.filter(r => (r.tier === 'Tier 1' || r.tier === 'Tier 2'))
    .sort((a, b) => (a.tier < b.tier ? -1 : a.tier > b.tier ? 1 : b.score - a.score));
  const cols = [{k: 'name', l: 'Agency'}, {k: 'score', l: 'Score', f: v => v.toFixed(2)}, {k: 'tier', l: 'Tier'}, {k: 'next_action', l: 'Next action'}, {k: 'owner', l: 'Owner'}, {k: 'channel', l: 'Channel'}];
  const tb = () => { $('#nv').textContent = $('#nn').value; $('#tb').innerHTML = table(rows().slice(0, +$('#nn').value), cols); };
  $('#nn').addEventListener('input', tb); tb();
};

V.weekly = function () {
  const w = D.weekly.filter(r => !r.is_partial_week);
  view.innerHTML = `<h2>Weekly Growth Review</h2><p class="small">North star: qualified submissions per week = complete submissions from ICP agencies that are new or active (previous submission less than 60 days earlier).</p>
  <div class="ctl"><label>From <select id="w0">${w.map(r => `<option>${r.week_start}</option>`).join('')}</select></label>
  <label>To <select id="w1">${w.map(r => `<option>${r.week_start}</option>`).join('')}</select></label><label><input type="checkbox" id="ma" checked> 4-week average</label></div>
  <div id="fig-north"></div>${take(D.takeaways.north_star)}<h3>Inputs (what we control)</h3><div id="fig-in"></div><h3>Diagnostics (why the north star moved)</h3><div id="fig-dg"></div>`;
  $('#w1').selectedIndex = w.length - 1;
  const ma = (arr) => arr.map((_, i) => i < 3 ? null : (arr[i] + arr[i - 1] + arr[i - 2] + arr[i - 3]) / 4);
  const draw = () => {
    const a = Math.min($('#w0').selectedIndex, $('#w1').selectedIndex), b = Math.max($('#w0').selectedIndex, $('#w1').selectedIndex), sel = w.slice(a, b + 1), x = sel.map(r => r.week_start);
    const tr = [{type: 'bar', x, y: sel.map(r => r.qualified_submissions), name: 'Qualified submissions', marker: {color: C.blue}, hovertemplate: 'Week of %{x}: %{y}<extra></extra>'}];
    if ($('#ma').checked) tr.push({type: 'scatter', x, y: ma(w.map(r => r.qualified_submissions)).slice(a, b + 1), name: '4-week average', line: {color: C.green, width: 3}});
    plot('fig-north', tr, lay(320));
    const line = (k, n, c, src) => ({type: 'scatter', x, y: src.slice(a, b + 1), name: n, line: {color: c, width: 2}});
    plot('fig-in', [line('', 'New ICP agencies', C.blue, ma(w.map(r => r.new_icp_agencies))), line('', 'Newly engaged', C.teal, ma(w.map(r => r.new_engaged_agencies))), line('', 'Activations', C.green, ma(w.map(r => r.new_activations)))], lay(280));
    const d = (k, n, c) => ({type: 'scatter', x, y: w.map(r => r[k]).slice(a, b + 1), name: n, line: {color: c, width: 2}, connectgaps: false});
    plot('fig-dg', [d('completeness_rate', 'Submission completeness', C.blue), d('quote_rate', 'Quote rate', C.teal), d('bind_rate_of_quoted', 'Bind rate of quoted', C.green)], lay(280, {yaxis: {tickformat: '.0%', gridcolor: C.grid}}));
  };
  ['w0', 'w1', 'ma'].forEach(i => $('#' + i).addEventListener('input', draw)); draw();
};

V.sources = function () {
  const labels = {bind_rate_per_lead: 'Bound agencies per lead', first_submission_rate: 'First-submission rate', repeat_rate_of_bound: 'Repeat rate of bound agencies', commission_per_lead: 'Commission per lead'};
  view.innerHTML = `<h2>Source Quality</h2><p class="small">Judged by downstream bind and repeat, not lead count. Sources with fewer than ${D.meta.min_n} agencies are suppressed.</p>
  <div class="ctl"><label>Metric <select id="sm">${Object.keys(labels).map(k => `<option value="${k}">${labels[k]}</option>`).join('')}</select></label><label><input type="checkbox" id="st" checked> Show suppressed tiny sources in the table</label></div>
  <div id="fig-source"></div><div id="fig-vol"></div>${take(D.takeaways.sources)}<div id="tb"></div>`;
  const ok = D.sources.filter(r => !r.suppressed);
  const draw = () => {
    const m = $('#sm').value, d = ok.filter(r => r[m] != null).sort((a, b) => b[m] - a[m]), money_ = m === 'commission_per_lead';
    plot('fig-source', [{type: 'bar', x: d.map(r => r.lead_source), y: d.map(r => r[m]), marker: {color: C.blue}, text: d.map(r => money_ ? money(r[m]) : pct(r[m])), textposition: 'outside'}], lay(300, {yaxis: {tickformat: money_ ? '$,.0f' : '.0%', title: labels[m], gridcolor: C.grid}}));
    plot('fig-vol', [{type: 'bar', x: ok.map(r => r.lead_source), y: ok.map(r => r.leads), marker: {color: C.green}, text: ok.map(r => r.leads), textposition: 'outside'}], lay(240, {yaxis: {title: 'Leads (volume)', gridcolor: C.grid}}));
    const rows = $('#st').checked ? D.sources : ok;
    $('#tb').innerHTML = table(rows, [{k: 'lead_source', l: 'Source'}, {k: 'leads', l: 'Leads'}, {k: 'first_submission_rate', l: 'First submission', f: v => pct(v)}, {k: 'bind_rate_per_lead', l: 'Bound per lead', f: v => pct(v)},
      {k: 'repeat_rate_of_bound', l: 'Repeat of bound', f: v => pct(v)}, {k: 'commission_per_lead', l: 'Commission / lead', f: v => money(v)}, {k: 'suppressed', l: 'Suppressed (n<' + D.meta.min_n + ')', f: v => v ? 'yes' : ''}]);
  };
  ['sm', 'st'].forEach(i => $('#' + i).addEventListener('input', draw)); draw();
};

V.ttq = function () {
  view.innerHTML = `<h2>Time-to-Quote</h2><div class="ctl">${seg('sc', [['all_submissions', 'All quoted submissions'], ['first_submissions', "Each agency's first submission"]], 'all_submissions')}</div>
  <div id="fig-cx"></div><div id="fig-lob"></div>${take(D.takeaways.ttq)}<div id="tb"></div>`;
  const draw = sc => {
    const d = D.ttq.filter(r => r.scope === sc), cx = ['low', 'medium', 'high'].map(v => d.find(r => r.dimension === 'risk_complexity' && r.value === v)).filter(r => r && r.median_hours != null);
    plot('fig-cx', [{type: 'bar', x: cx.map(r => r.value), y: cx.map(r => r.median_hours), marker: {color: [C.sky, C.blue, C.dark]}, text: cx.map(r => Math.round(r.median_hours) + 'h'), textposition: 'outside'}], lay(280, {yaxis: {title: 'Median hours to quote', gridcolor: C.grid}}));
    const lob = d.filter(r => r.dimension === 'line_of_business').sort((a, b) => a.median_hours - b.median_hours);
    $('#fig-lob').style.display = lob.length ? '' : 'none';
    if (lob.length) plot('fig-lob', [{type: 'bar', orientation: 'h', y: lob.map(r => r.value), x: lob.map(r => r.median_hours), marker: {color: C.green}}], lay(300, {margin: {l: 170, r: 12, t: 10, b: 40}, xaxis: {title: 'Median hours to quote', gridcolor: C.grid}}));
    $('#tb').innerHTML = table(d, [{k: 'dimension', l: 'Dimension'}, {k: 'value', l: 'Value'}, {k: 'n', l: 'n'}, {k: 'median_hours', l: 'Median hours', f: v => v == null ? 'suppressed' : v.toFixed(1)}]);
  };
  draw('all_submissions'); onSeg('sc', draw);
};

V.activation = function () {
  view.innerHTML = `<h2>Activation and Cohorts</h2><div id="fig-act"></div><div class="ctl"><label>Retention window <select id="rw"><option value="all">All windows</option><option value="30">30 days</option><option value="60">60 days</option><option value="90">90 days</option></select></label></div>
  <div id="fig-ret"></div>${take(D.takeaways.activation)}<p class="small">Only mature agencies (a full window observed before the as-of date) are in each denominator; blank cells are suppressed or immature.</p>`;
  const a = D.activation.filter(r => r.cohort !== 'ALL');
  plot('fig-act', [{type: 'bar', x: a.map(r => r.cohort), y: a.map(r => r.activation_rate), marker: {color: C.green}, text: a.map(r => pct(r.activation_rate, 0)), textposition: 'outside'}], lay(300, {yaxis: {tickformat: '.0%', title: 'Engaged agencies submitting within 14 days', gridcolor: C.grid}}));
  const c = D.cohorts.filter(r => r.cohort !== 'ALL');
  const draw = () => { const w = $('#rw').value, ks = w === 'all' ? ['30', '60', '90'] : [w];
    plot('fig-ret', [{type: 'heatmap', x: ks.map(k => k + ' days'), y: c.map(r => r.cohort), z: c.map(r => ks.map(k => r['retention_' + k])), zmin: 0, zmax: 1, showscale: false,
      colorscale: [[0, '#eef2f7'], [0.5, C.sky], [1, C.dark]], text: c.map(r => ks.map(k => pct(r['retention_' + k], 0))), texttemplate: '%{text}'}], lay(420, {yaxis: {autorange: 'reversed', title: 'First-submission month'}})); };
  $('#rw').addEventListener('input', draw); draw();
};

V.dormant = function () {
  const d = D.dormant, specs = [...new Set(d.map(r => r.specialty_focus))].sort();
  view.innerHTML = `<h2>Dormancy and Reactivation</h2><div class="kpis">${kpi('Dormant agencies', fmt(d.length))}${kpi('Prior bound premium', money(d.reduce((s, r) => s + r.prior_bound_premium, 0)))}${kpi('Prior commission', money(d.reduce((s, r) => s + r.prior_commission, 0)))}</div>
  <div class="ctl"><label>Top agencies <input type="range" id="tn" min="5" max="50" value="25"> <b id="tv">25</b></label><label>Specialty <select id="sp"><option value="">All</option>${specs.map(s => `<option>${s}</option>`).join('')}</select></label><button class="btn" id="dl" type="button">Download CSV</button></div>
  <div id="fig-dorm"></div>${take(D.takeaways.dormant)}<div id="tb"></div>`;
  const cols = [{k: 'priority_rank', l: '#'}, {k: 'name', l: 'Agency'}, {k: 'owner', l: 'Owner'}, {k: 'state', l: 'State'}, {k: 'specialty_focus', l: 'Specialty'}, {k: 'days_dormant', l: 'Days dormant'},
    {k: 'prior_complete_submissions', l: 'Prior submissions'}, {k: 'prior_bound_premium', l: 'Prior bound premium', f: v => money(v)}, {k: 'score', l: 'Fit score', f: v => v.toFixed(2)}];
  const sel = () => d.filter(r => !$('#sp').value || r.specialty_focus === $('#sp').value);
  const draw = () => { $('#tv').textContent = $('#tn').value; const s = sel(), top = s.slice(0, +$('#tn').value);
    plot('fig-dorm', [{type: 'bar', orientation: 'h', y: top.map(r => r.name).reverse(), x: top.map(r => r.prior_bound_premium).reverse(), marker: {color: C.blue}, hovertemplate: '%{y}<br>prior bound premium: $%{x:,.0f}<extra></extra>'}],
      lay(Math.max(320, 22 * top.length + 80), {margin: {l: 260, r: 12, t: 10, b: 40}, xaxis: {title: 'Prior bound premium (USD)', gridcolor: C.grid}}));
    $('#tb').innerHTML = table(s.slice(0, 100), cols) + (s.length > 100 ? `<p class="small">Showing 100 of ${s.length}; download the CSV for all.</p>` : ''); };
  ['tn', 'sp'].forEach(i => $('#' + i).addEventListener('input', draw)); $('#dl').addEventListener('click', () => download('dormant_agencies.csv', sel(), cols)); draw();
};

V.pipeline = function () {
  const p = D.pipeline;
  view.innerHTML = `<h2>Pipeline and Revenue Projection by Segment</h2><details class="card"><summary>Assumptions behind this projection</summary><ul><li>Open (pending) pipeline = agencies whose highest stage is ICP, engaged, first submission or quoted and that reached it within the maturity window of the next step; older ones are treated as lost.</li>
  <li>Each converts at the product of its segment's remaining cohort-mature step rates; the overall rate is used when a segment has fewer than ${D.meta.min_n} agencies at that stage.</li><li>Revenue per bound agency = observed average first-bind commission. Repeat revenue is excluded. A projection from synthetic rates, not a forecast.</li></ul></details>
  <div class="ctl">${p.map(r => `<label><input type="checkbox" class="sg" value="${esc(r.segment)}" checked> ${esc(r.segment)}</label>`).join('')}</div><div class="kpis" id="pk"></div>
  <div id="fig-pipe"></div><div id="fig-pcom"></div>${take(D.takeaways.pipeline)}<div id="tb"></div>`;
  const draw = () => { const on = [...document.querySelectorAll('.sg')].filter(c => c.checked).map(c => c.value), s = p.filter(r => on.includes(r.segment)).sort((a, b) => a.projected_commission - b.projected_commission);
    const sum = k => s.reduce((t, r) => t + r[k], 0);
    $('#pk').innerHTML = kpi('Expected new bound agencies', sum('expected_new_bound_agencies').toFixed(0)) + kpi('Projected first-bind commission', money(sum('projected_commission'))) + kpi('Projected bound premium', money(sum('projected_premium')));
    const st = [['open_icp', 'ICP-qualified', C.sky], ['open_engaged', 'Engaged', C.mint], ['open_first_submission', 'First submission', C.blue], ['open_quoted', 'Quoted', C.green]];
    plot('fig-pipe', st.map(([k, n, c]) => ({type: 'bar', orientation: 'h', y: s.map(r => r.segment), x: s.map(r => r[k]), name: n, marker: {color: c}})), lay(340, {barmode: 'stack', margin: {l: 150, r: 12, t: 10, b: 50}, xaxis: {title: 'Open agencies by stage', gridcolor: C.grid}}));
    plot('fig-pcom', [{type: 'bar', orientation: 'h', y: s.map(r => r.segment), x: s.map(r => r.projected_commission), marker: {color: C.green}}], lay(300, {margin: {l: 150, r: 12, t: 10, b: 50}, xaxis: {title: 'Projected first-bind commission (USD)', gridcolor: C.grid}}));
    $('#tb').innerHTML = table(s.slice().reverse(), [{k: 'segment', l: 'Segment'}, {k: 'expected_new_bound_agencies', l: 'Expected bound', f: v => v.toFixed(1)}, {k: 'avg_first_bind_commission', l: 'Avg first-bind commission', f: v => money(v)}, {k: 'projected_commission', l: 'Projected commission', f: v => money(v)}, {k: 'projected_premium', l: 'Projected premium', f: v => money(v)}]); };
  document.querySelectorAll('.sg').forEach(c => c.addEventListener('input', draw)); draw();
};

V.ranked = function () {
  const r0 = D.ranked, owners = [...new Set(r0.map(r => r.owner))].sort(), states = [...new Set(r0.map(r => r.state))].sort(), tiers = ['Tier 1', 'Tier 2', 'Tier 3', 'Active', 'Reactivation'];
  view.innerHTML = `<h2>Ranked Accounts</h2><div id="fig-tier"></div>${take(D.takeaways.ranked)}
  <div class="card"><b>Out-of-sample check.</b> Prospects scored ${D.holdout[0].window_days} days before the as-of date (${D.holdout[0].scored_as_of}) using only data available then; first submissions counted in the following ${D.holdout[0].window_days} days.
  ${table(D.holdout, [{k: 'tier', l: 'Tier'}, {k: 'prospects', l: 'Prospects'}, {k: 'converted', l: 'Converted'}, {k: 'rate', l: 'Conversion', f: v => v == null ? 'suppressed (n small)' : pct(v)}])}
  <p class="small">Tiers 1-3 contain prospects only; customers are Active or Reactivation. Engagement counts opens, clicks, replies and meetings, never submissions. On synthetic data this checks plumbing, not real predictive power.</p></div>
  <p class="small">Score = 0.30 specialty fit + 0.25 commercial volume + 0.20 E&amp;S activity + 0.15 engagement + 0.10 geographic priority. Every reason names the top two drivers.</p>
  <div class="ctl">${tiers.map((t, i) => `<label><input type="checkbox" class="tr" value="${t}" ${i < 2 ? 'checked' : ''}> ${t}</label>`).join('')}</div>
  <div class="ctl"><label>Owner <select id="ow"><option value="">All</option>${owners.map(o => `<option>${esc(o)}</option>`).join('')}</select></label><label>State <select id="stt"><option value="">All</option>${states.map(o => `<option>${o}</option>`).join('')}</select></label>
  <label>Min score <input type="range" id="ms" min="0" max="1" step="0.05" value="0"> <b id="mv">0.00</b></label><input type="search" id="q" placeholder="Search name" aria-label="Search name"><button class="btn" id="dl" type="button">Download CSV</button></div>
  <div id="cnt" class="small"></div><div id="tb"></div><div class="pg"><button class="btn" id="pv" type="button">Previous</button><span id="pn"></span><button class="btn" id="nx" type="button">Next</button></div>`;
  const vc = tiers.map(t => r0.filter(r => r.tier === t).length);
  plot('fig-tier', [{type: 'bar', x: tiers, y: vc, marker: {color: [C.green, C.blue, C.muted, C.teal, C.sky]}, text: vc, textposition: 'outside'}], lay(240));
  const cols = [{k: 'name', l: 'Agency'}, {k: 'score', l: 'Score', f: v => v.toFixed(2)}, {k: 'tier', l: 'Tier'}, {k: 'next_action', l: 'Next action'}, {k: 'owner', l: 'Owner'}, {k: 'channel', l: 'Channel'}, {k: 'reason', l: 'Reason'}];
  let page = 0; const PS = 20;
  const sel = () => { const on = [...document.querySelectorAll('.tr')].filter(c => c.checked).map(c => c.value), q = $('#q').value.toLowerCase();
    return r0.filter(r => on.includes(r.tier) && r.score >= +$('#ms').value && (!$('#ow').value || r.owner === $('#ow').value) && (!$('#stt').value || r.state === $('#stt').value) && (!q || r.name.toLowerCase().includes(q))); };
  const draw = () => { $('#mv').textContent = (+$('#ms').value).toFixed(2); const s = sel(), pages = Math.max(1, Math.ceil(s.length / PS)); page = Math.min(page, pages - 1);
    $('#cnt').textContent = fmt(s.length) + ' accounts match'; $('#tb').innerHTML = table(s.slice(page * PS, page * PS + PS), cols); $('#pn').textContent = 'Page ' + (page + 1) + ' of ' + pages;
    $('#pv').disabled = page === 0; $('#nx').disabled = page >= pages - 1; };
  ['ow', 'stt', 'ms', 'q'].forEach(i => $('#' + i).addEventListener('input', () => { page = 0; draw(); })); document.querySelectorAll('.tr').forEach(c => c.addEventListener('input', () => { page = 0; draw(); }));
  $('#pv').addEventListener('click', () => { page--; draw(); }); $('#nx').addEventListener('click', () => { page++; draw(); }); $('#dl').addEventListener('click', () => download('ranked_accounts_filtered.csv', sel(), cols)); draw();
};

V.experiments = function () {
  const e = D.experiments, S = D.sweep;
  view.innerHTML = `<h2>Experiments</h2><div class="banner"><b>SIMULATED results on synthetic data.</b> They demonstrate the method; the generator planted the effects (A +30%, B +15%, C 0).</div>
  <p class="small">${esc(D.meta.exp_note)}</p><div class="ctl">${seg('et', e.map(r => [r.id, r.id + ': ' + r.name]), e[0].id)}</div><div id="ecard"></div><div id="fig-exp"></div>
  <h3>Decision rates across ${S.n_seeds} simulated seeds</h3><div class="tw"><table><thead><tr><th>Experiment</th><th>SHIP</th><th>ITERATE</th><th>INCONCLUSIVE</th><th>Significant (p&lt;0.05)</th><th>Mean lift</th></tr></thead><tbody>
  ${['A', 'B', 'C'].map(k => `<tr><td>${k}</td><td>${S[k].decisions.SHIP || 0}</td><td>${S[k].decisions.ITERATE || 0}</td><td>${S[k].decisions.INCONCLUSIVE || 0}</td><td>${S[k]['significant_p_lt_0.05']}</td><td>${pct(S[k].mean_rel_lift)}</td></tr>`).join('')}</tbody></table></div>
  <h3>Sample-size calculator</h3><p class="small">How many agencies per arm would a real test need? Same two-proportion formula as the framework.</p>
  <div class="card"><div class="calc"><div><label for="c-base">Baseline rate: <b id="o-base"></b></label><input id="c-base" type="range" min="2" max="60" value="10"></div>
  <div><label for="c-lift">Relative lift to detect: <b id="o-lift"></b></label><input id="c-lift" type="range" min="5" max="60" value="20"></div>
  <div><label for="c-alpha">Alpha</label><select id="c-alpha"><option value="1.6449">0.10</option><option value="1.96" selected>0.05</option><option value="2.5758">0.01</option></select></div>
  <div><label for="c-power">Power</label><select id="c-power"><option value="0.8416" selected>80%</option><option value="1.2816">90%</option><option value="1.6449">95%</option></select></div></div>
  <p>Required per arm: <span class="result" id="o-n" aria-live="polite"></span> &nbsp; Total: <b id="o-tot"></b></p></div>`;
  const card = id => { const r = e.find(x => x.id === id); $('#ecard').innerHTML = `<div class="card"><h3>${esc(r.name)} ${badge(r.decision)}</h3><p>Control ${pct(r.rate_control)} &rarr; treatment ${pct(r.rate_treatment)}; relative lift <b>${(r.rel_lift * 100).toFixed(1)}%</b> (95% CI ${(r.ci_low * 100).toFixed(1)}% to ${(r.ci_high * 100).toFixed(1)}%), p ${r.p_value < 0.001 ? '< 0.001' : '= ' + r.p_value.toFixed(3)}.</p>
    <div class="bar"><span style="width:${Math.min(100, 100 * Math.min(r.n_control, r.n_treatment) / r.n_required)}%"></span></div><p class="small">Sample: ${fmt(Math.min(r.n_control, r.n_treatment))} per arm of ${fmt(r.n_required)} required. Power at the pre-registered ${(r.mde * 100).toFixed(0)}% lift: ${pct(r.power, 0)}.${r.ci_clears ? '' : ' The lower CI bound (' + (r.ci_low * 100).toFixed(1) + '%) is below the ' + (r.mde * 100).toFixed(0) + '% ship threshold; the rule ships on the point estimate (winner\'s-curse risk).'} Planted truth: ${(r.planted * 100).toFixed(0)}%. Simulated.</p>${take(r.take)}</div>`; };
  card(e[0].id); onSeg('et', card);
  const labs = e.map(r => r.id + ': ' + r.name + ' (' + r.decision + ')');
  plot('fig-exp', e.map((r, i) => ({type: 'scatter', mode: 'markers', x: [r.rel_lift * 100], y: [labs[i]], showlegend: false, marker: {size: 11, color: C.blue}, error_x: {type: 'data', symmetric: false, array: [(r.ci_high - r.rel_lift) * 100], arrayminus: [(r.rel_lift - r.ci_low) * 100], color: C.blue}, hovertemplate: labs[i] + '<br>lift %{x:.1f}%<extra></extra>'}))
    .concat(e.map((r, i) => ({type: 'scatter', mode: 'markers', x: [r.planted * 100], y: [labs[i]], showlegend: false, hoverinfo: 'skip', marker: {symbol: 'line-ns', size: 22, color: C.green, line: {width: 3, color: C.green}}}))),
    lay(260, {margin: {l: 300, r: 12, t: 10, b: 50}, xaxis: {title: 'Relative lift, % (blue = estimate with 95% CI, green tick = planted truth)', gridcolor: C.grid, zeroline: true}}));
  const z = id => parseFloat($('#' + id).value);
  const calc = () => { const p1 = z('c-base') / 100, lift = z('c-lift') / 100, p2 = Math.min(0.99, p1 * (1 + lift)), za = z('c-alpha'), zb = z('c-power'), pb = (p1 + p2) / 2;
    const n = Math.ceil(Math.pow(za * Math.sqrt(2 * pb * (1 - pb)) + zb * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)), 2) / Math.pow(p1 - p2, 2));
    $('#o-base').textContent = (p1 * 100).toFixed(0) + '%'; $('#o-lift').textContent = '+' + (lift * 100).toFixed(0) + '%'; $('#o-n').textContent = fmt(n); $('#o-tot').textContent = fmt(2 * n); };
  ['c-base', 'c-lift', 'c-alpha', 'c-power'].forEach(i => $('#' + i).addEventListener('input', calc)); calc();
};

const ORDER = [['monday', 'Monday Morning'], ['weekly', 'Weekly Growth Review'], ['sources', 'Source Quality'], ['ttq', 'Time-to-Quote'], ['activation', 'Activation & Cohorts'],
  ['dormant', 'Dormancy & Reactivation'], ['pipeline', 'Pipeline & Revenue'], ['ranked', 'Ranked Accounts'], ['experiments', 'Experiments']];
$('#tabs').innerHTML = ORDER.map(o => `<a href="#${o[0]}" data-v="${o[0]}">${o[1]}</a>`).join('');
function route() { const h = (location.hash || '#monday').slice(1), id = V[h] ? h : 'monday';
  document.querySelectorAll('#tabs a').forEach(a => a.classList.toggle('active', a.dataset.v === id)); view.innerHTML = ''; V[id](); document.title = ORDER.find(o => o[0] === id)[1] + ' | Broker Growth OS'; }
window.addEventListener('hashchange', () => { route(); window.scrollTo({top: 0}); }); route();
"""


def _records(df: pd.DataFrame, cols=None) -> list:
    d = df[cols] if cols else df
    return json.loads(d.to_json(orient="records", double_precision=6))


def build_data(root: Path | str | None = None) -> dict:
    paths = config.get_paths(root)
    m = lambda n: pd.read_csv(paths.marts / f"{n}.csv")
    f, sq, wk, ex, tl = m("funnel_counts").sort_values("stage_order"), m("source_quality"), m("weekly_growth_review"), m("experiment_results"), m("topline")
    act, coh, ttq, dor, pp = m("activation_rate"), m("cohort_retention"), m("time_to_quote"), m("dormant_reactivation"), m("pipeline_projection")
    ranked = pd.read_csv(paths.marts / "ranked_accounts.csv")
    sweep = json.loads((config.ROOT / "docs" / "seed_sweep.json").read_text())["summary"]
    exps = []
    for _, r in ex.iterrows():
        exps.append(dict(id=r.experiment_id, name=r["name"], decision=r.decision, rate_control=r.rate_control, rate_treatment=r.rate_treatment, rel_lift=r.rel_lift,
                         ci_low=r.rel_ci_low, ci_high=r.rel_ci_high, p_value=r.p_value, n_control=int(r.n_control), n_treatment=int(r.n_treatment),
                         n_required=int(r.n_required_per_arm), power=r.power_at_mde, mde=r.mde_relative, ci_clears=bool(r.ci_low_clears_ship), planted=r.planted_true_lift, take=ins.takeaway_experiment(r)))
    note = ("Each result below is one simulated draw. Running three experiments at once carries a multiple comparisons risk; no alpha adjustment is applied. "
            f"Across {sweep['n_seeds']} simulated seeds: A ships in {sweep['A']['decisions'].get('SHIP', 0)}, B in {sweep['B']['decisions'].get('SHIP', 0)}, "
            f"and C looks significant by chance in {sweep['C']['significant_p_lt_0.05']}.")
    return {
        "meta": {"min_n": config.MIN_N, "exp_note": note},
        "stage_names": {k: v.name for k, v in STAGE_BY_KEY.items()},
        "topline": _records(tl)[0], "funnel": _records(f), "sources": _records(sq), "weekly": _records(wk), "ttq": _records(ttq),
        "activation": _records(act), "cohorts": _records(coh), "dormant": _records(dor), "pipeline": _records(pp),
        "ranked": _records(ranked, ["name", "score", "tier", "next_action", "owner", "channel", "reason", "state", "action"]),
        "experiments": exps, "sweep": sweep, "holdout": _records(pd.read_csv(paths.marts / "tier_holdout.csv")),
        "takeaways": {"funnel": ins.takeaway_funnel(f), "north_star": ins.takeaway_north_star(wk), "sources": ins.takeaway_sources(sq), "ttq": ins.takeaway_ttq(ttq),
                      "activation": ins.takeaway_activation(act, coh), "dormant": ins.takeaway_dormant(dor), "pipeline": ins.takeaway_pipeline(pp), "ranked": ins.takeaway_ranked(ranked)},
    }


def _page(title: str, body: str, script: str = "", plotly: bool = False) -> str:
    cdn = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>' if plotly else ""
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{title}</title><meta name="theme-color" content="{theme.BLUE_DARK}">\n<style>{CSS}</style>{cdn}</head><body>\n{body}\n{script}</body></html>\n')


def build_site(root: Path | str | None = None) -> str:
    """Home page = the interactive dashboard only (no memo). Data is embedded; charts render in the browser."""
    paths = config.get_paths(root)
    data = round_obj(build_data(root))
    facts = docs.memo_facts(root)
    f = pd.read_csv(paths.marts / "funnel_counts.csv").set_index("stage")
    kp = [("Raw leads", facts["raw"], ""), ("ICP-qualified", facts["icp"], ""), ("Engaged", facts["engaged"], ""), ("First submissions", facts["first_sub"], ""),
          ("Bound", facts["bound"], f"{facts['bound_pct']} of mature leads ({facts['bound_obs_pct']} raw)")]
    kpis = "".join(f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{k}</div>" + (f"<div class='d'>{d}</div>" if d else "") + "</div>" for k, v, d in kp)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    body = f"""<a class="skip" href="#view">Skip to dashboard</a>
<header class="top"><div class="in"><div><h1>Broker Growth OS</h1><p>Interactive growth dashboard: funnel, fit scoring, metrics and experiments for a specialty insurance wholesaler.</p></div>
<div class="links"><a href="memo.html">Strategy memo</a><a href="{REPO}">GitHub</a></div></div></header>
<nav aria-label="Dashboard views"><div class="in" id="tabs"></div></nav>
<main><div class="banner" role="note"><b>{docs.DISCLAIMER}</b> Every number here comes from a generated synthetic dataset; experiment results are simulated. Use the controls on each view to filter and explore.</div>
<div class="kpis" aria-label="Headline funnel numbers">{kpis}</div><div id="view"></div></main>
<footer>Synthetic data. Experiment results are simulated and demonstrate the method only. &middot; <a href="memo.html">Strategy memo</a> &middot; <a href="{REPO}">Source code</a><br><span class="fp" id="fingerprint">{docs.stamp(root)}</span></footer>
<script id="data" type="application/json">{payload}</script>"""
    return _page("Broker Growth OS", body, f"<script>{JS}</script>", plotly=True)


def build_memo_page(root: Path | str | None = None) -> str:
    paths = config.get_paths(root)
    facts = docs.memo_facts(root)
    memo = _md((paths.root / "STRATEGY_MEMO.md").read_text()) if (paths.root / "STRATEGY_MEMO.md").exists() else _md(docs.build_memo(facts))
    body = f"""<header class="top"><div class="in"><div><h1>Strategy memo</h1><p>Broker Growth OS: growth thesis, funnel, gaps found in the synthetic baseline, and a 90-day plan.</p></div>
<div class="links"><a href="index.html">&larr; Back to the dashboard</a><a href="{REPO}">GitHub</a></div></div></header>
<main><div class="banner" role="note"><b>{docs.DISCLAIMER}</b> Every number below comes from the generated synthetic outputs.</div>
<div class="card memo">{memo}</div>
<h3>More</h3><ul><li><a href="{REPO}/blob/main/README.md">README and quickstart</a></li><li><a href="{REPO}/blob/main/AUDIT_REPORT.md">Independent audit report</a></li>
<li><a href="{REPO}/blob/main/DECISIONS.md">Decision log</a></li><li><a href="{REPO}/blob/main/DEPLOY.md">Run the Streamlit version locally or deploy it</a></li></ul></main>
<footer>Synthetic data. Demonstrates the method, not Hedge's actual performance.<br><span class="fp" id="fingerprint">{docs.stamp(root)}</span></footer>"""
    return _page("Strategy memo | Broker Growth OS", body)


def run_site(root: Path | str | None = None) -> Path:
    paths = config.get_paths(root)
    out = paths.root / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_site(root))
    (paths.root / "docs" / "memo.html").write_text(build_memo_page(root))
    return out
