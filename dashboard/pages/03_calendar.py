import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
import calendar
from database.db import get_connection

st.set_page_config(page_title="Calendar · Trading Bot", layout="wide")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from styles import inject_css
inject_css()


# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_daily_pnl():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DATE(timestamp) as trade_date,
                   SUM(pnl)        as daily_pnl,
                   COUNT(*)        as trade_count
            FROM trades
            WHERE pnl IS NOT NULL
            GROUP BY DATE(timestamp)
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def fetch_trades_on_date(date_str: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM trades WHERE DATE(timestamp) = ? ORDER BY id ASC
        """, (date_str,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


rows     = fetch_daily_pnl()
pnl_map  = {r["trade_date"]: r["daily_pnl"]    for r in rows}
cnt_map  = {r["trade_date"]: r["trade_count"]   for r in rows}


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<h1 style="margin-bottom:4px">Calendar</h1>
<p style="color:#8B949E;font-size:13px;margin-top:0">Daily P&amp;L heatmap — green = profit, red = loss</p>
""", unsafe_allow_html=True)


# ── Month / Year selector ─────────────────────────────────────────────────────

today = pd.Timestamp.now()
c_y, c_m, _ = st.columns([1, 2, 4])
with c_y:
    year  = st.number_input("Year",  min_value=2020, max_value=2035, value=today.year,  label_visibility="collapsed")
with c_m:
    month = st.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                         format_func=lambda m: calendar.month_name[m],
                         label_visibility="collapsed")

# Month-level summary
month_days = [d for d in pnl_map if d.startswith(f"{year:04d}-{month:02d}")]
month_pnl  = sum(pnl_map[d] for d in month_days)
month_sign = "+" if month_pnl >= 0 else ""
month_cls  = "pos" if month_pnl >= 0 else "neg"

st.markdown(f"""
<div style="display:flex;align-items:center;gap:8px;margin:4px 0 20px">
  <span style="font-size:20px;font-weight:700;color:#E6EDF3">
    {calendar.month_name[month]} {year}
  </span>
  <span style="font-family:'Fira Code',monospace;font-size:16px;
               color:{'#22C55E' if month_pnl >= 0 else '#EF4444'};font-weight:600">
    {month_sign}${month_pnl:,.2f}
  </span>
  <span style="font-size:12px;color:#8B949E">{len(month_days)} trading days</span>
</div>
""", unsafe_allow_html=True)


# ── Calendar grid ─────────────────────────────────────────────────────────────

cal  = calendar.monthcalendar(year, month)
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Day headers
hcols = st.columns(7)
for i, d in enumerate(days):
    hcols[i].markdown(f'<div class="cal-day-header">{d}</div>', unsafe_allow_html=True)

# Weeks
for week in cal:
    wcols = st.columns(7)
    for i, day in enumerate(week):
        if day == 0:
            wcols[i].markdown('<div class="cal-cell empty"></div>', unsafe_allow_html=True)
            continue

        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        pnl      = pnl_map.get(date_str)
        cnt      = cnt_map.get(date_str, 0)

        if pnl is None:
            cell_class = "no-data"
            pnl_html   = '<div class="cal-pnl" style="color:#30363D;font-size:10px">no trades</div>'
        elif pnl >= 0:
            cell_class = "profit"
            pnl_html   = f'<div class="cal-pnl pos">+${pnl:.0f}</div><div class="cal-cnt">{cnt} trade{"s" if cnt != 1 else ""}</div>'
        else:
            cell_class = "loss"
            pnl_html   = f'<div class="cal-pnl neg">-${abs(pnl):.0f}</div><div class="cal-cnt">{cnt} trade{"s" if cnt != 1 else ""}</div>'

        today_border = 'border-color:#3B82F6 !important;' if (
            day == today.day and month == today.month and year == today.year
        ) else ''

        wcols[i].markdown(
            f'<div class="cal-cell {cell_class}" style="{today_border}">'
            f'<div class="cal-num">{day}</div>{pnl_html}</div>',
            unsafe_allow_html=True,
        )


# ── Day drill-down ────────────────────────────────────────────────────────────

st.markdown('<div class="section-hd">Day Detail</div>', unsafe_allow_html=True)

d_col, _ = st.columns([1, 5])
with d_col:
    sel_day = st.number_input("Select day", min_value=1, max_value=31,
                              value=today.day, label_visibility="collapsed")

sel_date   = f"{year:04d}-{month:02d}-{sel_day:02d}"
day_trades = fetch_trades_on_date(sel_date)

if day_trades:
    day_df = pd.DataFrame(day_trades)
    cols   = [c for c in ["timestamp", "symbol", "direction", "size", "entry_price", "pnl", "status"] if c in day_df.columns]

    if "pnl" in day_df.columns:
        day_df["pnl"] = day_df["pnl"].apply(
            lambda v: f"+${v:,.2f}" if isinstance(v, (int, float)) and not pd.isna(v) and v > 0
            else (f"-${abs(v):,.2f}" if isinstance(v, (int, float)) and not pd.isna(v) and v < 0 else "—")
        )

    day_total = sum(pnl_map.get(sel_date, 0) or 0 for _ in [1])
    sign      = "+" if day_total >= 0 else ""
    st.markdown(
        f'<div style="font-size:13px;color:#8B949E;margin-bottom:8px">'
        f'<strong style="color:#E6EDF3">{sel_date}</strong> — '
        f'{len(day_trades)} trade{"s" if len(day_trades) != 1 else ""}</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(day_df[cols], use_container_width=True, hide_index=True,
                 column_config={
                     "pnl":    st.column_config.TextColumn("P&L"),
                     "size":   st.column_config.NumberColumn("Size", format="%.2f"),
                     "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
                 })
else:
    st.markdown(
        f'<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;'
        f'padding:20px;text-align:center;color:#8B949E;font-size:13px">'
        f'No trades on {sel_date}.</div>',
        unsafe_allow_html=True,
    )
