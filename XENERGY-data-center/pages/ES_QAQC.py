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
    """Detect delimiter automatically for CSVs."""
    sample = file_obj.read(8192).decode(errors="replace")
    file_obj.seek(0)
    try:
        # auto-detect separator
        return pd.read_csv(file_obj, sep=None, engine="python")
    except Exception:
        # fallback heuristics
        if sample.count(";") > sample.count(","):
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep=";")
        elif sample.count("\t") > 0:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep="\t")
        elif sample.count("|") > 0:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep="|")
        else:
            file_obj.seek(0)
            return pd.read_csv(file_obj)


def extract_level_from_blast(text):
    """Level = first 4-digit block in Blast (e.g. 2905_PL1S_5001 → 2905)."""
    if pd.isna(text):
        return None
    m = re.search(r"(\d{4})", str(text))
    return int(m.group(1)) if m else None


def extract_expansion_from_blast(text):
    """
    Expansion from Blast:
      - 3040_N17B_6008 → 17
      - 2545_PL1_5001 → 1
      - 2995_S04_6001 → 4
      - 3010_L05_6018 → 5
    """
    if pd.isna(text):
        return None
    txt = str(text).upper()
    m = re.search(r"(?:N|PL|L|S)(\d{1,2})", txt)
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
      - Rows with Aux* or forms like a1 / a2 / a are marked invalid (return None for borehole).
      - Empty borehole returns ("", grid) → will be filled later by counter.
    """
    if pd.isna(raw_val):
        return None, ""

    s = str(raw_val).strip()
    if s == "":
        return None, ""  # will be filled later

    # remove spaces globally
    s = re.sub(r"\s+", "", s)

    # split by underscore: LEVEL_SUFFIX (e.g. 5001_B267, 5001_255)
    if "_" in s:
        left, right = s.split("_", 1)
        grid = int(left) if left.isdigit() else None
        suffix = right
    else:
        # no underscore: might be just hole ID, grid unknown
        grid = None
        suffix = s

    suffix_low = suffix.lower()

    # Aux → invalid
    if suffix_low.startswith("aux"):
        return grid, None

    # if exactly pattern letter+digits
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
            # examples: a1, e5 → invalid
            return grid, None

    # if only digits → normal numeric borehole
    if suffix_low.isdigit():
        return grid, int(suffix_low)

    # any other strange combination → invalid
    return grid, None


def fill_boreholes_by_blast(df):
    """
    For each Blast, fill empty Borehole ('') with sequential IDs starting at 10000.
    Rows with Borehole = None (invalid/aux/a1 etc.) should already be dropped before.
    """
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


# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    # --- READ FILE (Excel or CSV) with smart delimiter detection ---
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    steps_done = []

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):

        # STEP 1 – Clean invalid Density values (empty, letters, symbols, negatives, zero)
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

        # STEP 2 – Remove negative coordinates (Local X/Y Design)
        if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
            before = len(df)
            df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with negative local coordinates.")
        else:
            steps_done.append("❌ Missing columns 'Local X (Design)' or 'Local Y (Design)'.")

        # STEP 3 – Level & Expansion from Blast, Grid & Borehole from Borehole
        if "Blast" in df.columns:
            # Level & Expansion from Blast
            df["Level"] = df["Blast"].apply(extract_level_from_blast)
            df["Expansion"] = df["Blast"].apply(extract_expansion_from_blast)

            # Grid & Borehole from Borehole (if column exists)
            if "Borehole" in df.columns:
                grids = []
                bores = []
                for v in df["Borehole"]:
                    grid, bore = parse_borehole_and_grid(v)
                    grids.append(grid)
                    bores.append(bore if bore is not None else None if v is not None else "")
                df["Grid"] = grids
                df["Borehole"] = bores

                # Drop rows where Borehole is None (Aux or invalid like a1, a2, a...)
                before_invalid = len(df)
                df = df[df["Borehole"].notna()]  # keep numeric or "" (to fill)
                deleted_invalid = before_invalid - len(df)

                # Fill Borehole "" per Blast with counters
                df["Borehole"] = df["Borehole"].apply(lambda x: "" if x is None else x)
                df = fill_boreholes_by_blast(df)

                steps_done.append(
                    f"✅ Parsed Level & Expansion from Blast, Grid & Borehole from Borehole "
                    f"({deleted_invalid} invalid/aux/aX rows removed)."
                )

                # Reorder: Blast → Level → Expansion → Grid → Borehole → rest
                cols = list(df.columns)
                for c in ["Level", "Expansion", "Grid", "Borehole"]:
                    if c in cols:
                        cols.remove(c)
                if "Blast" in cols:
                    idx = cols.index("Blast")
                    insert = ["Level", "Expansion", "Grid", "Borehole"]
                    cols[idx + 1:idx + 1] = [c for c in insert if c not in cols]
                    df = df[cols]
            else:
                steps_done.append("⚠️ Column 'Borehole' not found. Only Level/Expansion from Blast were created.")
        else:
            steps_done.append("❌ Column 'Blast' not found in file. Level/Expansion/Grid were not created.")

        # STEP 4 – Hole Length cross-fill
        if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
            before = len(df)
            df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
            df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all", inplace=True)
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Hole Length data (removed {deleted} rows with both lengths empty).")
        else:
            steps_done.append("⚠️ Hole Length columns not found.")

        # STEP 5 – Explosive cross-fill
        if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
            before = len(df)
            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
            df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all", inplace=True)
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Explosive data (removed {deleted} rows with both values empty).")
        else:
            steps_done.append("⚠️ Explosive columns not found.")

        # STEP 6 – Clean Asset column (keep only numeric part)
        asset_col = next((c for c in df.columns if "Asset" in c), None)
        if asset_col:
            before_non_numeric = df[asset_col].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            steps_done.append(
                f"✅ Cleaned '{asset_col}' column (removed letters; {before_non_numeric} entries contained text)."
            )
        else:
            steps_done.append("⚠️ 'Asset' column not found.")

        # --- Display Steps in Green Cards ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

    # ==========================================================
    # AFTER CLEANING — RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    option = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])
    if option == "⬇️ Download All Columns":
        export_df = df
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(df.columns),
            default=list(df.columns)
        )
        export_df = df[selected_columns] if selected_columns else df

    # Prepare Excel + CSV
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
            file_name="Escondida_QAQC_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="Escondida_QAQC_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")
