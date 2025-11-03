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

# 🔙 Back to Dashboard
if st.button("⬅️ Back to Menu", key="back_dgmqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

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
        df["__SourceFile__"] = file.name
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
with st.expander("⚙️ See Processing Steps", expanded=False):
    steps_done = []

    # --- STEP 1 – Clean Density ---
    if "Density" in df.columns:
        before = len(df)
        df = df[~df["Density"].astype(str).str.contains("[A-Za-z]", na=False)]  # remove letters
        df = df[~df["Density"].astype(str).str.contains("-", na=False)]          # remove negatives / symbols
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        steps_done.append(f"✅ Cleaned 'Density' — removed {deleted} invalid rows.")
    else:
        steps_done.append("⚠️ Column 'Density' not found.")

    # --- STEP 2 – Remove negative coordinates ---
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        steps_done.append(f"✅ Removed {deleted} rows with negative or invalid coordinates.")
    else:
        steps_done.append("⚠️ Missing coordinate columns (Local X/Y).")

    # --- STEP 3 – Clean Borehole (remove AUX, fix numbers) ---
    borehole_col = None
    for col in df.columns:
        if "Borehole" in col or "Pozo" in col or "Hole" in col:
            borehole_col = col
            break

    if borehole_col:
        before = len(df)
        df = df[~df[borehole_col].astype(str).str.contains(r"\baux\b|\baux\d+|\ba\d+\b", flags=re.IGNORECASE, na=False)]
        df[borehole_col] = df[borehole_col].astype(str).str.replace(r"(\d+)_\d+", r"\1", regex=True)
        deleted = before - len(df)
        steps_done.append(f"✅ Cleaned '{borehole_col}' — removed {deleted} AUX rows and fixed numbers like 45_8 → 45.")
    else:
        steps_done.append("⚠️ Borehole column not found.")

    # --- STEP 4 – Extract Expansion and Level from Blast ---
    if "Blast" in df.columns:
        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F0*(\d+)", expand=False)
        df["Level"] = df["Blast"].astype(str).str.extract(r"B0*(\d{3,4})", expand=False)

        cols = list(df.columns)
        blast_idx = cols.index("Blast")
        for c in ["Expansion", "Level"]:
            if c in cols:
                cols.remove(c)
        cols[blast_idx + 1:blast_idx + 1] = ["Expansion", "Level"]
        df = df[cols]
        steps_done.append("✅ Extracted 'Expansion' and 'Level' columns from Blast.")
    else:
        steps_done.append("⚠️ Column 'Blast' not found.")

    # --- STEP 5 – Cross-fill Hole Length (Design/Actual) ---
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])

        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        steps_done.append(f"✅ Cross-filled Hole Length values (removed {deleted} empty rows).")
    else:
        steps_done.append("⚠️ Hole Length columns not found.")

    # --- STEP 6 – Cross-fill Explosive (Design/Actual) ---
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        steps_done.append(f"✅ Cross-filled Explosive values (removed {deleted} empty rows).")
    else:
        steps_done.append("⚠️ Explosive columns not found.")

    # --- STEP 7 – Clean Asset column (keep only numbers) ---
    asset_col = None
    for col in df.columns:
        if "Asset" in col:
            asset_col = col
            break
    if asset_col:
        before = df[asset_col].isna().sum()
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        after = df[asset_col].isna().sum()
        steps_done.append(f"✅ Cleaned 'Asset' column — converted to numeric ({before - after} values fixed).")
    else:
        steps_done.append("⚠️ 'Asset' column not found.")

    # --- Display steps ---
    for step in steps_done:
        st.markdown(
            f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
            f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
            unsafe_allow_html=True
        )

# ==================================================
# SHOW CLEANED RESULTS
# ==================================================
st.markdown("---")
st.subheader("✅ Cleaned & Merged Data Preview")
st.dataframe(df.head(15), use_container_width=True)
st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

# ==================================================
# DOWNLOAD SECTION
# ==================================================
st.markdown("---")
st.subheader("💾 Export Cleaned File")

option = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])

if option == "⬇️ Download All Columns":
    export_df = df
else:
    selected_columns = st.multiselect(
        "Select columns (drag to reorder):",
        options=list(df.columns),
        default=[]
    )
    export_df = df[selected_columns] if selected_columns else df

# --- Export Files ---
excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

csv_buffer = io.StringIO()
export_df.to_csv(csv_buffer, index=False, sep=";")

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel File",
        excel_buffer,
        file_name="DGM_QAQC_Merged_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
with col2:
    st.download_button(
        "📗 Download CSV File",
        csv_buffer.getvalue(),
        file_name="DGM_QAQC_Merged_Cleaned.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi -")
