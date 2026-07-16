import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo
from p_utils import (
    load_final_year, TEAM_OPTIONS, normalize_team, get_last_updated
)

st.set_page_config(page_title=" Pitching Composite Database", layout="wide", page_icon="⚾")

st.markdown("""
<style>
[data-testid="stToolbar"]     { visibility: hidden; }
[data-testid="stDecoration"]  { display: none; }
[data-testid="stStatusWidget"]{ display: none; }
.block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

title_col, meta_col = st.columns([3, 1])
with title_col:
    st.title(" Pitching Composite Database")

HEMBO_STATS = [
    "ERA", "RA9", "OPS",
    "DRA", "SIERA", "xERA", "Composite", #50% DRA, 40% SIERA, 10% xERA
    "bWAR", "fWAR", "WARP", "Value Composite",
]


SUM_STATS = {
 
    "bWAR", "fWAR", "WARP", "Value Composite",
}
AVG_STATS = { "ERA", "RA9", "OPS", "DRA", "SIERA", "xERA", "Composite",}

DECIMAL_STATS = {
   "bWAR", "fWAR", "WARP", "Value Composite",
}
TWO_DECIMAL_STATS = {"ERA","RA9","DRA","SIERA","xERA","Composite"}

THREE_DECIMAL_STATS = {"OPS"}

current_year = date.today().year
START_YEAR = 1901



def load_year_range(start: int, end: int) -> pd.DataFrame:
    frames = []
    for yr in range(start, end + 1):
        df = load_final_year(yr)
        if df is not None and not df.empty:
            df = df.copy()
            df["Year"] = yr
            if "PlayerId" in df.columns:
                df["PlayerId"] = pd.to_numeric(df["PlayerId"], errors="coerce").astype("Int64").astype(str)
                df = df.sort_values("IP", ascending=False).drop_duplicates(subset=["PlayerId"], keep="first")
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_multi_year(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
  
    agg: dict = {}

    if "IP" in df.columns:
        df["IP"] = pd.to_numeric(df["IP"], errors="coerce").fillna(0)
        agg["IP"] = ("IP", "sum")

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        df[stat] = pd.to_numeric(df[stat], errors="coerce")
        if stat in AVG_STATS:
            # IP-weighted average
            df[f"_w_{stat}"] = df[stat] * df.get("IP", pd.Series(1, index=df.index))
            agg[f"_w_{stat}"] = (f"_w_{stat}", "sum")
        else:
            agg[stat] = (stat, "sum")

    grouped = df.groupby(group_cols, as_index=False).agg(**agg)

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        if stat in AVG_STATS and f"_w_{stat}" in grouped.columns:
            grouped[stat] = grouped[f"_w_{stat}"] / grouped["IP"].replace(0, float("nan"))
            grouped.drop(columns=[f"_w_{stat}"], inplace=True)

    return grouped


last_updated = get_last_updated(current_year)
st.caption(f"2026 data last updated: {last_updated}")

# ── View mode toggle ───────────────────────────────────────────────────
view_mode = st.radio(
    "View",
    ["Player", "Team"],
    horizontal=True,
    label_visibility="collapsed",
)

# ── Filters ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6,c7 = st.columns([1,1,1,1,1,1,2])

with c1:
    year_mode = st.selectbox("Year Mode", ["Single Season", "Multi-Year Span","Split Season"])

with c2:
    if year_mode == "Single Season":
        year_single = st.selectbox("Year", list(range(current_year, START_YEAR - 1, -1)))
        year_start = year_end = year_single
    else:
        year_start = st.selectbox("From", list(range(current_year, START_YEAR - 1, -1)), index=4)

with c3:
    if year_mode != "Single Season":
        valid_ends = list(range(current_year, year_start - 1, -1))
        year_end = st.selectbox("To", valid_ends, index=0)
    else:
        st.empty()



with c5:
    if view_mode == "Player":
        team = st.selectbox(
            "Team",
            options=list(TEAM_OPTIONS.keys()),
            format_func=lambda x: TEAM_OPTIONS[x],
        )
    else:
        team = "all"
        st.empty()

with c6:
    if view_mode == "Player":
        min_pa = st.number_input("Min IP", min_value=0, max_value=5000, value=0, step=10)
    else:
        min_pa = 0
with c7:
    if view_mode == "Player":
        search = st.text_input("Search players (separate by commas)")
    else:
        search = ""

# ── Load data ──────────────────────────────────────────────────────────
if year_start == year_end:
    df = load_final_year(year_start)
    if df is not None and not df.empty:
        df["Year"] = year_start
else:
    df = load_year_range(year_start, year_end)

if df is None or df.empty:
    st.error(f"No data found for the selected year(s).")
    st.stop()

if view_mode == "Player":
    if team != "all" and "Team" in df.columns:
        target = normalize_team(team)
        df = df[df["Team"].astype(str).apply(lambda t: normalize_team(t) == target)]

# ── Aggregate multi-year if needed ────────────────────────────────────
multi_year = year_start != year_end and year_mode == "Multi-Year Span"

if view_mode == "Player":
    if multi_year:
        sorted_df = df.sort_values("Year")
        
        # Save most recent Name, Team, Pos per player keyed on MLBAMID
        last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team"]]

        df = aggregate_multi_year(df, ["PlayerId"])

        # Re-attach name/team/pos
        df = df.merge(last, on="PlayerId", how="left")

    # Min IP filter
    if min_pa > 0 and "IP" in df.columns:
        df = df[pd.to_numeric(df["IP"], errors="coerce").fillna(0) >= min_pa]

    # Player search
    if search.strip():
        terms = [t.strip() for t in search.split(",") if t.strip()]
        if terms:
            mask = pd.Series(False, index = df.index)
            for term in terms:
                mask |= df["Name"].astype(str).str.contains(term, case = False, na = False)
            df = df[mask]

    base_cols = [c for c in ["Name",] if c in df.columns]
    if year_mode == "Split Season":
        base_cols = [c for c in ["Name",  "Year",] if c in df.columns]
    sort_col = "Value Composite" if "Value Composite" in df.columns else None

elif view_mode == "Team":
    # Aggregate by Team (all years if multi-year)
    if "Team" in df.columns:
        # Drop multi-team placeholder rows (traded players recorded as "---", "TOT", "2TM", etc.)
        MULTI_TEAM_PLACEHOLDERS = {"---", "TOT", "2TM", "3TM", "4TM", "- - -", ""}
        df = df[~df["Team"].astype(str).str.strip().str.upper().isin(MULTI_TEAM_PLACEHOLDERS)]
        if year_mode == "Split Season":
            group_cols = ["Team", "Year"]
        else:
            group_cols = ["Team"]
        
        df = aggregate_multi_year(df, group_cols)
    else:
        st.error("No Team column found in data.")
        st.stop()

    base_cols = ["Team", "Year"] if year_mode == "Split Season" else ["Team"]
    sort_col = "Value Composite" if "Value Composite" in df.columns else None

# ── Build display dataframe ────────────────────────────────────────────
stat_cols = [c for c in HEMBO_STATS if c in df.columns]
available_base = [c for c in base_cols if c in df.columns]
display = df[available_base + stat_cols].copy()


if sort_col and sort_col in display.columns:
    display = display.sort_values(sort_col, ascending=False, na_position="last")

display = display.reset_index(drop=True)
display.index += 1

# ── Column config ──────────────────────────────────────────────────────
col_config = {}
for stat in stat_cols:
    col_config[stat] = st.column_config.NumberColumn(
        format="%.1f" if stat in DECIMAL_STATS else "%.2f" if stat in TWO_DECIMAL_STATS else "%.3f" if stat in THREE_DECIMAL_STATS else "%d",
    )

year_label = str(year_start) if year_mode == "Single Season" else f"{year_start}–{year_end}"
mode_label = "Teams" if view_mode == "Team" else "Players"
if view_mode != "Team" and year_mode == "Split Season":
    mode_label = "Player Seasons"
if view_mode == "Team" and year_mode == "Split Season":
    mode_label = "Team Seasons"
st.caption(f"Showing {len(display)} {mode_label} · {year_label}")

st.dataframe(display, width="stretch", height=600, column_config=col_config)