import os
import re

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="AFCON 2025 — Local CSVs (No Position)", layout="wide", page_icon="📁"
)

st.title("⚽ AFCON 2025 — Load Teams from Local CSV Files (Position Removed)")
st.markdown("This version removes all Position-related fields, filters, and charts.")

# -----------------------
# Configuration
# -----------------------
DEFAULT_DATA_DIR = "./data"
st.sidebar.header("Settings")

data_dir = st.sidebar.text_input("CSV folder path", value=DEFAULT_DATA_DIR)
refresh = st.sidebar.button("Refresh file list")


# -----------------------
# List CSV Files
# -----------------------
@st.cache_data
def list_csv_files(folder):
    try:
        return [
            os.path.join(folder, f)
            for f in sorted(os.listdir(folder))
            if f.lower().endswith(".csv")
        ]
    except:
        return []


csv_files = list_csv_files(data_dir) if not refresh else list_csv_files(data_dir)

if not csv_files:
    st.warning(f"No CSV files found in: `{data_dir}`")
    st.stop()

file_display_names = [os.path.basename(p) for p in csv_files]
selected_files = st.sidebar.multiselect(
    "Select CSV file(s)", file_display_names, default=[file_display_names[0]]
)

if not selected_files:
    st.info("Select at least one CSV file.")
    st.stop()


# -----------------------
# Load & clean (NO POSITION)
# -----------------------
@st.cache_data
def load_and_clean_csv(path):
    df = pd.read_csv(path)

    # Normalize columns
    df.columns = [c.strip() for c in df.columns]

    # Column detection (Position removed)
    col_map = {}
    cols = {c.lower(): c for c in df.columns}

    def find_col(names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    col_map["name"] = find_col(["name", "player", "player name"])
    col_map["age"] = find_col(["age"])
    col_map["height"] = find_col(["height"])
    col_map["foot"] = find_col(["foot"])
    col_map["market_value"] = find_col(["market_value", "market value", "value"])

    # Create or copy columns
    for key, col in col_map.items():
        if col is None:
            df[key] = "N/A"
        else:
            df[key] = df[col]

    # --- Market value cleanup ---
    mv = df["market_value"].astype(str)
    mv = mv.str.replace("€", "", regex=False)
    mv = mv.str.replace("-", "0", regex=False)
    mv = mv.str.replace("m", "000000", regex=False)
    mv = mv.str.replace("k", "000", regex=False)
    mv = mv.str.replace(" ", "", regex=False)
    df["market_value_numeric"] = pd.to_numeric(mv, errors="coerce").fillna(0)

    # --- Age numeric ---
    df["age_numeric"] = pd.to_numeric(
        df["age"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    )

    # --- Height numeric ---
    h = df["height"].astype(str)
    h_m = h.str.extract(r"(\d+[.,]\d+)")[0]
    h_cm = h.str.extract(r"(\d{3})")[0]
    height_val = h_m.fillna(h_cm)
    height_val = height_val.str.replace(",", ".", regex=False)
    df["height_numeric"] = pd.to_numeric(height_val, errors="coerce")

    # Convert cm → m
    df.loc[df["height_numeric"] > 3, "height_numeric"] /= 100

    return df


# -----------------------
# Load selected files
# -----------------------
dfs = []
for fname in selected_files:
    full_path = next((p for p in csv_files if os.path.basename(p) == fname), None)
    if full_path:
        df = load_and_clean_csv(full_path)
        df["team"] = os.path.splitext(fname)[0]
        dfs.append(df)

df_all = pd.concat(dfs, ignore_index=True)

# -----------------------
# Filters (NO POSITION)
# -----------------------
st.sidebar.subheader("Filters")

teams = sorted(df_all["team"].unique())
selected_team = st.sidebar.selectbox("Team", ["All"] + teams)

if selected_team != "All":
    df_filtered = df_all[df_all["team"] == selected_team].copy()
else:
    df_filtered = df_all.copy()

# Age filter
if df_filtered["age_numeric"].notna().any():
    min_age = int(df_filtered["age_numeric"].min())
    max_age = int(df_filtered["age_numeric"].max())
    age_range = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))
    df_filtered = df_filtered[
        (df_filtered["age_numeric"] >= age_range[0])
        & (df_filtered["age_numeric"] <= age_range[1])
    ]

# Foot filter
feet = sorted(df_all["foot"].dropna().unique())
selected_foot = st.sidebar.selectbox("Preferred Foot", ["All"] + feet)
if selected_foot != "All":
    df_filtered = df_filtered[df_filtered["foot"] == selected_foot]

# -----------------------
# Metrics
# -----------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Players", len(df_filtered))
col2.metric("Average Age", f"{df_filtered['age_numeric'].mean():.1f}")
col3.metric(
    "Total Market Value (€M)", f"{df_filtered['market_value_numeric'].sum() / 1e6:.2f}M"
)
col4.metric("Average Height (m)", f"{df_filtered['height_numeric'].mean():.2f}")

st.markdown("---")

# -----------------------
# Visualizations (NO POSITION)
# -----------------------
st.subheader("Age Distribution")
st.bar_chart(df_filtered["age_numeric"].dropna().value_counts().sort_index())

st.subheader("Top Market Values")
st.table(
    df_filtered.sort_values("market_value_numeric", ascending=False).head(10)[
        ["name", "team", "market_value", "market_value_numeric"]
    ]
)

st.markdown("---")

# -----------------------
# Full Table
# -----------------------
st.subheader("Player Table")

search = st.text_input("Search by player name")
df_show = df_filtered.copy()
if search:
    df_show = df_show[df_show["name"].str.contains(search, case=False, na=False)]

st.dataframe(df_show, height=500)

# Download
csv = df_show.to_csv(index=False)
st.download_button("📥 Download CSV", csv, "filtered_players.csv")

st.caption("Position column removed as requested.")
