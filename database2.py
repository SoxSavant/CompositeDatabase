import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo
from h_utils import (
    load_final_year, label_map,
    POSITION_OPTIONS, TEAM_OPTIONS, normalize_team,
    apply_dh_override, s3, bucket
)
from p_utils import (
    load_final_year_processed,
    TEAM_OPTIONS as P_TEAM_OPTIONS,
    normalize_team as p_normalize_team,
    label_map as p_label_map,
    ip_to_outs, outs_to_ip,
    get_last_updated as p_get_last_updated,
)

st.set_page_config(page_title="JUST BASEBALL", layout="wide", page_icon="⚾")

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
    st.title("JUST BASEBALL")

# ── Domain / view mode toggles ─────────────────────────────────────────
col1, col2, _ = st.columns([2, 2, 8])
with col1:
    domain = st.radio("", ["Hitting", "Pitching"], horizontal=True)
with col2:
    view_mode = st.radio("", ["Player", "Team"], horizontal=True)

# ── Domain-specific stat configuration ─────────────────────────────────
if domain == "Hitting":
    HEMBO_STATS = [
        "OPS", "wRC+",
        "DRS", "FRV", "Fielding Composite (minus BP)",
        "BRV", "BsR", "Baserunning Composite (minus BP)",
        "bWAR", "fWAR", "Value Composite (minus BP)",
    ]

    # Stats that should be summed across years (counting/rate that accumulates)
    # vs averaged (rate stats like OPS+, wRC+, DRC+)
    SUM_STATS = {
        "DRS", "FRV", "Fielding Composite (minus BP)",
        "BRV", "BsR", "Baserunning Composite (minus BP)",
        "bWAR", "fWAR", "Value Composite (minus BP)",
    }
    AVG_STATS = {"OPS", "wRC+"}

    DECIMAL_STATS = {
        "BRV", "BsR",
        "Baserunning Composite (minus BP)", "bWAR", "fWAR", "Value Composite (minus BP)",
        "Fielding Composite (minus BP)"
    }
    TWO_DECIMAL_STATS = set()
    THREE_DECIMAL_STATS = {"OPS"}

    cur_label_map = label_map
    cur_team_options = TEAM_OPTIONS
    cur_normalize_team = normalize_team
    default_sort_col = "Value Composite (minus BP)"
else:
    HEMBO_STATS = ["ERA", "xERA", "SIERA", "FIP", "xFIP", "bWAR", "fWAR", "Composite"]

    SUM_STATS = {"bWAR", "fWAR", "Composite"}
    AVG_STATS = {"ERA", "xERA", "SIERA", "FIP", "xFIP"}

    DECIMAL_STATS = {"bWAR", "fWAR", "Composite"}
    TWO_DECIMAL_STATS = {"ERA", "xERA", "SIERA", "FIP", "xFIP"}
    THREE_DECIMAL_STATS = set()

    cur_label_map = p_label_map
    cur_team_options = P_TEAM_OPTIONS
    cur_normalize_team = p_normalize_team
    default_sort_col = "Composite"

current_year = date.today().year
START_YEAR = 1901


def get_last_updated(year: int) -> str:
    try:
        obj = s3.get_object(Bucket=bucket, Key=f"project/hitting_{year}.csv")
        last_modified = obj["LastModified"].astimezone(ZoneInfo("America/New_York"))
        return last_modified.strftime("%B %d, %Y")
    except Exception:
        return "unknown"


def load_year_data(year: int) -> pd.DataFrame:
    """Domain-aware single-year loader."""
    if domain == "Hitting":
        return load_final_year(year)
    df = load_final_year_processed(year)
    if df is not None and not df.empty and "fWAR-bWAR Avg" in df.columns:
        df = df.rename(columns={"fWAR-bWAR Avg": "Composite"})
    return df


def load_year_range(start: int, end: int) -> pd.DataFrame:
    frames = []
    sort_metric = "PA" if domain == "Hitting" else "IP"
    for yr in range(start, end + 1):
        df = load_year_data(yr)
        if df is not None and not df.empty:
            df = df.copy()
            df["Year"] = yr
            if "PlayerId" in df.columns:
                df["PlayerId"] = pd.to_numeric(df["PlayerId"], errors="coerce").astype("Int64").astype(str)
                if sort_metric in df.columns:
                    df = df.sort_values(sort_metric, ascending=False).drop_duplicates(subset=["PlayerId"], keep="first")
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_multi_year(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """
    Aggregate a multi-year hitting dataframe.
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
    """
    Aggregate a multi-year pitching dataframe.
    IP is summed (via outs); rate stats (ERA, xERA, SIERA, FIP, xFIP) are
    IP-weighted averaged; counting stats (bWAR, fWAR, Composite) are summed.
    """
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
            df[f"_w_{stat}"] = df[stat] * df["_outs"].where(mask, 0)
            df[f"_ou_{stat}"] = df["_outs"].where(mask, 0)
            agg[f"_w_{stat}"] = (f"_w_{stat}", "sum")
            agg[f"_ou_{stat}"] = (f"_ou_{stat}", "sum")
        else:
            agg[stat] = (stat, "sum")

    grouped = df.groupby(group_cols, as_index=False).agg(**agg)

    if "_outs" in grouped.columns:
        grouped["IP"] = grouped["_outs"].apply(outs_to_ip)

    for stat in HEMBO_STATS:
        if stat not in df.columns:
            continue
        if stat in AVG_STATS and f"_w_{stat}" in grouped.columns:
            grouped[stat] = grouped[f"_w_{stat}"] / grouped[f"_ou_{stat}"].replace(0, float("nan"))
            grouped.drop(columns=[f"_w_{stat}", f"_ou_{stat}"], inplace=True)

    grouped = grouped.drop(columns=["_outs"], errors="ignore")
    return grouped


last_updated = get_last_updated(current_year) if domain == "Hitting" else p_get_last_updated(current_year)
st.caption(f"2026 data last updated: {last_updated}")

# ── Filters ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 1, 1, 1, 1, 1, 2])

with c1:
    year_mode = st.selectbox("Year Mode", ["Single Season", "Multi-Year Span", "Split Season"])

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
    if domain == "Hitting" and view_mode == "Player":
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
            options=list(cur_team_options.keys()),
            format_func=lambda x: cur_team_options[x],
        )
    else:
        team = "all"
        st.empty()

with c6:
    min_pa = 0
    min_ip = 0
    if view_mode == "Player":
        if domain == "Hitting":
            min_pa = st.number_input("Min PA", min_value=0, max_value=5000, value=0, step=10)
        else:
            min_ip = st.number_input("Min IP", min_value=0, max_value=3000, value=0, step=10)

with c7:
    if view_mode == "Player":
        search = st.text_input("Search players (separate by commas)")
    else:
        search = ""

# ── Load data ──────────────────────────────────────────────────────────
if year_start == year_end:
    df = load_year_data(year_start)
    if df is not None and not df.empty:
        df["Year"] = year_start
else:
    df = load_year_range(year_start, year_end)

if df is None or df.empty:
    st.error(f"No data found for the selected year(s).")
    st.stop()

# ── Position / team / PA / IP / search filters (player mode only) ─────
if domain == "Hitting":
    df["Pos"] = df["Pos"].astype(str).str.strip().str.upper()
    df = apply_dh_override(df)

if view_mode == "Player":
    if domain == "Hitting" and position != "all":
        pos = position.upper()
        if pos == "OF":
            df = df[df["Pos"].isin({"LF", "CF", "RF", "OF"})]
        else:
            df = df[df["Pos"] == pos]

    if team != "all" and "Team" in df.columns:
        target = cur_normalize_team(team)
        df = df[df["Team"].astype(str).apply(lambda t: cur_normalize_team(t) == target)]

# ── Aggregate multi-year if needed ────────────────────────────────────
multi_year = year_start != year_end and year_mode == "Multi-Year Span"

if view_mode == "Player":
    if multi_year:
        sorted_df = df.sort_values("Year")

        # Save most recent Name, Team, (Pos) per player keyed on PlayerId
        if domain == "Hitting":
            last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team", "Pos"]]
            df = aggregate_multi_year(df, ["PlayerId"])
        else:
            last = sorted_df.groupby("PlayerId", as_index=False).last()[["PlayerId", "Name", "Team"]]
            df = aggregate_multi_year_pitching(df, ["PlayerId"])

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
            mask = pd.Series(False, index=df.index)
            for term in terms:
                mask |= df["Name"].astype(str).str.contains(term, case=False, na=False)
            df = df[mask]

    base_cols = [c for c in ["Name"] if c in df.columns]
    if year_mode == "Split Season":
        base_cols = [c for c in ["Name", "Year"] if c in df.columns]
    sort_col = default_sort_col if default_sort_col in df.columns else None

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
            df = aggregate_multi_year(df, group_cols)
        else:
            df = aggregate_multi_year_pitching(df, group_cols)
    else:
        st.error("No Team column found in data.")
        st.stop()

    base_cols = ["Team", "Year"] if year_mode == "Split Season" else ["Team"]
    sort_col = default_sort_col if default_sort_col in df.columns else None

# ── Build display dataframe ────────────────────────────────────────────
stat_cols = [c for c in HEMBO_STATS if c in df.columns]
available_base = [c for c in base_cols if c in df.columns]
display = df[available_base + stat_cols].copy()


if sort_col and sort_col in display.columns:
    display = display.sort_values(sort_col, ascending=False, na_position="last")

display = display.reset_index(drop=True)
display.index += 1


def strip_bf_suffix(label: str) -> str:
    return label.replace(" (minus BP)", "").strip()


# ── Column config ──────────────────────────────────────────────────────
col_config = {}
for stat in stat_cols:
    col_config[stat] = st.column_config.NumberColumn(
        label=strip_bf_suffix(cur_label_map.get(stat, stat)),
        format=(
            "%.1f" if stat in DECIMAL_STATS
            else "%.2f" if stat in TWO_DECIMAL_STATS
            else "%.3f" if stat in THREE_DECIMAL_STATS
            else "%d"
        ),
    )

year_label = str(year_start) if year_mode == "Single Season" else f"{year_start}–{year_end}"
mode_label = "Teams" if view_mode == "Team" else "Players"
if view_mode != "Team" and year_mode == "Split Season":
    mode_label = "Player Seasons"
if view_mode == "Team" and year_mode == "Split Season":
    mode_label = "Team Seasons"
st.caption(f"Showing {len(display)} {mode_label} · {year_label}")

st.dataframe(display, width="stretch", height=600, column_config=col_config)