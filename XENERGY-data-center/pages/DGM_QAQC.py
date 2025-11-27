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
    "<p style='text-align:center; color:gray;'>"
    "Automatic cleaning, merging, and validation of QAQC drilling data (Excel & CSV supported)."
    "</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Dashboard (use unique key for this page)
if st.button("⬅️ Back to Menu", key="back_dgmqaqc_page"):
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
            df_local = pd.read_csv(file, sep=sep)
        else:
            df_local = pd.read_excel(file)
        return df_local
    except Exception as e:
        st.error(f"❌ Error reading {file.name}: {e}")
        return None

dfs = [read_any_file(f) for f in uploaded_files if f is not None]
dfs = [d for d in dfs if d is not None]

if not dfs:
    st.error("❌ No valid files could be read.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)
original_rows = len(df)

st.success(f"✅ Successfully merged {len(dfs)} files — total rows: {len(df)}")
st.subheader("📄 Original Data Preview")
st.dataframe(df.head(10), use_container_width=True)

# ==================================================
# CLEANING STEPS
# ==================================================
with st.expander("⚙️ See Processing Steps", expanded=False):
    steps_done = []
    total_deleted = 0  # to track total removed rows

    def add_step(msg, deleted=None):
        """Helper to register a step and accumulate deleted rows."""
        nonlocal total_deleted
        if deleted is not None:
            total_deleted += deleted
            msg = f"{msg} (removed {deleted} rows)."
        steps_done.append("✅ " + msg)

    # --- STEP 1 – Clean Density (invalid / <=0 / non-numeric) ---
    if "Density" in df.columns:
        before = len(df)
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        add_step("Cleaned 'Density' — kept only positive numeric values", deleted)
    else:
        steps_done.append("⚠️ Column 'Density' not found — no density cleaning applied.")

    # --- STEP 2 – Remove negative / invalid coordinates (Local X/Y Design) ---
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        add_step("Removed rows with negative or invalid Local X/Y (Design)", deleted)
    else:
        steps_done.append("⚠️ Missing coordinate columns (Local X (Design) / Local Y (Design)).")

    # --- STEP 3 – Clean Borehole (remove AUX/Pxx, convert to numeric ID) ---
    borehole_col = None
    for col in df.columns:
        if "Borehole" in col or "Pozo" in col or "Hole" in col:
            borehole_col = col
            break

    def parse_borehole(val):
        """
        Borehole cleaning rules:
        - Delete rows containing AUX (Aux, aux1, Aux 12, etc.)
        - Delete rows that are just Pxx (e.g. P02, P 02)
        - For valid rows, extract all integers and take the BIGGEST one:
          01A_402 → 402, 10_115 → 115, 488_1 → 488, 15_488 → 488, A.7 → 7, 0.5 414. → 414, etc.
        """
        if pd.isna(val):
            return pd.NA

        s = str(val).strip().upper()
        s = s.replace(",", ".")  # unify decimal separators

        # Delete AUX rows
        if re.search(r"\bAUX\b", s):
            return pd.NA

        # Delete patterns like "P02", "P 02", "P2" (only P + number)
        if re.fullmatch(r"P\s*0*\d+", s):
            return pd.NA

        # Delete patterns like "A1", "A 2" (plain A + number, not A.7/A,3 etc.)
        if re.fullmatch(r"A\s*\d+", s):
            return pd.NA

        # Extract all integer groups and keep the biggest one
        nums = re.findall(r"\d+", s)
        if not nums:
            return pd.NA

        ints = [int(n) for n in nums]
        return max(ints)

    if borehole_col:
        before = len(df)
        cleaned = df[borehole_col].apply(parse_borehole)
        df[borehole_col] = cleaned
        df = df.dropna(subset=[borehole_col])
        deleted = before - len(df)
        add_step(
            f"Cleaned '{borehole_col}' — removed AUX/Pxx rows and normalized values like '45_8' → '45'",
            deleted,
        )
    else:
        steps_done.append("⚠️ Borehole column not found (no AUX / ID cleaning applied).")

    # --- STEP 4 – Extract Expansion and Level from Blast ---
    def extract_expansion_level(text):
        if pd.isna(text):
            return None, None
        t = str(text).upper()

        # Expansion: F12, F_12, F-12, F012...
        xp_match = re.search(r"F[_\-]?0*(\d{1,2})", t)
        expansion = int(xp_match.group(1)) if xp_match else None

        # Level: try Bxxx/Bxxxx first (B_2460, B2460, B-2460)
        lvl_match = re.search(r"B[_\-]?0*(\d{3,4})", t)
        if lvl_match:
            level = int(lvl_match.group(1))
        else:
            # Fallback: any 4-digit between 2000–4999 (common bench levels)
            lvl_match = re.search(r"\b(2\d{3}|3\d{3}|4\d{3})\b", t)
            level = int(lvl_match.group(1)) if lvl_match else None

        return expansion, level

    if "Blast" in df.columns:
        xp_list, lvl_list = zip(*df["Blast"].apply(extract_expansion_level))
        df["Expansion"] = xp_list
        df["Level"] = lvl_list

        # Place Expansion & Level right after Blast
        cols = list(df.columns)
        # Remove if already in cols to reinsert in correct position
        for c in ["Expansion", "Level"]:
            if c in cols:
                cols.remove(c)
        blast_idx = cols.index("Blast")
        cols[blast_idx + 1:blast_idx + 1] = ["Expansion", "Level"]
        df = df[cols]

        add_step("Extracted 'Expansion' and 'Level' from Blast and placed them next to 'Blast'")
    else:
        steps_done.append("⚠️ Column 'Blast' not found — Expansion/Level not created.")

    # --- STEP 5 – Cross-fill Hole Length (Design/Actual) ---
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])

        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        add_step("Cross-filled Hole Length (Design/Actual)", deleted)
    else:
        steps_done.append("⚠️ Hole Length columns not found (Design/Actual).")

    # --- STEP 6 – Cross-fill Explosive (Design/Actual) ---
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce").replace(0, pd.NA)

        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        add_step("Cross-filled Explosive (kg) (Design/Actual)", deleted)
    else:
        steps_done.append("⚠️ Explosive (kg) columns not found (Design/Actual).")

    # --- STEP 7 – Clean Asset column (keep only numbers) ---
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
        fixed = max(after_nan - before_nan, 0)  # just indicative
        steps_done.append(f"✅ Cleaned '{asset_col}' — extracted numeric Asset ID ({fixed} values adjusted).")
    else:
        steps_done.append("⚠️ 'Asset' column not found — no Asset cleaning applied.")

    # --- DISPLAY ALL STEPS ---
    for step in steps_done:
        st.markdown(
            f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
            f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
            unsafe_allow_html=True
        )

    # --- TOTAL REMOVED ROWS ---
    final_rows = len(df)
    total_deleted = original_rows - final_rows
    st.markdown(
        f"<div style='background-color:#ffe8e8;padding:10px;border-radius:8px;margin-top:10px;'>"
        f"<span style='color:#b00020;font-weight:600;'>🧹 Total rows removed in all filters: {total_deleted}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

# ==================================================
# DATE RANGE EXTRACTION (for filename)
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
