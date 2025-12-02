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
            # Detect separator
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
# HELPER FUNCTIONS
# ==================================================
def clean_borehole_value(raw):
    """
    Apply all Borehole rules:
      - Remove rows with AUX / aux / Aux1 / P02 etc. (return None)
      - Convert cases like:
        01A_402 → 402, 10_115 → 115, 4_441 → 441, 05A_401 → 401,
        488_1 → 488, 401_2 → 401, 01R_106 → 106, 02_225 → 225,
        308_4 → 308, 445 A → 445, 218_6 → 218, 401_8A → 401,
        416_10B → 416, 201_8 → 201, 101_10 → 101, 02_101 → 101,
        441_2 → 441, 15_488 → 488, 11C_866 → 866, 14B_316 → 316,
        A.7 → 7, A.15 → 15, A,3 → 3, a20 → 20,
        01A_101 → 101, 1R_107 → 107, 11B_416 → 416,
        7A_506 → 506, 25B_471 → 471, 618 → 618,
        311_05B → 311, 446a → 446, "0.5 414." → 414
    Strategy:
      - If contains "aux" or pattern like "p02" → delete row (return None).
      - Extract ALL integers from the string and keep the LARGEST one.
    """
    if pd.isna(raw):
        return None

    s = str(raw).strip().lower()

    # Delete AUX-type and P02-type rows
    if re.search(r"\baux\b", s, flags=re.IGNORECASE) or re.search(r"\baux\d*\b", s, flags=re.IGNORECASE):
        return None
    if re.search(r"\bp0\d+\b", s):  # P02, p03, etc.
        return None

    # Extract all numbers
    nums = re.findall(r"\d+", s)
    if not nums:
        return None

    nums_int = [int(n) for n in nums]
    return max(nums_int)


def extract_expansion_level(text):
    """
    Extract Expansion (Fxx) and Level (Bxxxx or 2xxx/3xxx/4xxx) from Blast string.
    - Expansion: F0*XX (F12, F_12, F-12, F012, etc.)
    - Level:
        1) If B0*#### exists → that number
        2) Else any 4-digit 2xxx/3xxx/4xxx in the string
    """
    if pd.isna(text):
        return None, None
    t = str(text).upper()

    # Expansion
    xp = None
    m_xp = re.search(r"F[_\-]?0*(\d{1,2})", t)
    if m_xp:
        xp = int(m_xp.group(1))

    # Level
    lvl = None
    m_lvl = re.search(r"B0*(\d{3,4})", t)
    if m_lvl:
        lvl = int(m_lvl.group(1))
    else:
        # Fallback: any 4-digit bench level 2000–4999
        m_lvl2 = re.search(r"\b(2\d{3}|3\d{3}|4\d{3})\b", t)
        if m_lvl2:
            lvl = int(m_lvl2.group(1))

    return xp, lvl


# ==================================================
# CLEANING STEPS
# ==================================================
with st.expander("⚙️ See Processing Steps", expanded=False):
    steps_done = []
    rows_after_each_step = []

    # STEP 1 – Clean Density
    if "Density" in df.columns:
        before = len(df)
        # remove letters or obvious strange strings
        df = df[~df["Density"].astype(str).str.contains("[A-Za-z]", na=False)]
        # remove minus sign entries (negatives or weird hyphen uses)
        df = df[~df["Density"].astype(str).str.contains("-", na=False)]
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        rows_after_each_step.append(("Density filter", deleted))
        steps_done.append(f"✅ Cleaned 'Density' — removed {deleted} invalid rows.")
    else:
        steps_done.append("⚠️ Column 'Density' not found.")

    # STEP 2 – Remove negative / invalid coordinates
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        rows_after_each_step.append(("Coordinate filter", deleted))
        steps_done.append(f"✅ Removed {deleted} rows with negative or invalid coordinates.")
    else:
        steps_done.append("⚠️ Missing coordinate columns (Local X/Y).")

    # STEP 3 – Clean Borehole
    borehole_col = None
    for col in df.columns:
        if "Borehole" in col or "Pozo" in col or "Hole" in col:
            borehole_col = col
            break

    if borehole_col:
        before = len(df)
        # Apply cleaning function
        df[borehole_col] = df[borehole_col].apply(clean_borehole_value)
        # Drop rows where Borehole could not be resolved (None)
        df = df.dropna(subset=[borehole_col])
        df[borehole_col] = df[borehole_col].astype(int)
        deleted = before - len(df)
        rows_after_each_step.append(("Borehole cleaning", deleted))
        steps_done.append(
            f"✅ Cleaned '{borehole_col}' — removed {deleted} AUX/invalid rows and normalized numbers."
        )
    else:
        steps_done.append("⚠️ Borehole column not found.")

    # STEP 4 – Extract Expansion and Level from Blast
    if "Blast" in df.columns:
        xpansion_list = []
        level_list = []

        for val in df["Blast"]:
            xp, lvl = extract_expansion_level(val)
            xpansion_list.append(xp)
            level_list.append(lvl)

        df["Expansion"] = xpansion_list
        df["Level"] = level_list

        # Reorder: Blast, Expansion, Level
        cols = list(df.columns)
        blast_idx = cols.index("Blast")
        # Remove if already exist to re-insert correctly
        if "Expansion" in cols:
            cols.remove("Expansion")
        if "Level" in cols:
            cols.remove("Level")
        cols[blast_idx + 1:blast_idx + 1] = ["Expansion", "Level"]
        df = df[cols]

        steps_done.append("✅ Extracted 'Expansion' and 'Level' columns from Blast and placed next to it.")
    else:
        steps_done.append("⚠️ Column 'Blast' not found.")

    # STEP 5 – Cross-fill Hole Length (Design/Actual)
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce").replace(0, pd.NA)
        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        rows_after_each_step.append(("Hole Length cross-fill", deleted))
        steps_done.append(f"✅ Cross-filled Hole Length values (removed {deleted} empty rows).")
    else:
        steps_done.append("⚠️ Hole Length columns not found.")

    # STEP 6 – Cross-fill Explosive (Design/Actual)
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce").replace(0, pd.NA)
        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        rows_after_each_step.append(("Explosive cross-fill", deleted))
        steps_done.append(f"✅ Cross-filled Explosive values (removed {deleted} empty rows).")
    else:
        steps_done.append("⚠️ Explosive columns not found.")

    # STEP 7 – Clean Asset column (keep only numbers, invalid→266)
    asset_col = None
    for col in df.columns:
        if "Asset" in col:
            asset_col = col
            break

    if asset_col:
        before_na = df[asset_col].isna().sum()
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        df[asset_col] = df[asset_col].fillna(266)
        after_na = df[asset_col].isna().sum()
        fixed = before_na - after_na  # for info only
        steps_done.append(
            f"✅ Cleaned '{asset_col}' — kept only numbers and filled invalid/missing with 266."
        )
    else:
        steps_done.append("⚠️ 'Asset' column not found.")

    # STEP 8 – Clean Water Level / Water Presence → everything numeric, invalid→0
    water_col = None
    for col in df.columns:
        name = col.lower()
        if "water" in name and ("level" in name or "presence" in name):
            water_col = col
            break

    if water_col:
        df[water_col] = pd.to_numeric(df[water_col], errors="coerce")
        df[water_col] = df[water_col].fillna(0)
        steps_done.append(f"✅ Cleaned '{water_col}' — all values numeric, invalid set to 0.")
    else:
        steps_done.append("⚠️ Water Level/Presence column not found.")

    # --- Display steps and totals ---
    for step in steps_done:
        st.markdown(
            f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
            f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
            unsafe_allow_html=True
        )

    total_deleted = original_rows - len(df)
    st.markdown(
        f"<div style='background-color:#eef2ff;padding:10px;border-radius:8px;margin-top:4px;'>"
        f"<b>📊 Total rows removed during cleaning: {total_deleted}</b></div>",
        unsafe_allow_html=True
    )

# ==================================================
# DATE RANGE EXTRACTION (for file name)
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



