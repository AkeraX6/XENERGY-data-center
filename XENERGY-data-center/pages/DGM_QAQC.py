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
st.markdown(
    "<p style='text-align:center; color:gray;'>Automatic cleaning, merging, and validation of QAQC drilling data (Excel & CSV supported).</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Dashboard (unique key to avoid duplicate ID error)
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
            # Peek to detect separator
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

dfs = [read_any_file(f) for f in uploaded_files if f is not None]
dfs = [d for d in dfs if d is not None]

if not dfs:
    st.error("❌ No valid files could be read.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)
rows_initial = len(df)

st.success(f"✅ Successfully merged {len(dfs)} files — total rows: {len(df)}")
st.subheader("📄 Original Data Preview")
st.dataframe(df.head(10), use_container_width=True)

# ==================================================
# HELPER: CLEAN BOREHOLE
# ==================================================
def clean_borehole_value(val):
    """
    Apply all your Borehole rules:
    - Remove rows with AUX / aux / Aux1 / aux1 / Aux 1 / A1 / A2 / P02, etc.
    - Convert patterns like:
      01A_402  → 402
      10_115   → 115
      4_441    → 441
      488_1    → 488
      15_488   → 488
      445 A    → 445
      A.7      → 7
      A.15     → 15
      A,3      → 3
      a20      → 20
      0.5 414. → 414
      etc.
    """
    if pd.isna(val):
        return None

    s = str(val).strip().lower()

    # ---- DELETE ROW CASES ----
    # AUX variants
    if re.search(r"\baux\b", s) or re.search(r"\baux\d*\b", s):
        return None
    # A1, A2, a1, a2, etc. SOLO
    if re.fullmatch(r"a\d+", s):
        return None
    # P02 exactly (or similar like p02)
    if re.fullmatch(r"p0*2", s):
        return None

    # ---- NUMERIC EXTRACTION ----
    # Replace commas by dots to avoid "A,3" being split weirdly
    s_norm = s.replace(",", ".")
    nums = re.findall(r"\d+", s_norm)
    if not nums:
        return None

    ints = [int(n) for n in nums]

    # First look for the FIRST integer >= 100 (3+ digits) scanning left-to-right
    for n in ints:
        if n >= 100:
            return n

    # If no 3+ digit number, keep the last integer (e.g. A.7 → 7, A.15 → 15)
    return ints[-1]

# ==================================================
# CLEANING STEPS
# ==================================================
with st.expander("⚙️ See Processing Steps", expanded=False):
    steps_done = []
    rows_before_step = len(df)

    # --- STEP 1 – Clean Density (invalid/letters/zero/negative) ---
    if "Density" in df.columns:
        before = len(df)
        # Remove rows where Density has letters
        df = df[~df["Density"].astype(str).str.contains("[A-Za-z]", na=False)]
        # Convert to numeric
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        # Remove NaN or <= 0
        df = df[df["Density"] > 0]
        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        steps_done.append(f"✅ Cleaned 'Density' — removed {deleted} invalid rows.")
    else:
        steps_done.append("⚠️ Column 'Density' not found.")

    # --- STEP 2 – Remove negative coordinates (Local X/Y Design) ---
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

    # --- STEP 3 – Clean Borehole (AUX deletion + number extraction) ---
    borehole_col = None
    for col in df.columns:
        if "Borehole" in col or "Pozo" in col or "Hole" in col:
            borehole_col = col
            break

    if borehole_col:
        before = len(df)
        # Apply cleaning
        df[borehole_col] = df[borehole_col].apply(clean_borehole_value)
        # Drop rows where borehole cleaning returned None
        df = df.dropna(subset=[borehole_col])
        deleted = before - len(df)
        steps_done.append(
            f"✅ Cleaned '{borehole_col}' — removed {deleted} AUX/invalid rows and normalized numbers (e.g., 45_8 → 45)."
        )
    else:
        steps_done.append("⚠️ Borehole column not found.")

    # --- STEP 4 – Extract Expansion and Level from Blast ---
    def extract_expansion(text):
        if pd.isna(text):
            return pd.NA
        t = str(text).upper()
        m = re.search(r"F0*(\d+)", t)
        return int(m.group(1)) if m else pd.NA

    def extract_level(text):
        if pd.isna(text):
            return pd.NA
        t = str(text).upper()
        # Case 1: explicit B2460 / B2610
        m = re.search(r"B0*(\d{3,4})", t)
        if m:
            return int(m.group(1))
        # Case 2: 4-digit bench 2000–4999 anywhere in text (e.g. F12_2610_19C)
        m = re.search(r"(2\d{3}|3\d{3}|4\d{3})", t)
        if m:
            return int(m.group(1))
        return pd.NA

    if "Blast" in df.columns:
        df["Expansion"] = df["Blast"].apply(extract_expansion)
        df["Level"] = df["Blast"].apply(extract_level)

        # Reorder columns so: Blast, Expansion, Level
        cols = list(df.columns)
        blast_idx = cols.index("Blast")

        # Ensure Expansion & Level exist and then reinsert
        for c in ["Expansion", "Level"]:
            if c in cols:
                cols.remove(c)
        cols[blast_idx + 1:blast_idx + 1] = ["Expansion", "Level"]
        df = df[cols]

        steps_done.append("✅ Extracted 'Expansion' and 'Level' from Blast and placed them next to 'Blast'.")
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
        before_na = df[asset_col].isna().sum()
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        after_na = df[asset_col].isna().sum()
        fixed = before_na - after_na
        steps_done.append(f"✅ Cleaned '{asset_col}' — converted to numeric ({max(fixed, 0)} values fixed).")
    else:
        steps_done.append("⚠️ 'Asset' column not found.")

    # --- TOTAL REMOVED ---
    rows_final = len(df)
    total_deleted = rows_initial - rows_final
    steps_done.append(f"📉 Total rows removed by all filters: {total_deleted}")

    # --- Display steps ---
    for step in steps_done:
        st.markdown(
            f"<div style='background-color:#e8f8f0;padding:8px;border-radius:8px;margin-bottom:6px;'>"
            f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
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
    try:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        valid_dates = df[date_col].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().strftime("%d%m%y")
            max_date = valid_dates.max().strftime("%d%m%y")
            file_suffix = f"_{min_date}_{max_date}"
    except Exception:
        pass  # If date parsing fails, just skip suffix

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

file_base = f"DGM_QAQC_Cleaned{file_suffix}"

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel File",
        excel_buffer,
        file_name=f"{file_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
with col2:
    st.download_button(
        "📗 Download CSV File",
        csv_buffer.getvalue(),
        file_name=f"{file_base}.csv",
        mime="text/csv",
        use_container_width=True
    )

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi -")
