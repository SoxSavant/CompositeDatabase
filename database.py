import streamlit as st
import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo
from h_utils import (
    load_final_year, label_map,
    POSITION_OPTIONS, TEAM_OPTIONS, normalize_team,
    apply_dh_override, s3, bucket
)

st.set_page_config(page_title="Hembo Stats", layout="wide", page_icon="⚾")

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
    st.title("Hembo Stats")


HEMBO_STATS = [ "bWAR", "fWAR", "WARP","Value Composite",
    "OPS+", "wRC+", "DRC+", "Hitting Composite",
    "DRS", "FRV", "DRP", "Fielding Composite",
    "Rbaser", "BsR", "DRB", "Baserunning Composite",

]

current_year = date.today().year
START_YEAR = 2000

@st.cache_data(ttl=3600)
def get_last_updated(year: int) -> str:
    try:
        obj = s3.get_object(Bucket=bucket, Key=f"project/hitting_{year}.csv")
        last_modified = obj["LastModified"].astimezone(ZoneInfo("America/New_York"))
        return last_modified.strftime("%B %d, %Y")
    except Exception:
        return "unknown"

last_updated = get_last_updated(current_year)
st.caption(f"2026 data last updated: {last_updated}")

# ── Filters ────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])

with c1:
    year = st.selectbox("Year", list(range(current_year, START_YEAR - 1, -1)))
with c2:
    position = st.selectbox(
        "Position",
        options=list(POSITION_OPTIONS.keys()),
        format_func=lambda x: POSITION_OPTIONS[x],
    )
with c3:
    team = st.selectbox(
        "Team",
        options=list(TEAM_OPTIONS.keys()),
        format_func=lambda x: TEAM_OPTIONS[x],
    )
with c4:
    min_pa = st.number_input("Min PA", min_value=0, max_value=5000, value=0, step=10)
with c5:
    search = st.text_input("Search player")

# ── Load ───────────────────────────────────────────────────────────────
df = load_final_year(year)

if df is None or df.empty:
    st.error(f"No data found for {year}.")
    st.stop()

# ── Position filter ────────────────────────────────────────────────────
df["Pos"] = df["Pos"].astype(str).str.strip().str.upper()
df = apply_dh_override(df)

if position != "all":
    pos = position.upper()
    if pos == "OF":
        df = df[df["Pos"].isin({"LF", "CF", "RF", "OF"})]
    else:
        df = df[df["Pos"] == pos]

# ── Team filter ────────────────────────────────────────────────────────
if team != "all" and "Team" in df.columns:
    target = normalize_team(team)
    df = df[df["Team"].astype(str).apply(lambda t: normalize_team(t) == target)]

# ── Min PA filter ──────────────────────────────────────────────────────
if min_pa > 0 and "PA" in df.columns:
    df = df[pd.to_numeric(df["PA"], errors="coerce").fillna(0) >= min_pa]

# ── Player search ──────────────────────────────────────────────────────
if search.strip():
    df = df[df["Name"].astype(str).str.contains(search.strip(), case=False, na=False)]



# ── Display ────────────────────────────────────────────────────────────
base_cols = [c for c in ["Name", "Team", "Pos", "PA"] if c in df.columns]
stat_cols = [c for c in HEMBO_STATS if c in df.columns]
display = df[base_cols + stat_cols].sort_values("Value Composite", ascending = False,na_position="last").reset_index(drop=True)
display.index += 1

col_config = {}
for stat in stat_cols:
    is_decimal = stat in {
        "DRP", "Rbaser", "BsR", "DRB",
        "Baserunning Composite", "bWAR", "fWAR", "WARP", "Value Composite",
    }
    col_config[stat] = st.column_config.NumberColumn(
        label=label_map.get(stat, stat),
        format="%.1f" if is_decimal else "%d",
    )

st.dataframe(display, use_container_width=True, height=600, column_config=col_config)