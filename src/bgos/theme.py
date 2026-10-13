"""Shared green-and-blue visual theme for the Streamlit dashboard and the static showcase page."""

INK = "#0b2a3c"        # text
BLUE = "#1456a0"       # primary
BLUE_DARK = "#0b3a6b"
GREEN = "#0f7a55"      # secondary / positive
GREEN_DARK = "#0a5c40"
TEAL = "#0e7490"
SKY = "#7fb2e5"
MINT = "#8fd1b3"
MUTED = "#5b7083"
GRID = "#d5e3df"
SURFACE = "#eef6f4"
AMBER = "#b45f06"      # warnings / negative only
COLORWAY = [BLUE, GREEN, TEAL, SKY, MINT, AMBER]

# NOTE: colours with alpha use #rrggbbaa so no comma-separated numbers appear in source.
APP_CSS = f"""
<style>
:root {{ --ink:{INK}; --blue:{BLUE}; --green:{GREEN}; --surface:{SURFACE}; --grid:{GRID}; }}
.block-container {{ padding-top: 1rem; max-width: 1240px; }}
.hero {{ background: linear-gradient(120deg, {BLUE_DARK} 0%, {BLUE} 45%, {GREEN} 100%); color:#fff; border-radius:16px;
         padding: 22px 26px; margin-bottom: 12px; box-shadow: 0 8px 24px #0b3a6b26; }}
.hero h1 {{ color:#fff; font-size:1.75rem; margin:0 0 4px 0; padding:0; letter-spacing:-0.01em; }}
.hero p {{ color:#e6f4ee; margin:0; font-size:.98rem; }}
.hero .pill {{ display:inline-block; background:#ffffff26; border:1px solid #ffffff55; border-radius:999px; padding:2px 12px;
               font-size:.78rem; margin-right:6px; margin-top:10px; }}
.banner {{ background:#fff7e0; border:1px solid #e8c766; color:#5b4500; padding:.55rem .9rem; border-radius:10px; font-size:.92rem; margin-bottom:.9rem; }}
.takeaway {{ border-left:4px solid {GREEN}; background:{SURFACE}; border-radius:0 10px 10px 0; padding:.6rem .9rem; margin:.3rem 0 1.2rem 0; color:{INK}; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid {GRID}; border-radius:14px; padding:14px 16px;
        box-shadow: 0 1px 2px #0b2a3c0f; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }}
div[data-testid="stMetric"]:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px #0b2a3c1f; border-color:{GREEN}; }}
div[data-testid="stMetricLabel"] p {{ white-space: normal; font-size:.85rem; }}
div[data-testid="stMetricValue"] {{ color:{BLUE_DARK}; }}
section[data-testid="stSidebar"] {{ background:{SURFACE}; border-right:1px solid {GRID}; }}
h2, h3 {{ color:{BLUE_DARK}; letter-spacing:-0.005em; }}
button[kind="primary"], .stDownloadButton button {{ border-radius:10px; }}
.stDownloadButton button {{ border:1px solid {GREEN}; color:{GREEN_DARK}; background:#fff; min-height:44px; }}
.stDownloadButton button:hover {{ background:{GREEN}; color:#fff; border-color:{GREEN}; }}
button:focus-visible, a:focus-visible {{ outline:3px solid {BLUE}; outline-offset:2px; }}
.footer {{ color:{MUTED}; font-size:.85rem; margin-top:2rem; border-top:1px solid {GRID}; padding-top:.7rem; }}
@media (prefers-reduced-motion: reduce) {{ div[data-testid="stMetric"] {{ transition:none; }} div[data-testid="stMetric"]:hover {{ transform:none; }} }}
</style>
"""
