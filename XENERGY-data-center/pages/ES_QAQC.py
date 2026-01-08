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
    s = series.copy()
    # normalize to string then replace, but keep real NaNs
    s = s.replace(["-", " -", "- ", "—", "–"], pd.NA)
    return s


def _to_numeric(series: pd.Series) -> pd.Series:
    """Dash → NA then numeric."""
    return pd.to_numeric(_replace_dash_with_na(series), errors="coerce")


def extract_level_from_blast(text):
    """Level = first 4-digit block in Blast (e.g. 2620_E07_5001 Ene 02 → 2620)."""
    if pd.isna(text):
        return None
    m = re.search(r"(\d{4})", str(text))
    return int(m.group(1)) if m else None


def extract_expansion_from_blast(text):
    """
    Expansion from Blast examples:
      - 3040_N17B_6008_... → 17
      - 2545_PL1_5001 ...  → 1
      - 2995_S04_6001 ...  → 4
      - 3010_L05_6018 ...  → 5
      - 2620_E07_5001 ...  → 7   ✅ NEW
    """
    if pd.isna(text):
        return None
    txt = str(text).upper()
    m = re.search(r"(?:N|PL|L|S|E)(\d{1,2})", txt)  # ✅ added E
    if not m:
        return None
    return int(m.group(1))


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

    # Aux → invalid
    if suffix_low.startswith("aux"):
        return grid, None

    # letter+digits
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
            return grid, None  # a1, e5, etc.

    # digits only
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
    """
    Cross-fill col_a <-> col_b treating empty AND '-' as missing.
    Does NOT drop rows here; drop is done separately where needed.
    """
    if col_a not in df.columns or col_b not in df.columns:
        steps_done.append(f"⚠️ {label}: columns not found ({col_a}, {col_b}).")
        return df

    # treat '-' as NA
    df[col_a] = _replace_dash_with_na(df[col_a])
    df[col_b] = _replace_dash_with_na(df[col_b])

    # cross fill
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

            # reorder columns: Blast → Level → Expansion → Grid → Borehole → rest
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
        # drop if still both missing
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

    # STEP 7 – WaterLevel: convert '-' to 0  ✅ NEW
    # (If you have multiple variants of the name, add them here)
    if "WaterLevel" in df.columns:
        before_dash = (_replace_dash_with_na(df["WaterLevel"]).isna() & df["WaterLevel"].astype(str).str.strip().isin(["-","—","–"])).sum()
        df["WaterLevel"] = _replace_dash_with_na(df["WaterLevel"])
        df["WaterLevel"] = _to_numeric(df["WaterLevel"]).fillna(0)
        steps_done.append("✅ WaterLevel: converted '-' (and non-numeric) to 0.")
    elif "Water Level" in df.columns:
        df["Water Level"] = _replace_dash_with_na(df["Water Level"])
        df["Water Level"] = _to_numeric(df["Water Level"]).fillna(0)
        steps_done.append("✅ Water Level: converted '-' (and non-numeric) to 0.")
    else:
        steps_done.append("ℹ️ WaterLevel column not found (skipped).")

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
    all_dfs = []
    all_steps = {}

    # Process each file
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name.lower()

        if file_name.endswith(".csv"):
            df = read_csv_smart(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.subheader(f"📄 {uploaded_file.name} (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows: {len(df)}")

        df_cleaned, steps = process_file(df)
        all_dfs.append(df_cleaned)
        all_steps[uploaded_file.name] = steps

        with st.expander(f"⚙️ Processing Steps for {uploaded_file.name}", expanded=False):
            for step in steps:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )

    merged_df = pd.concat(all_dfs, ignore_index=True)

    # ==========================================================
    # MERGED RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Merged Data (All Files Combined)")
    st.dataframe(merged_df.head(20), use_container_width=True)
    st.success(
        f"✅ Merged dataset: {len(merged_df)} rows × {len(merged_df.columns)} columns from {len(uploaded_files)} file(s)."
    )

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned Files")

    option = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])
    if option == "⬇️ Download All Columns":
        export_df = merged_df
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(merged_df.columns),
            default=list(merged_df.columns)
        )
        export_df = merged_df[selected_columns] if selected_columns else merged_df

    excel_buffer = io.BytesIO()
    export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    csv_buffer = io.StringIO()
    export_df.to_csv(csv_buffer, index=False)

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
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="Escondida_QAQC_Cleaned_Merged.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload Excel or CSV files to begin.")



