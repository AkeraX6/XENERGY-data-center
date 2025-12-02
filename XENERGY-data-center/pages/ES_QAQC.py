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
st.markdown("<p style='text-align:center; color:gray;'>Automatic cleaning, merging, and validation of QAQC drilling data (Excel & CSV supported).</p>", unsafe_allow_html=True)
st.markdown("---")

# ==================================================
# FILE UPLOAD
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
# FILE READER FUNCTION
# ==================================================
def read_any_file(file):
    """Reads Excel or CSV (auto-detects separator)."""
    name = file.name.lower()
    try:
        if name.endswith(".csv"):
            sample = file.read(2048).decode("utf-8", errors="ignore")
            file.seek(0)
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(file, sep=sep)
        else:
            df = pd.read_excel(file)
        return df
    except Exception as e:
        st.error(f"❌ Error reading {file.name}: {e}")
        return None

# Read and merge
dfs = [read_any_file(f) for f in uploaded_files if f is not None]
dfs = [d for d in dfs if d is not None]

if not dfs:
    st.error("❌ No valid files could be read.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)
st.success(f"✅ Successfully merged {len(dfs)} files — total rows: {len(df)}")
st.dataframe(df.head(10), use_container_width=True)

# ==================================================
# CLEANING STEPS
# ==================================================
with st.expander("⚙️ Processing Summary", expanded=False):
    steps_done = []
    total_removed = 0

    # STEP 1 — Clean Density
    if "Density" in df.columns:
        before = len(df)
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        deleted = before - len(df)
        total_removed += deleted
        steps_done.append(f"Density cleaned: removed {deleted} invalid rows")
    else:
        steps_done.append("⚠️ Column 'Density' not found")

    # STEP 2 — Remove negative X/Y
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        total_removed += deleted
        steps_done.append(f"Negative/invalid coordinates removed: {deleted} rows")
    else:
        steps_done.append("⚠️ Coordinates not found")

    # STEP 3 — Clean Borehole
    borehole_col = next((c for c in df.columns if "borehole" in c.lower() or "pozo" in c.lower() or "hole" in c.lower()), None)
    if borehole_col:
        before = len(df)
        df[borehole_col] = df[borehole_col].astype(str)
        df = df[~df[borehole_col].str.contains(r"\baux\b|\baux\d+|\ba\d+\b|P0?\d", flags=re.IGNORECASE, na=False)]
        df[borehole_col] = df[borehole_col].str.extract(r"(\d+)", expand=False)
        df[borehole_col] = pd.to_numeric(df[borehole_col], errors="coerce")
        df = df.dropna(subset=[borehole_col])
        deleted = before - len(df)
        total_removed += deleted
        steps_done.append(f"Borehole cleaned: deleted {deleted} AUX/invalid rows")
    else:
        steps_done.append("⚠️ No Borehole column found")

    # STEP 4 — Expansion + Level extraction
    if "Blast" in df.columns:
        before = len(df)
        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F0*(\d+)", expand=False)
        df["Level"] = df["Blast"].astype(str).str.extract(r"B0*(\d{3,4})", expand=False)
        df["Level"] = df["Level"].fillna(df[borehole_col])

        # Move next to Blast
        cols = list(df.columns)
        idx = cols.index("Blast") + 1
        cols.insert(idx, cols.pop(cols.index("Expansion")))
        cols.insert(idx+1, cols.pop(cols.index("Level")))
        df = df[cols]

        steps_done.append("Extracted Expansion + Level and aligned next to Blast")
    else:
        steps_done.append("⚠️ Column 'Blast' not found")

    # STEP 5 — Hole Length Crossfill
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        total_removed += deleted
        steps_done.append(f"Hole Length crossfilled: removed {deleted} rows")

    # STEP 6 — Explosive Crossfill
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        total_removed += deleted
        steps_done.append(f"Explosive crossfilled: removed {deleted} rows")

    # STEP 7 — Clean Asset (default 266 if missing)
    asset_col = next((c for c in df.columns if "asset" in c.lower()), None)
    if asset_col:
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        df[asset_col] = df[asset_col].fillna(266)
        steps_done.append("Asset cleaned → missing set to 266")

    # STEP 8 — Clean Water Level (replace "-", blanks → 0)
    water_col = next((c for c in df.columns if "water" in c.lower() or "agua" in c.lower()), None)
    if water_col:
        df[water_col] = df[water_col].astype(str).str.strip()
        df[water_col] = df[water_col].replace(["-", "_", "", " ", "NaN", "nan"], "0")
        df[water_col] = pd.to_numeric(df[water_col], errors="coerce").fillna(0)
        steps_done.append("Water Level cleaned → '-' or empty set to 0")

    # Final step message
    steps_done.append(f"Total rows removed: {total_removed}")

    # Show steps list
    for step in steps_done:
        st.markdown(f"✔️ {step}")

# ==================================================
# SHOW RESULTS
# ==================================================
st.markdown("---")
st.subheader("📊 Cleaned Data Preview")
st.dataframe(df.head(15), use_container_width=True)
st.success(f"Final dataset: {len(df)} rows × {len(df.columns)} columns")

# ==================================================
# DOWNLOAD
# ==================================================
option = st.radio("📥 Download option:", ["All Columns", "Select Columns"])
if option == "Select Columns":
    selected = st.multiselect("Select columns:", df.columns.tolist(), default=df.columns.tolist())
    export_df = df[selected]
else:
    export_df = df

date_col = next((c for c in df.columns if "Date" in c or "Fecha" in c), None)
suffix = ""
if date_col:
    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if not dates.empty:
        suffix = f"_{dates.min().strftime('%d%m%y')}_{dates.max().strftime('%d%m%y')}"

excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

st.download_button(
    "📘 Download Excel",
    excel_buffer,
    file_name=f"DGM_QAQC_Cleaned{suffix}.xlsx"
)

txt_buffer = io.StringIO()
export_df.to_csv(txt_buffer, index=False, sep=";")

st.download_button(
    "📄 Download TXT",
    txt_buffer.getvalue(),
    file_name=f"DGM_QAQC_Cleaned{suffix}.txt"
)

st.caption("🚀 Built by Maxam — Omar El Kendi")




