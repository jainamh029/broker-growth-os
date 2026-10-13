"""Shared green-and-blue visual theme for the Streamlit dashboard and the static showcase page."""

INK = "#0f172a"        # text
BLUE = "#2563eb"       # primary
BLUE_DARK = "#0b1b33"
GREEN = "#0f766e"      # secondary / positive
GREEN_DARK = "#115e59"
TEAL = "#0891b2"
SKY = "#93c5fd"
MINT = "#99d9cf"
MUTED = "#475569"
GRID = "#e2e8f0"
SURFACE = "#eef2f7"   # callouts / table headers
BG = "#f3f5f8"        # page background (soft mint)
BG2 = "#eceff5"       # page background gradient end (soft blue)
CARD = "#ffffff"      # card / control background (slightly lighter than the page)
AMBER = "#b45309"      # warnings / negative only
COLORWAY = [BLUE, GREEN, TEAL, SKY, MINT, AMBER]

# NOTE: colours with alpha use #rrggbbaa so no comma-separated numbers appear in source.
APP_CSS = f"""
<style>
:root {{ --ink:{INK}; --blue:{BLUE}; --green:{GREEN}; --surface:{SURFACE}; --grid:{GRID}; }}
.stApp {{ background: linear-gradient(160deg, {BG} 0%, {BG2} 100%); }}
.block-container {{ padding-top: 1rem; max-width: 1240px; }}
.hero {{ background: linear-gradient(120deg, #0b1b33 0%, #10294d 60%, #134e4a 100%); color:#fff; border-radius:16px;
         padding: 22px 26px; margin-bottom: 12px; box-shadow: 0 8px 24px #0b1b3333; }}
.hero h1 {{ color:#fff; font-size:1.75rem; margin:0 0 4px 0; padding:0; letter-spacing:-0.01em; }}
.hero p {{ color:#e6f4ee; margin:0; font-size:.98rem; }}
.hero .pill {{ display:inline-block; background:#ffffff26; border:1px solid #ffffff55; border-radius:999px; padding:2px 12px;
               font-size:.78rem; margin-right:6px; margin-top:10px; }}
.banner {{ background:#fff7e0; border:1px solid #e8c766; color:#5b4500; padding:.55rem .9rem; border-radius:10px; font-size:.92rem; margin-bottom:.9rem; }}
.takeaway {{ border-left:4px solid {GREEN}; background:{SURFACE}; border-radius:0 10px 10px 0; padding:.6rem .9rem; margin:.3rem 0 1.2rem 0; color:{INK}; }}
div[data-testid="stMetric"] {{ background:{CARD}; border:1px solid {GRID}; border-radius:14px; padding:14px 16px;
        box-shadow: 0 1px 2px #0f172a0f; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }}
div[data-testid="stMetric"]:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px #0f172a1f; border-color:{GREEN}; }}
div[data-testid="stMetricLabel"] p {{ white-space: normal; font-size:.85rem; }}
div[data-testid="stMetricValue"] {{ color:{BLUE_DARK}; }}
section[data-testid="stSidebar"] {{ background:#ffffff; border-right:1px solid {GRID}; }}
h2, h3 {{ color:{BLUE_DARK}; letter-spacing:-0.005em; }}
button[kind="primary"], .stDownloadButton button {{ border-radius:10px; }}
.stDownloadButton button {{ border:1px solid {GREEN}; color:{GREEN_DARK}; background:{CARD}; min-height:44px; }}
.stDownloadButton button:hover {{ background:{GREEN}; color:#fff; border-color:{GREEN}; }}
button:focus-visible, a:focus-visible {{ outline:3px solid {BLUE}; outline-offset:2px; }}
.footer {{ color:{MUTED}; font-size:.85rem; margin-top:2rem; border-top:1px solid {GRID}; padding-top:.7rem; }}
@media (prefers-reduced-motion: reduce) {{ div[data-testid="stMetric"] {{ transition:none; }} div[data-testid="stMetric"]:hover {{ transform:none; }} }}
</style>
"""
