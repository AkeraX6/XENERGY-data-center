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
if st.button("⬅️ Back to Menu", key="back_qaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or multiple QAQC files (Excel/CSV)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key="uploader_qaqc"
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

# Read & merge
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
with st.expander("⚙️ Processing Steps", expanded=False):

    steps_done = []
    total_deleted = 0

    # --- STEP 1 – Clean Density ---
    if "Density" in df.columns:
        before = len(df)

        df["Density"] = df["Density"].astype(str)
        df = df[~df["Density"].str.contains("[A-Za-z]", na=False)]
        df = df[~df["Density"].str.contains("-", na=False)]
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]

        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        total_deleted += deleted

        steps_done.append(f"🧹 Cleaned Density → removed {deleted} rows")
    else:
        steps_done.append("⚠️ Density column not found.")

    # --- STEP 2 – Remove negative coordinates ---
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)

        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")

        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]

        deleted = before - len(df)
        total_deleted += deleted

        steps_done.append(f"🧭 Removed {deleted} rows with invalid coordinates")
    else:
        steps_done.append("⚠️ Coordinate columns missing.")

    # --- STEP 3 – Clean Borehole (remove AUX + fix 45_8) ---
    borehole_col = None
    for col in df.columns:
        if "Borehole" in col or "Pozo" in col or "Hole" in col:
            borehole_col = col
            break

    if borehole_col:
        before = len(df)

        df = df[~df[borehole_col].astype(str).str.contains(
            r"\baux\b|\baux\d+|\ba\d+\b",
            flags=re.IGNORECASE,
            na=False
        )]

        df[borehole_col] = df[borehole_col].astype(str).str.replace(
            r"(\d+)_\d+", r"\1", regex=True
        )

        deleted = before - len(df)
        total_deleted += deleted

        steps_done.append(f"🔧 Cleaned Borehole → removed {deleted} AUX rows")
    else:
        steps_done.append("⚠️ Borehole column not found.")

    # --- STEP 4 – Extract EXPANSION + LEVEL ---
    if "Blast" in df.columns:

        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F0*(\d+)", expand=False)

        # FIXED LEVEL EXTRACTION (handles many formats)
        def extract_level(text):
            if pd.isna(text):
                return None
            text = str(text).upper()

            # First try BXXXX
            m = re.search(r"B0*(\d{3,4})", text)
            if m:
                return m.group(1)

            # Try 4-digit level anywhere
            m = re.search(r"(2\d{3}|3\d{3}|4\d{3})", text)
            if m:
                return m.group(1)

            return None

        df["Level"] = df["Blast"].apply(extract_level)

        # Place next to Blast
        cols = list(df.columns)
        b_index = cols.index("Blast")
        for c in ["Expansion", "Level"]:
            if c in cols:
                cols.remove(c)
        cols[b_index + 1:b_index + 1] = ["Expansion", "Level"]
        df = df[cols]

        steps_done.append("📌 Extracted Expansion & Level (now placed next to Blast)")
    else:
        steps_done.append("⚠️ Blast column not found.")

    # --- STEP 5 – Cross-fill Hole Length ---
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)

        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])

        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")

        deleted = before - len(df)
        total_deleted += deleted

        steps_done.append(f"📏 Cross-filled Hole Length → removed {deleted} empty rows")
    else:
        steps_done.append("⚠️ Hole Length columns missing.")

    # --- STEP 6 – Cross-fill Explosive ---
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)

        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")

        deleted = before - len(df)
        total_deleted += deleted

        steps_done.append(f"💥 Cross-filled Explosive → removed {deleted} empty rows")
    else:
        steps_done.append("⚠️ Explosive columns missing.")

    # --- STEP 7 – Clean Asset column ---
    asset_col = None
    for col in df.columns:
        if "Asset" in col:
            asset_col = col
            break

    if asset_col:
        before_nan = df[asset_col].isna().sum()

        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")

        after_nan = df[asset_col].isna().sum()
        fixed = before_nan - after_nan

        steps_done.append(f"🏷️ Cleaned Asset → {fixed} values fixed")

    else:
        steps_done.append("⚠️ Asset column not found.")

    # --- Summary lines ---
    steps_done.append(f"🧮 Total rows deleted: **{total_deleted}**")

    for step in steps_done:
        st.markdown(
            f"<div style='background:#eef8f0;padding:8px;border-radius:6px;margin-bottom:6px;'>{step}</div>",
            unsafe_allow_html=True
        )

# ==================================================
# DATE RANGE FOR FILE NAME
# ==================================================
date_col = None
for col in df.columns:
    if "Date" in col or "Fecha" in col:
        date_col = col
        break

file_suffix = ""
if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = df[date_col].dropna()
    if not valid_dates.empty:
        min_date = valid_dates.min().strftime("%d%m%y")
        max_date = valid_dates.max().strftime("%d%m%y")
        file_suffix = f"_{min_date}_{max_date}"

# ==================================================
# SHOW CLEANED RESULTS
# ==================================================
st.markdown("---")
st.subheader("✅ Cleaned & Merged Data Preview")
st.dataframe(df.head(15), use_container_width=True)
st.success(f"Final dataset: {len(df)} rows × {len(df.columns)} columns")

# ==================================================
# DOWNLOAD SECTION
# ==================================================
option = st.radio("Download:", ["⬇️ All Columns", "🧩 Selected Columns"], key="dlchoice_qaqc")

if option == "⬇️ All Columns":
    export_df = df
else:
    selected_columns = st.multiselect(
        "Select columns to export:",
        options=list(df.columns),
        default=[],
        key="colselect_qaqc"
    )
    export_df = df[selected_columns] if selected_columns else df

# Export Excel
excel_buf = io.BytesIO()
export_df.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

# Export CSV
csv_buf = io.StringIO()
export_df.to_csv(csv_buf, index=False, sep=";")

file_base = f"DGM_QAQC_Cleaned{file_suffix}"

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Export Excel",
        excel_buf,
        file_name=f"{file_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="dl_excel_qaqc"
    )
with col2:
    st.download_button(
        "📗 Export CSV",
        csv_buf.getvalue(),
        file_name=f"{file_base}.csv",
        mime="text/csv",
        use_container_width=True,
        key="dl_csv_qaqc"
    )

st.caption("Built by Maxam — Omar El Kendi")
