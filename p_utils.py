from pathlib import Path
import streamlit as st
import pandas as pd
import requests
import boto3
import os
import numpy as np
from zoneinfo import ZoneInfo


TEAM_ALIASES = {
    "ATH": "OAK",
    "ATH/OAK": "OAK",
    "OAK/ATH": "OAK",
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


label_map = {}



s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

bucket = "sports-analytics-files"

def load_final_year(year: int) -> pd.DataFrame:
    key = f"project/pitching_{year}.csv"
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
        obj = s3.get_object(Bucket=bucket, Key=f"project/pitching_{year}.csv")
        last_modified = obj["LastModified"].astimezone(ZoneInfo("America/New_York"))
        return last_modified.strftime("%B %d, %Y")
    except Exception:
        return "unknown"
    
def ip_to_outs(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return np.nan
    try:
        v = float(value)
    except Exception:
        return np.nan
    innings = int(np.floor(v))
    fractional = v - innings
    if abs(fractional - 0.1) < 0.05:
        outs_extra = 1
    elif abs(fractional - 0.2) < 0.05:
        outs_extra = 2
    else:
        outs_extra = min(max(int(round(fractional * 3)), 0), 2)
    return innings * 3 + outs_extra


def outs_to_ip(outs: float) -> float:
    if pd.isna(outs):
        return np.nan
    innings = int(float(outs) // 3)
    remainder = int(round(float(outs) % 3))
    return innings + remainder / 10

