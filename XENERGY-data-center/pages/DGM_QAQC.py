import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — QAQC Data Filter (Multi-file)</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automatic cleaning, merging, and validation of QAQC drilling data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Dashboard
if st.button("⬅️ Back to Menu", key="back_dgmqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOADER
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or multiple QAQC files (Excel/CSV)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("📂 Please upload at least one Excel or CSV file to begin.")
    st.stop()

# ==================================================
# FILE READER
# ==================================================
def read_file(file):
    name = file.name.lower()
    try:
        if name.endswith(".csv"):
            sample = file.read(2048).decode("utf-8", errors="ignore")
            file.seek(0)
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(file, sep=sep)
        else:
            df = pd.read_excel(file)
        df["__SourceFile__"] = file.name
        return df
    except:
        st.error(f"❌ Error reading file {file.name}")
        return None

dfs = [read_file(f) for f in uploaded_files]
dfs = [d for d in dfs if d is not None]

df = pd.concat(dfs, ignore_index=True)

st.success(f"📌 {len(uploaded_files)} files merged — {len(df)} rows loaded.")
st.dataframe(df.head(8), use_container_width=True)

# ==================================================
# CLEANING SECTION
# ==================================================
total_deleted = 0

with st.expander("⚙️ Processing Summary", expanded=True):
    steps = []

    # STEP 1 – Clean Density
    if "Density" in df.columns:
        before = len(df)
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"🧹 Cleaned Density → {deleted} invalid rows removed.")

    # STEP 2 – Remove negative coordinates
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        cols_to_clean = ["Local X (Design)", "Local Y (Design)"]
        df[cols_to_clean] = df[cols_to_clean].apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=cols_to_clean)
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"📍 Removed negative coordinates → {deleted} rows.")

    # STEP 3 – Clean Borehole + remove AUX
    bore_col = next((c for c in df.columns if "Borehole" in c or "Pozo" in c or "Hole" in c), None)
    if bore_col:
        before = len(df)
        df = df[~df[bore_col].astype(str).str.contains("AUX|aux|REP", regex=True, na=False)]
        df[bore_col] = df[bore_col].astype(str).str.replace(r"(\d+)_\d+", r"\1", regex=True)
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"🕳 Removed AUX and fixed Borehole → {deleted} rows.")

    # STEP 4 – Expansion + Level from Blast
    if "Blast" in df.columns:
        before = len(df)

        # FIX: Detect 4-digit Level anywhere
        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F[_\-]?0*(\d+)", expand=False)
        df["Level"] = df["Blast"].astype(str).str.extract(r"(\d{4})", expand=False)

        # Convert to numbers
        df["Expansion"] = pd.to_numeric(df["Expansion"], errors="coerce")
        df["Level"] = pd.to_numeric(df["Level"], errors="coerce")

        deleted = before - len(df)
        steps.append("⛰ Extracted Expansion & Level from Blast.")

    # STEP 5 – Cross-fill Hole Length
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        cols = ["Hole Length (Design)", "Hole Length (Actual)"]
        df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
        df[cols] = df[cols].replace(0, pd.NA)

        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])

        df = df.dropna(subset=cols, how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"📏 Filled missing Hole Length → {deleted} rows removed.")

    # STEP 6 – Cross-fill Explosive
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        cols = ["Explosive (kg) (Design)", "Explosive (kg) (Actual)"]
        df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
        df[cols] = df[cols].replace(0, pd.NA)

        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

        df = df.dropna(subset=cols, how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"💥 Filled missing Explosive → {deleted} rows removed.")

    # STEP 7 – Clean Asset (keep numeric only)
    asset_col = next((c for c in df.columns if "Asset" in c), None)
    if asset_col:
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        steps.append("🏷 Cleaned Asset → kept only numeric values.")

    # === Final Cleaning Summary ===
    for s in steps:
        st.markdown(f"<div style='background:#e6fff1;padding:6px;border-radius:6px;'>{s}</div>", unsafe_allow_html=True)

    st.markdown(f"<p style='color:#b30000;font-weight:600;'>🧮 Total rows deleted: {total_deleted}</p>", unsafe_allow_html=True)

# ==================================================
# DATE RANGE FOR FILE NAME
# ==================================================
date_col = next((c for c in df.columns if "Date" in c or "Fecha" in c), None)
file_suffix = ""

if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    valid = df[date_col].dropna()
    if not valid.empty:
        min_date = valid.min().strftime("%d%m%y")
        max_date = valid.max().strftime("%d%m%y")
        file_suffix = f"_{min_date}_{max_date}"

# ==================================================
# RESULTS
# ==================================================
st.markdown("---")
st.subheader("📊 Final Cleaned Data Preview")
st.dataframe(df.head(20), use_container_width=True)
st.success(f"🧾 Final dataset: {len(df)} rows × {len(df.columns)} columns.")

# ==================================================
# DOWNLOADS
# ==================================================
st.markdown("---")
st.subheader("💾 Export Cleaned File")

choice = st.radio("Choose download type:", ["All Columns", "Select Columns"])

if choice == "Select Columns":
    selected = st.multiselect("Select columns to export:", df.columns, default=df.columns.tolist())
    export_df = df[selected] if selected else df
else:
    export_df = df

# Excel
excel_buf = io.BytesIO()
export_df.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

# TXT alternative separator
txt_buf = io.StringIO()
export_df.to_csv(txt_buf, index=False, sep=";")

filename = f"DGM_QAQC_Cleaned{file_suffix}"

col1, col2 = st.columns(2)
with col1:
    st.download_button("📘 Download Excel", excel_buf, f"{filename}.xlsx")

with col2:
    st.download_button("📄 Download TXT", txt_buf.getvalue(), f"{filename}.txt")

st.caption("Built by Maxam — Omar El Kendi")
