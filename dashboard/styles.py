"""Shared dark-theme CSS injected into every dashboard page."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700&family=Fira+Code:wght@400;500;600&display=swap');

/* ── Tokens ────────────────────────────────────────────────────── */
:root {
    --bg:       #0D1117;
    --surface:  #161B22;
    --surface2: #1C2333;
    --border:   #30363D;
    --primary:  #3B82F6;
    --accent:   #D97706;
    --success:  #22C55E;
    --danger:   #EF4444;
    --text:     #E6EDF3;
    --muted:    #8B949E;
    --radius:   10px;
}

/* ── App shell ─────────────────────────────────────────────────── */
.stApp, .main .block-container {
    background: var(--bg) !important;
    font-family: 'Inter', sans-serif;
    color: var(--text);
}
.block-container { padding-top: 2rem !important; }

/* ── Sidebar ────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text) !important; }
[data-testid="stSidebarNav"] a {
    border-radius: 6px;
    transition: background 0.15s;
}
[data-testid="stSidebarNav"] a:hover { background: var(--surface2) !important; }

/* ── Typography ─────────────────────────────────────────────────── */
h1, h2, h3, h4, p, li, span, label, div {
    color: var(--text) !important;
}
h1 { font-size: 1.75rem !important; font-weight: 700 !important; letter-spacing: -0.02em; }
h2 { font-size: 1.25rem !important; font-weight: 600 !important; }
h3 { font-size: 1rem   !important; font-weight: 600 !important; }

/* ── Inputs / selects ───────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
.stTextInput input {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text) !important;
}

/* ── Dataframe ──────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden;
}
[data-testid="stDataFrame"] th {
    background: var(--surface2) !important;
    color: var(--muted) !important;
    font-size: 11px !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    font-weight: 600 !important;
}
[data-testid="stDataFrame"] td {
    background: var(--surface) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
    font-size: 13px !important;
}

/* ── Buttons ────────────────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button {
    background: var(--primary) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    padding: 8px 18px !important;
    transition: opacity 0.15s !important;
    cursor: pointer !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    opacity: 0.85 !important;
}

/* ── Info / alert boxes ─────────────────────────────────────────── */
.stAlert {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text) !important;
}

/* ── Divider ────────────────────────────────────────────────────── */
hr { border-color: var(--border) !important; opacity: 0.6; }

/* ── KPI cards ──────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
}
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 22px 16px;
    position: relative;
    overflow: hidden;
}
.kpi-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    border-radius: var(--radius) var(--radius) 0 0;
}
.kpi-card.blue::after  { background: var(--primary); }
.kpi-card.green::after { background: var(--success); }
.kpi-card.amber::after { background: var(--accent); }
.kpi-card.red::after   { background: var(--danger); }
.kpi-card.purple::after{ background: #8B5CF6; }
.kpi-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted) !important;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 26px;
    font-weight: 700;
    font-family: 'Fira Code', monospace;
    color: var(--text) !important;
    line-height: 1.15;
}
.kpi-value.pos { color: var(--success) !important; }
.kpi-value.neg { color: var(--danger)  !important; }
.kpi-sub {
    font-size: 11px;
    color: var(--muted) !important;
    margin-top: 4px;
}

/* ── Section header ─────────────────────────────────────────────── */
.section-hd {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted) !important;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
    margin: 28px 0 14px;
}

/* ── Info band ──────────────────────────────────────────────────── */
.info-band {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 24px;
}
.info-tile {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 18px;
}
.info-tile .lbl { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted) !important; margin-bottom: 4px; }
.info-tile .val { font-size: 15px; font-weight: 600; color: var(--text) !important; }

/* ── Calendar ───────────────────────────────────────────────────── */
.cal-day-header {
    text-align: center;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted) !important;
    padding: 6px 0;
}
.cal-cell {
    border-radius: 8px;
    padding: 6px 4px;
    text-align: center;
    min-height: 64px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    border: 1px solid transparent;
    margin: 2px;
}
.cal-cell.empty   { background: rgba(22,27,34,0.4); }
.cal-cell.no-data { background: var(--surface); border-color: var(--border); }
.cal-cell.profit  { background: rgba(34,197,94,0.10); border-color: rgba(34,197,94,0.3); }
.cal-cell.loss    { background: rgba(239,68,68,0.10); border-color: rgba(239,68,68,0.3); }
.cal-num  { font-size: 14px; font-weight: 700; color: var(--text) !important; }
.cal-pnl  { font-family: 'Fira Code', monospace; font-size: 11px; margin-top: 3px; }
.cal-pnl.pos { color: var(--success) !important; }
.cal-pnl.neg { color: var(--danger)  !important; }
.cal-cnt  { font-size: 10px; color: var(--muted) !important; margin-top: 1px; }

/* ── Direction badges ───────────────────────────────────────────── */
.dir-buy  { color: #60A5FA !important; font-weight: 700; font-family: 'Fira Code', monospace; font-size: 12px; }
.dir-sell { color: #F87171 !important; font-weight: 700; font-family: 'Fira Code', monospace; font-size: 12px; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)
