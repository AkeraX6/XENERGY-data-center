import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and preparation of QAQC drilling data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def read_csv_smart(file_obj):
    """Detect delimiter and encoding for CSVs more robustly."""
    import csv

    sample_bytes = file_obj.read(8192)
    file_obj.seek(0)

    encodings_to_try = ("utf-8", "cp1252", "latin1", "iso-8859-1")
    delimiters = [",", ";", "\t", "|"]

    for enc in encodings_to_try:
        try:
            text = sample_bytes.decode(enc, errors="replace")
        except Exception:
            continue

        sep = None
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(text, delimiters="".join(delimiters))
            sep = dialect.delimiter
        except Exception:
            if text.count(";") > text.count(","):
                sep = ";"
            elif "\t" in text:
                sep = "\t"
            elif "|" in text:
                sep = "|"
            else:
                sep = ","

        try:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep=sep, engine="python", encoding=enc)
        except Exception:
            file_obj.seek(0)
            continue

    file_obj.seek(0)
    return pd.read_csv(file_obj, sep=None, engine="python", encoding="latin1")


def _replace_dash_with_na(series: pd.Series) -> pd.Series:
    """Treat '-' (and common variants) as missing."""
    if series is None:
        return series
    return series.replace(["-", " -", "- ", "—", "–", "", "\xa0"], pd.NA)


def _to_numeric(series: pd.Series) -> pd.Series:
    """Dash → NA then numeric."""
    return pd.to_numeric(_replace_dash_with_na(series), errors="coerce")


def find_water_level_column(df: pd.DataFrame):
    """
    Find water level column even if it is called:
    'Water lev', 'Water level', 'WaterLevel', 'WATER LEV', etc.
    """
    for c in df.columns:
        key = re.sub(r"\s+", "", str(c).strip().lower())
        if ("water" in key) and ("lev" in key):
            return c
    return None


def extract_level_from_blast(text):
    """Level = first 4-digit block in Blast (e.g. 2620_E07_5001 Ene 02 → 2620)."""
    if pd.isna(text):
        return None
    m = re.search(r"(\d{4})", str(text))
    return int(m.group(1)) if m else None


def extract_expansion_from_blast(text):
    """
    Expansion from Blast examples with special mappings:
      - N17B → 170
      - N17 → 17
      - PL1S → 111
      - PL1 → 1
      - S04 → 4
      - L05 → 5
      - E07 → 7
      etc.
    """
    if pd.isna(text):
        return None
    txt = str(text).upper()
    
    # Special cases first (most specific to least specific)
    if "N17B" in txt:
        return 170
    if "PL1S" in txt:
        return 111
    
    # Then check for general patterns
    # N17 → 17
    m = re.search(r"N(\d{1,2})(?![A-Z])", txt)
    if m:
        return int(m.group(1))
    
    # PL1 → 1 (without S)
    m = re.search(r"PL(\d{1,2})(?![A-Z])", txt)
    if m:
        return int(m.group(1))
    
    # Standard patterns: S04=4, L05=5, E07=7
    m = re.search(r"(?:S|L|E)(\d{1,2})", txt)
    if m:
        return int(m.group(1))
    
    return None


def parse_borehole_and_grid(raw_val):
    """
    From Borehole string get:
      - Grid: first numeric block before '_' (e.g. 5001_255 → 5001)
      - Borehole number with B/C/D logic:
          6001_B267 → 100000267
          6001_C045 → 20000045
          6001_D016 → 16
          5001_255  → 255
          B 125     → 100000125
          b002      → 1000002
      - Rows with Aux* or forms like a1 / a2 / a are invalid (return None for borehole).
      - Empty borehole returns ("", grid) → filled later by counter.
    """
    if pd.isna(raw_val):
        return None, ""

    s = str(raw_val).strip()
    if s == "":
        return None, ""  # will be filled later

    s = re.sub(r"\s+", "", s)

    if "_" in s:
        left, right = s.split("_", 1)
        grid = int(left) if left.isdigit() else None
        suffix = right
    else:
        grid = None
        suffix = s

    suffix_low = suffix.lower()

    if suffix_low.startswith("aux"):
        return grid, None

    m = re.match(r"^([a-z])(\d+)$", suffix_low)
    if m:
        letter, num = m.groups()
        if letter == "b":
            return grid, int("100000" + num)
        elif letter == "c":
            return grid, int("200000" + num)
        elif letter == "d":
            return grid, int(num)
        else:
            return grid, None

    if suffix_low.isdigit():
        return grid, int(suffix_low)

    return grid, None


def fill_boreholes_by_blast(df):
    """Fill empty Borehole ('') within each Blast with sequential IDs starting at 10000."""
    def _fill_group(group):
        counter = 10000
        new_vals = []
        for v in group["Borehole"]:
            if v == "" or pd.isna(v):
                new_vals.append(counter)
                counter += 1
            else:
                new_vals.append(v)
        group["Borehole"] = new_vals
        return group

    return df.groupby("Blast", group_keys=False).apply(_fill_group)


def cross_fill_pair(df, col_a, col_b, steps_done, label):
    """Cross-fill col_a <-> col_b treating empty AND '-' as missing."""
    if col_a not in df.columns or col_b not in df.columns:
        steps_done.append(f"⚠️ {label}: columns not found ({col_a}, {col_b}).")
        return df

    df[col_a] = _replace_dash_with_na(df[col_a])
    df[col_b] = _replace_dash_with_na(df[col_b])

    df[col_a] = df[col_a].fillna(df[col_b])
    df[col_b] = df[col_b].fillna(df[col_a])

    steps_done.append(f"✅ Cross-filled {label} (empty OR '-' treated as missing).")
    return df


def process_file(df):
    """Apply all cleaning steps to a dataframe. Returns cleaned df and list of steps."""
    steps_done = []

    # STEP 1 – Clean invalid Density values
    if "Density" in df.columns:
        before = len(df)
        df["Density_clean"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density_clean"].notna() & (df["Density_clean"] > 0)]
        deleted = before - len(df)
        df.drop(columns=["Density_clean"], inplace=True)
        steps_done.append(
            f"✅ Cleaned Density: removed {deleted} invalid rows (letters, negatives, symbols, empty or 0)."
        )
    else:
        steps_done.append("❌ Column 'Density' not found in the file.")

    # STEP 2 – Remove negative coordinates (Local Design)
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = _to_numeric(df["Local X (Design)"])
        df["Local Y (Design)"] = _to_numeric(df["Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        steps_done.append(f"✅ Removed {deleted} rows with negative local coordinates.")
    else:
        steps_done.append("❌ Missing columns 'Local X (Design)' or 'Local Y (Design)'.")

    # STEP 3 – Level & Expansion from Blast, Grid & Borehole from Borehole
    if "Blast" in df.columns:
        df["Level"] = df["Blast"].apply(extract_level_from_blast)
        df["Expansion"] = df["Blast"].apply(extract_expansion_from_blast)

        if "Borehole" in df.columns:
            grids = []
            bores = []
            for v in df["Borehole"]:
                grid, bore = parse_borehole_and_grid(v)
                grids.append(grid)
                bores.append(bore if bore is not None else None if v is not None else "")
            df["Grid"] = grids
            df["Borehole"] = bores

            before_invalid = len(df)
            df = df[df["Borehole"].notna()]
            deleted_invalid = before_invalid - len(df)

            df["Borehole"] = df["Borehole"].apply(lambda x: "" if x is None else x)
            df = fill_boreholes_by_blast(df)

            steps_done.append(
                f"✅ Parsed Level & Expansion from Blast (supports N/PL/L/S/E), Grid & Borehole from Borehole "
                f"({deleted_invalid} invalid/aux/aX rows removed)."
            )

            cols = list(df.columns)
            for c in ["Level", "Expansion", "Grid", "Borehole"]:
                if c in cols:
                    cols.remove(c)
            if "Blast" in cols:
                idx = cols.index("Blast")
                cols[idx + 1:idx + 1] = ["Level", "Expansion", "Grid", "Borehole"]
                df = df[cols]
        else:
            steps_done.append("⚠️ Column 'Borehole' not found. Only Level/Expansion from Blast were created.")
    else:
        steps_done.append("❌ Column 'Blast' not found in file. Level/Expansion/Grid were not created.")

    # STEP 4 – Hole Length cross-fill (empty OR '-')
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Hole Length (Design)", "Hole Length (Actual)", steps_done, "Hole Length")
        df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"🗑️ Hole Length: removed {deleted} rows where BOTH Design & Actual remained empty/'-'.")
    else:
        steps_done.append("⚠️ Hole Length columns not found.")

    # STEP 5 – Explosive cross-fill (empty OR '-')
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Explosive (kg) (Design)", "Explosive (kg) (Actual)", steps_done, "Explosive (kg)")
        df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"🗑️ Explosive: removed {deleted} rows where BOTH Design & Actual remained empty/'-'.")
    else:
        steps_done.append("⚠️ Explosive columns not found.")

    # STEP 6 – Stemming cross-fill (empty OR '-')  ✅ NEW
    if "Stemming (Design)" in df.columns and "Stemming (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Stemming (Design)", "Stemming (Actual)", steps_done, "Stemming")
        df.dropna(subset=["Stemming (Design)", "Stemming (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"🗑️ Stemming: removed {deleted} rows where BOTH Design & Actual remained empty/'-'.")
    else:
        steps_done.append("⚠️ Stemming columns not found (skipped).")

    # STEP 7 – Water Level: convert '-' to 0 (supports 'Water lev', etc.) ✅ FIXED
    water_col = find_water_level_column(df)
    if water_col:
        before = len(df)
        df[water_col] = df[water_col].astype(str).str.strip()
        df[water_col] = df[water_col].replace(["-", "—", "–", ""], "0")
        df[water_col] = pd.to_numeric(df[water_col], errors="coerce").fillna(0)
        steps_done.append(f"✅ '{water_col}': converted '-' / blanks to 0.")
    else:
        steps_done.append("ℹ️ Water level column not detected (skipped).")

    # STEP 8 – Clean Asset column
    asset_col = next((c for c in df.columns if "Asset" in c), None)
    if asset_col:
        before_non_numeric = df[asset_col].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        steps_done.append(
            f"✅ Cleaned '{asset_col}' column (removed letters; {before_non_numeric} entries contained text)."
        )
    else:
        steps_done.append("⚠️ 'Asset' column not found.")

    # STEP 9 – Move Blast Date to the end (if it exists)
    if "Blast Date" in df.columns:
        cols = list(df.columns)
        cols.remove("Blast Date")
        cols.append("Blast Date")
        df = df[cols]
        steps_done.append("✅ Moved 'Blast Date' column to the end of the table.")

    return df, steps_done


# ==========================================================
# FILE UPLOAD (MULTIPLE FILES)
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload your files",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs_raw = []
    all_dfs_cleaned = []
    all_steps = {}

    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name.lower()

        if file_name.endswith(".csv"):
            df = read_csv_smart(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        all_dfs_raw.append(df)
        df_cleaned, steps = process_file(df)
        all_dfs_cleaned.append(df_cleaned)
        all_steps[uploaded_file.name] = steps

    merged_df_raw = pd.concat(all_dfs_raw, ignore_index=True)
    merged_df = pd.concat(all_dfs_cleaned, ignore_index=True)

    st.markdown("---")
    st.subheader("📋 Before Cleaning (All Files Merged)")
    st.dataframe(merged_df_raw.head(20), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(merged_df_raw)}")

    st.markdown("---")
    st.subheader("✅ After Cleaning (All Files Merged)")
    st.dataframe(merged_df.head(20), use_container_width=True)
    st.success(
        f"✅ Merged dataset: {len(merged_df)} rows × {len(merged_df.columns)} columns from {len(uploaded_files)} file(s)."
    )

    st.markdown("---")
    st.subheader("💾 Export Cleaned Files")

    # --- Density correction: scale values that were stored without decimal ---
    if "Density" in merged_df.columns:
        def fix_density(v):
            try:
                v = float(v)
            except (ValueError, TypeError):
                return v
            if 100 <= v <= 200:
                return v / 100
            if 10 <= v <= 99:
                return v / 10
            if 2 < v <= 9:
                return v / 10
            return v
        merged_df["Density"] = merged_df["Density"].apply(fix_density)

    # --- Remove trailing .0 from whole numbers across all numeric columns ---
    for col in merged_df.columns:
        if pd.api.types.is_float_dtype(merged_df[col]):
            mask = merged_df[col].notna() & (merged_df[col] == merged_df[col].round(0))
            merged_df.loc[mask, col] = merged_df.loc[mask, col].astype(int)
            # Keep column as object so ints stay without .0
            merged_df[col] = merged_df[col].astype(object)

    # --- Add Matrix column: Expansion == 4 → 0, else → 1 ---
    if "Expansion" in merged_df.columns:
        merged_df["Matrix"] = merged_df["Expansion"].apply(lambda x: 0 if x == 4 else 1)
    else:
        merged_df["Matrix"] = 1

    # --- Column order for exports ---
    txt_columns = [
        "Level", "Expansion", "Grid", "Borehole",
        "Local X (Design)", "Local Y (Design)", "Diameter (Design)",
        "Density", "Hole Length (Design)", "Hole Length (Actual)",
        "Explosive (kg) (Design)", "Explosive (kg) (Actual)",
        "Stemming (Design)", "Stemming (Actual)",
        "Burden (Design)", "Spacing (Design)", "Subdrill (Design)",
        "Water Presence", "Water level", "Asset", "Matrix"
    ]
    txt_cols_present = [c for c in txt_columns if c in merged_df.columns]

    # --- TXT export: no headers, space-separated ---
    txt_df = merged_df[txt_cols_present]
    txt_buffer = io.StringIO()
    txt_df.to_csv(txt_buffer, index=False, header=False, sep=" ")

    # --- Excel export: same order as TXT but with Blast as first column ---
    excel_columns = (["Blast"] if "Blast" in merged_df.columns else []) + txt_cols_present
    excel_df = merged_df[excel_columns]
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        excel_df.to_excel(writer, index=False, sheet_name="QAQC_Cleaned")
    excel_buffer.seek(0)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name="Escondida_QAQC_Cleaned_Merged.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📄 Download TXT File",
            txt_buffer.getvalue(),
            file_name="Escondida_QAQC_Cleaned_Merged.txt",
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload Excel or CSV files to begin.")
