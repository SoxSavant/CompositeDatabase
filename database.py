import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo

from p_utils import ip_to_outs, outs_to_ip


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

current_year = date.today().year
START_YEAR = 1901

from h_utils import get_last_updated


last_updated = get_last_updated(current_year)
st.caption(f"2026 data last updated: {last_updated}")


col1, col2, _ = st.columns([3,2,8])

with col1:
    domain = st.radio("", ["Hitting", "Pitching","Combined"], horizontal=True)

HIDE_STATS = ["Rbaser", "BsR", "DRB"]

if domain == "Hitting":
    from h_utils import (
    load_final_year, label_map,
    POSITION_OPTIONS, TEAM_OPTIONS, normalize_team, get_last_updated,
    apply_dh_override,
)

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
    TWO_DECIMAL_STATS = {}

    THREE_DECIMAL_STATS = {}
elif domain == "Pitching":
    from p_utils import (
    load_final_year, TEAM_OPTIONS, normalize_team, get_last_updated, label_map
)
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
else:  
    from h_utils import load_final_year as load_hitting_year, TEAM_OPTIONS, normalize_team, label_map
    from p_utils import load_final_year as load_pitching_year

    HEMBO_STATS = ["Bat WAR", "Pitch WAR", "Total WAR","Bat WPA", "Pitch WPA", "Total WPA"]
    SUM_STATS = {"Bat WAR", "Pitch WAR", "Total WAR","Bat WPA", "Pitch WPA", "Total WPA"}
    AVG_STATS = set()
    DECIMAL_STATS = {"Bat WAR", "Pitch WAR", "Total WAR",}
    TWO_DECIMAL_STATS = {"Bat WPA", "Pitch WPA", "Total WPA"}
    THREE_DECIMAL_STATS = {}

def load_combined_year(year: int) -> pd.DataFrame:
    hit = load_hitting_year(year)
    pit = load_pitching_year(year)

    hit_slim = pd.DataFrame(columns=["PlayerId", "Name", "Team", "Bat WAR", "Bat WPA"])
    if hit is not None and not hit.empty:
        hit_slim = hit[["PlayerId", "Name", "Team", "Value Composite","WPA"]].copy()
        hit_slim["PlayerId"] = pd.to_numeric(hit_slim["PlayerId"], errors="coerce").astype("Int64").astype(str)
        hit_slim = hit_slim.rename(columns={"Value Composite": "Bat WAR","WPA":"Bat WPA"})

    pit_slim = pd.DataFrame(columns=["PlayerId", "Name", "Team", "Pitch WAR","Pitch WPA"])
    if pit is not None and not pit.empty:
        pit_slim = pit[["PlayerId", "Name", "Team", "Value Composite","WPA"]].copy()
        pit_slim["PlayerId"] = pd.to_numeric(pit_slim["PlayerId"], errors="coerce").astype("Int64").astype(str)
        pit_slim = pit_slim.rename(columns={"Value Composite": "Pitch WAR","WPA":"Pitch WPA"})

    merged = hit_slim.merge(pit_slim, on="PlayerId", how="outer", suffixes=("_h", "_p"))
    merged["Name"] = merged["Name_h"].combine_first(merged["Name_p"])
    merged["Team"] = merged["Team_h"].combine_first(merged["Team_p"])
    merged = merged.drop(columns=["Name_h", "Name_p", "Team_h", "Team_p"])
    return merged

def load_year_range_combined(start: int, end: int) -> pd.DataFrame:
    frames = []
    for yr in range(start, end + 1):
        df = load_combined_year(yr)
        if df is not None and not df.empty:
            df = df.copy()
            df["Year"] = yr
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def agg_multi_year_combined(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    for col in ["Bat WAR", "Pitch WAR","Bat WPA","Pitch WPA"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    agg = {c: (c, "sum") for c in ["Bat WAR", "Pitch WAR","Bat WPA","Pitch WPA"] if c in df.columns}
    return df.groupby(group_cols, as_index=False).agg(**agg)


def load_year_range(start: int, end: int) -> pd.DataFrame:
    frames = []
    for yr in range(start, end + 1):
        df = load_final_year(yr)
        if df is not None and not df.empty:
            df = df.copy()
            df["Year"] = yr
            if "PlayerId" in df.columns:
                df["PlayerId"] = pd.to_numeric(df["PlayerId"], errors="coerce").astype("Int64").astype(str)
                
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_multi_year_hitting(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
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

def aggregate_multi_year_pitching(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    agg: dict = {}

    if "IP" in df.columns:
        df["IP"] = pd.to_numeric(df["IP"], errors="coerce").fillna(0)
        df["_outs"] = df["IP"].apply(ip_to_outs)
        agg["_outs"] = ("_outs", "sum")

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        df[stat] = pd.to_numeric(df[stat], errors="coerce")
        if stat in AVG_STATS:
            mask = df[stat].notna()
            df[f"_w_{stat}"]  = df[stat] * df["_outs"].where(mask, 0)
            df[f"_ou_{stat}"] = df["_outs"].where(mask, 0)
            agg[f"_w_{stat}"]  = (f"_w_{stat}", "sum")
            agg[f"_ou_{stat}"] = (f"_ou_{stat}", "sum")
        else:
            agg[stat] = (stat, "sum")

    grouped = df.groupby(group_cols, as_index=False).agg(**agg)
    grouped["IP"] = grouped["_outs"].apply(outs_to_ip)

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        if stat in AVG_STATS and f"_w_{stat}" in grouped.columns:
            grouped[stat] = grouped[f"_w_{stat}"] / grouped[f"_ou_{stat}"].replace(0, float("nan"))
            grouped.drop(columns=[f"_w_{stat}", f"_ou_{stat}"], inplace=True)

    grouped = grouped.drop(columns=["_outs"], errors="ignore")
    return grouped



# ── View mode toggle ───────────────────────────────────────────────────
with col2:
    view_mode = st.radio(
        "",
        ["Player", "Team"],
        horizontal=True,
        
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
        year_start = st.selectbox("From", list(range(current_year, START_YEAR - 1, -1)), index=1)

with c3:
    if year_mode != "Single Season":
        valid_ends = list(range(current_year, year_start - 1, -1))
        year_end = st.selectbox("To", valid_ends, index=0)
    else:
        st.empty()

with c4:
    if domain == "Hitting":
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
    if domain == "Hitting":
        if view_mode == "Player":
            min_pa = st.number_input("Min PA", min_value=0, max_value=5000, value=0, step=10)
        else:
            min_pa = 0
    else:
        if view_mode == "Player":
            min_ip = st.number_input("Min IP", min_value=0, max_value=5000, value=0, step=10)
        else:
            min_ip = 0
with c7:
    if view_mode == "Player":
        search = st.text_input("Search players (separate by commas)")
    else:
        search = ""


# ── Load data ──────────────────────────────────────────────────────────
if year_start == year_end:
    if domain == "Combined":
        df = load_combined_year(year_start)
    else:
        df = load_final_year(year_start)   # existing hitting/pitching loader
    if df is not None and not df.empty:
        df["Year"] = year_start
else:
    df = load_year_range_combined(year_start, year_end) if domain == "Combined" else load_year_range(year_start, year_end)

if df is None or df.empty:
    st.error(f"No data found for the selected year(s).")
    st.stop()

# ── Position / team / PA / search filters (player mode only) ──────────
if domain == "Hitting":
    df["Pos"] = df["Pos"].astype(str).str.strip().str.upper()
    df = apply_dh_override(df)

if view_mode == "Player":
    if domain == "Hitting":
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
multi_year = year_start != year_end and year_mode == "Multi-Year Span"

if view_mode == "Player":
    if multi_year:
        sorted_df = df.sort_values("Year")
        
        # Save most recent Name, Team, Pos per player keyed on MLBAMID
        if domain == "Hitting":
            last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team", "Pos"]]
        else:
            last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team"]]

        if domain == "Hitting":
            df = aggregate_multi_year_hitting(df, ["PlayerId"])
        elif domain == "Pitching":
            df = aggregate_multi_year_pitching(df, ["PlayerId"])
        else:
            df = agg_multi_year_combined(df,["PlayerId"])

        # Re-attach name/team/pos
        df = df.merge(last, on="PlayerId", how="left")

    # Min PA/IP filter
    if domain == "Hitting":
        if min_pa > 0 and "PA" in df.columns:
            df = df[pd.to_numeric(df["PA"], errors="coerce").fillna(0) >= min_pa]
    else:
        if min_ip > 0 and "IP" in df.columns:
            df = df[pd.to_numeric(df["IP"], errors="coerce").fillna(0) >= min_ip]

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
    if domain == "Combined":
        sort_col = "Total WAR"
    elif "Value Composite" in df.columns:
        sort_col = "Value Composite"
    else:
        sort_col = None

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
        
        if domain == "Hitting":
            df = aggregate_multi_year_hitting(df, group_cols)
        elif domain == "Pitching":
            df = aggregate_multi_year_pitching(df, group_cols)
        else:
            df = agg_multi_year_combined(df, group_cols)
    else:
        st.error("No Team column found in data.")
        st.stop()

    base_cols = ["Team", "Year"] if year_mode == "Split Season" else ["Team"]
    sort_col = "Value Composite" if "Value Composite" in df.columns else None

if domain == "Combined":
    df["Bat WAR"] = pd.to_numeric(df.get("Bat WAR"), errors="coerce").fillna(0)
    df["Pitch WAR"] = pd.to_numeric(df.get("Pitch WAR"), errors="coerce").fillna(0)
    df["Total WAR"] = df["Bat WAR"] + df["Pitch WAR"]
    df["Bat WPA"] = pd.to_numeric(df.get("Bat WPA"), errors="coerce").fillna(0)
    df["Pitch WPA"] = pd.to_numeric(df.get("Pitch WPA"), errors="coerce").fillna(0)
    df["Total WPA"] = df["Bat WPA"] + df["Pitch WPA"]

# ── Build display dataframe ────────────────────────────────────────────
stat_cols = [c for c in HEMBO_STATS if c in df.columns and c not in HIDE_STATS]
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