from pathlib import Path
import streamlit as st
import pandas as pd
import requests
import boto3
import os
import numpy as np
from zoneinfo import ZoneInfo




label_map = {
    "HardHit%": "Hard Hit%",
    "EV": "Avg EV",
    "BatSpd": "Bat Speed"
}


TEAM_ALIASES = {
    "ATH": "OAK",
    "ATH/OAK": "OAK",
    "OAK/ATH": "OAK",
}

POSITION_OPTIONS = {
    "all": "All Positions",
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "LF": "LF", "CF": "CF", "RF": "RF", "OF": "OF", "DH": "DH",
}

TEAM_OPTIONS = {
    "all": "All Teams",
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BOS": "BOS",
    "CHC": "CHC", "CIN": "CIN", "CLE": "CLE", "COL": "COL",
    "CHW": "CHW", "DET": "DET", "HOU": "HOU", "KCR": "KCR",
    "LAA": "LAA", "LAD": "LAD", "MIA": "MIA", "MIL": "MIL",
    "MIN": "MIN", "NYM": "NYM", "NYY": "NYY", "ATH": "ATH",
    "PHI": "PHI", "PIT": "PIT", "SDP": "SDP", "SEA": "SEA",
    "SFG": "SFG", "STL": "STL", "TBR": "TBR", "TEX": "TEX",
    "TOR": "TOR", "WSN": "WSN",
}


def normalize_team(team: str) -> str:
    t = str(team).strip()
    return TEAM_ALIASES.get(t, t)

def apply_dh_override(df):
    if "Pos" not in df.columns or "PA" not in df.columns or "Inn" not in df.columns or "Season" not in df.columns:
        print(df.columns)
        return df

    df = df.copy()


    # row-level DH eligibility
    eligible = df["Season"] >= 1973

    is_pitcher = df["Pos"].astype(str).str.upper().eq("P")
    eligible &= ~is_pitcher

    pa = pd.to_numeric(df["PA"], errors="coerce").fillna(0)
    inn = pd.to_numeric(df["Inn"], errors="coerce").fillna(0)

    estimated = (pa / 4.1) * 9

    is_dh = eligible & ((inn == 0) | ((inn > 0) & (estimated / inn > 3)))

    df.loc[is_dh, "Pos"] = "DH"
    return df




s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

bucket = "sports-analytics-files"

def load_final_year(year: int) -> pd.DataFrame:
    key = f"project/hitting_{year}.csv"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        df = pd.read_csv(obj["Body"])
        df["Season"] = year
        return df
    except Exception:
        return pd.DataFrame()
    
# old loading function
    """@st.cache_data(show_spinner=False, ttl=900)
def load_final_year(year: int) -> pd.DataFrame:
    path = f"data/final/hitting_final_{year}.csv"
    try:
        df = pd.read_csv(path)
        df["Season"] = year
    
        return df
    except Exception:
        return pd.DataFrame()"""

def get_last_updated(year: int) -> str:
    try:
        obj = s3.get_object(Bucket=bucket, Key=f"project/hitting_{year}.csv")
        last_modified = obj["LastModified"].astimezone(ZoneInfo("America/New_York"))
        return last_modified.strftime("%B %d, %Y")
    except Exception:
        return "unknown"