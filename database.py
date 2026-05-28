import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo
from h_utils import (
    load_final_year, label_map,
    POSITION_OPTIONS, TEAM_OPTIONS, normalize_team,
    apply_dh_override, s3, bucket
)

st.set_page_config(page_title="Composite Database", layout="wide", page_icon="⚾")

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
    st.title("Composite Database")

HEMBO_STATS = [
    "OPS+", "wRC+", "DRC+", "Hitting Composite",
    "DRS", "FRV", "DRP", "Fielding Composite",
    "Rbaser", "BsR", "DRB", "Baserunning Composite",
    "bWAR", "fWAR", "WARP", "Value Composite",
]

# Stats that should be summed across years (counting/rate that accumulates)
# vs averaged (rate stats like OPS+, wRC+, DRC+)
SUM_STATS = {
    "DRS", "FRV", "DRP", "Fielding Composite",
    "Rbaser", "BsR", "DRB", "Baserunning Composite",
    "bWAR", "fWAR", "WARP", "Value Composite",
}
AVG_STATS = {"OPS+", "wRC+", "DRC+", "Hitting Composite"}

DECIMAL_STATS = {
    "DRP", "Rbaser", "BsR", "DRB",
    "Baserunning Composite", "bWAR", "fWAR", "WARP", "Value Composite",
    "Fielding Composite",
}

current_year = date.today().year
START_YEAR = 1901


@st.cache_data(ttl=3600)
def get_last_updated(year: int) -> str:
    try:
        obj = s3.get_object(Bucket=bucket, Key=f"project/hitting_{year}.csv")
        last_modified = obj["LastModified"].astimezone(ZoneInfo("America/New_York"))
        return last_modified.strftime("%B %d, %Y at %I:%M %p ET")
    except Exception:
        return "unknown"


@st.cache_data(ttl=3600)
def load_year_range(start: int, end: int) -> pd.DataFrame:
    frames = []
    for yr in range(start, end + 1):
        df = load_final_year(yr)
        if df is not None and not df.empty:
            df = df.copy()
            df["_year"] = yr
            if "PlayerId" in df.columns:
                df["PlayerId"] = pd.to_numeric(df["PlayerId"], errors="coerce").astype("Int64").astype(str)
                df = df.sort_values("PA", ascending=False).drop_duplicates(subset=["PlayerId"], keep="first")
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_multi_year(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """
    Aggregate a multi-year dataframe.
    PA is summed; rate stats are PA-weighted averaged; counting stats are summed.
    """
    agg: dict = {}

    if "PA" in df.columns:
        df["PA"] = pd.to_numeric(df["PA"], errors="coerce").fillna(0)
        agg["PA"] = ("PA", "sum")

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        df[stat] = pd.to_numeric(df[stat], errors="coerce")
        if stat in AVG_STATS:
            # PA-weighted average
            df[f"_w_{stat}"] = df[stat] * df.get("PA", pd.Series(1, index=df.index))
            agg[f"_w_{stat}"] = (f"_w_{stat}", "sum")
        else:
            agg[stat] = (stat, "sum")

    grouped = df.groupby(group_cols, as_index=False).agg(**agg)

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        if stat in AVG_STATS and f"_w_{stat}" in grouped.columns:
            grouped[stat] = grouped[f"_w_{stat}"] / grouped["PA"].replace(0, float("nan"))
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
c1, c2, c3, c4, c5, c6,c7 = st.columns([1,1,1,1,1,1,1])

with c1:
    year_mode = st.selectbox("Year Mode", ["Single Year", "Year Range"])

with c2:
    if year_mode == "Single Year":
        year_single = st.selectbox("Year", list(range(current_year, START_YEAR - 1, -1)))
        year_start = year_end = year_single
    else:
        year_start = st.selectbox("From", list(range(current_year, START_YEAR - 1, -1)), index=4)

with c3:
    if year_mode == "Year Range":
        valid_ends = list(range(current_year, year_start - 1, -1))
        year_end = st.selectbox("To", valid_ends, index=0)
    else:
        st.empty()

with c4:
    if view_mode == "Player":
        position = st.selectbox(
            "Position",
            options=list(POSITION_OPTIONS.keys()),
            format_func=lambda x: POSITION_OPTIONS[x],
        )
    else:
        position = "all"
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
        min_pa = st.number_input("Min PA", min_value=0, max_value=5000, value=0, step=10)
    else:
        min_pa = 0
with c7:
    if view_mode == "Player":
        search = st.text_input("Search player")
    else:
        search = ""

# ── Load data ──────────────────────────────────────────────────────────
if year_start == year_end:
    df = load_final_year(year_start)
    if df is not None and not df.empty:
        df["_year"] = year_start
else:
    df = load_year_range(year_start, year_end)

if df is None or df.empty:
    st.error(f"No data found for the selected year(s).")
    st.stop()

# ── Position / team / PA / search filters (player mode only) ──────────
df["Pos"] = df["Pos"].astype(str).str.strip().str.upper()
df = apply_dh_override(df)

if view_mode == "Player":
    if position != "all":
        pos = position.upper()
        if pos == "OF":
            df = df[df["Pos"].isin({"LF", "CF", "RF", "OF"})]
        else:
            df = df[df["Pos"] == pos]

    if team != "all" and "Team" in df.columns:
        target = normalize_team(team)
        df = df[df["Team"].astype(str).apply(lambda t: normalize_team(t) == target)]

# ── Aggregate multi-year if needed ────────────────────────────────────
multi_year = year_start != year_end

if view_mode == "Player":
    if multi_year:
        sorted_df = df.sort_values("_year")
        
        # Save most recent Name, Team, Pos per player keyed on MLBAMID
        last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team", "Pos"]]

        df = aggregate_multi_year(df, ["PlayerId"])

        # Re-attach name/team/pos
        df = df.merge(last, on="PlayerId", how="left")

    # Min PA filter
    if min_pa > 0 and "PA" in df.columns:
        df = df[pd.to_numeric(df["PA"], errors="coerce").fillna(0) >= min_pa]

    # Player search
    if search.strip():
        df = df[df["Name"].astype(str).str.contains(search.strip(), case=False, na=False)]

    base_cols = [c for c in ["Name", "Team", "Pos", "PA"] if c in df.columns]
    sort_col = "Value Composite" if "Value Composite" in df.columns else None

elif view_mode == "Team":
    # Aggregate by Team (all years if multi-year)
    if "Team" in df.columns:
        # Drop multi-team placeholder rows (traded players recorded as "---", "TOT", "2TM", etc.)
        MULTI_TEAM_PLACEHOLDERS = {"---", "TOT", "2TM", "3TM", "4TM", "- - -", ""}
        df = df[~df["Team"].astype(str).str.strip().str.upper().isin(MULTI_TEAM_PLACEHOLDERS)]
        group_cols = ["Team"]
        df = aggregate_multi_year(df, group_cols)
    else:
        st.error("No Team column found in data.")
        st.stop()

    base_cols = ["Team"]
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
        label=label_map.get(stat, stat),
        format="%.1f" if stat in DECIMAL_STATS else "%d",
    )

year_label = f"{year_start}–{year_end}" if multi_year else str(year_start)
mode_label = "Teams" if view_mode == "Team" else "Players"
st.caption(f"Showing {len(display)} {mode_label} · {year_label}")

st.dataframe(display, use_container_width=True, height=600, column_config=col_config)