import streamlit as st
import pandas as pd
import re
import io
from datetime import datetime

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and preparation of QAQC drilling data "
    "(YAML pipeline: validations → filters → transformations).</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# CONFIG (mirrors the YAML)
# ==========================================================
CONFIG_VERSION = "1.0"
DATA_SOURCE = "QAQC"
CLIENT = "TESTCLIENT"
SITE = "TESTSITE"

REQUIRED_COLUMNS = [
    "Blast", "Borehole", "Local X (Design)", "Local Y (Design)",
    "Diameter (Design)", "Density",
    "Hole Length (Design)", "Hole Length (Actual)",
    "Explosive (kg) (Design)", "Explosive (kg) (Actual)",
    "Stemming (Design)", "Stemming (Actual)",
    "Burden (Design)", "Spacing (Design)", "Subdrill (Design)",
    "Water Presence", "Asset",
]
OPTIONAL_COLUMNS = ["Water level"]

RENAME_MAP = {
    "Blast": "BlastProtocol",
    "Local X (Design)": "LocalXDesign",
    "Local Y (Design)": "LocalYDesign",
    "Diameter (Design)": "DiameterDesign",
    "Hole Length (Design)": "HoleLengthDesign",
    "Hole Length (Actual)": "HoleLengthActual",
    "Explosive (kg) (Design)": "ExplosiveKgDesign",
    "Explosive (kg) (Actual)": "ExplosiveKgActual",
    "Stemming (Design)": "StemmingDesign",
    "Stemming (Actual)": "StemmingActual",
    "Burden (Design)": "BurdenDesign",
    "Spacing (Design)": "SpacingDesign",
    "Subdrill (Design)": "SubdrillDesign",
    "Water Presence": "WaterPresence",
    "Water level": "WaterLevel",
    "Asset": "Asset",
}

PREFIX_MAPPINGS = {"B": "100000", "C": "200000", "D": ""}

FINAL_FIELDS = [
    "BlastProtocol", "BenchLevel", "Expansion", "DrillPattern", "BoreholeCode",
    "LocalXDesign", "LocalYDesign", "DiameterDesign", "Density",
    "HoleLengthDesign", "HoleLengthActual",
    "ExplosiveKgDesign", "ExplosiveKgActual",
    "StemmingDesign", "StemmingActual",
    "BurdenDesign", "SpacingDesign", "SubdrillDesign",
    "WaterPresence", "WaterLevel", "Asset",
    "ProcessedDate", "ConfigVersion", "DataSource", "Client", "Site",
]

# Precision for the TSV output (per YAML "tsv_with_precision")
TSV_PRECISION = {
    "LocalXDesign": 2, "LocalYDesign": 2, "Density": 2,
    "HoleLengthDesign": 2, "HoleLengthActual": 2,
    "ExplosiveKgDesign": 2, "ExplosiveKgActual": 2,
    "StemmingDesign": 2, "StemmingActual": 2,
}

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


# ----------------------------------------------------------
# PHASE 1: STRUCTURE VALIDATIONS
# ----------------------------------------------------------
def validate_structure(df, steps_done):
    """Schema + range validations from YAML structure_validations."""
    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        steps_done.append(f"❌ VALIDATE_FILE_SCHEMA: missing required columns → {missing_required}")
    else:
        steps_done.append("✅ VALIDATE_FILE_SCHEMA: all required columns present.")

    missing_optional = [c for c in OPTIONAL_COLUMNS if c not in df.columns]
    if missing_optional:
        steps_done.append(f"ℹ️ Optional columns missing → {missing_optional}")

    # Burden (Design) must be > 4.0  (error, fail_fast: false)
    if "Burden (Design)" in df.columns:
        b = pd.to_numeric(df["Burden (Design)"], errors="coerce")
        bad = int((b <= 4.0).sum())
        if bad:
            steps_done.append(f"⚠️ VALIDATE_RANGE Burden (Design) > 4.0: {bad} rows out of range.")
        else:
            steps_done.append("✅ VALIDATE_RANGE Burden (Design) > 4.0 OK.")

    # Spacing (Design) must be > 4.0
    if "Spacing (Design)" in df.columns:
        s = pd.to_numeric(df["Spacing (Design)"], errors="coerce")
        bad = int((s <= 4.0).sum())
        if bad:
            steps_done.append(f"⚠️ VALIDATE_RANGE Spacing (Design) > 4.0: {bad} rows out of range.")
        else:
            steps_done.append("✅ VALIDATE_RANGE Spacing (Design) > 4.0 OK.")

    # Local X / Y (Design) >= 10000  (warning)
    for col in ("Local X (Design)", "Local Y (Design)"):
        if col in df.columns:
            v = pd.to_numeric(df[col], errors="coerce")
            bad = int((v < 10000).sum())
            if bad:
                steps_done.append(f"⚠️ VALIDATE_RANGE {col} ≥ 10000: {bad} rows below threshold (warning).")

    return df


# ----------------------------------------------------------
# PHASE 2: FILTERS
# ----------------------------------------------------------
def apply_filters(df, steps_done):
    """Filter rows according to YAML filters block."""
    # 2.1 — Density must be numeric (drop rows where it isn't)
    if "Density" in df.columns:
        before = len(df)
        density_num = pd.to_numeric(df["Density"], errors="coerce")
        df = df[density_num.notna()].copy()
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        steps_done.append(f"✅ FILTER Density is_numeric: removed {before - len(df)} non-numeric rows.")
    else:
        steps_done.append("⚠️ FILTER Density skipped (column not found).")

    # 2.2 — Borehole must NOT contain 'aux' (case insensitive)
    if "Borehole" in df.columns:
        before = len(df)
        mask = ~df["Borehole"].astype(str).str.contains("aux", case=False, na=False)
        df = df[mask].copy()
        steps_done.append(f"✅ FILTER Borehole not_contains 'aux': removed {before - len(df)} rows.")
    else:
        steps_done.append("⚠️ FILTER Borehole skipped (column not found).")

    return df


# ----------------------------------------------------------
# PHASE 3: TRANSFORMATIONS
# ----------------------------------------------------------
def split_columns(df, source, separator, target_columns, max_split, fill_missing=""):
    """Mirror YAML SPLIT_COLUMNS: split with n=max_split, assign first len(targets) parts."""
    if source not in df.columns:
        return df
    series = df[source].astype(str)
    parts = series.str.split(separator, n=max_split, expand=True)
    for i, col in enumerate(target_columns):
        if i < parts.shape[1]:
            df[col] = parts[i].fillna(fill_missing).replace({"nan": fill_missing})
        else:
            df[col] = fill_missing
    return df


def regex_substitute(df, column, pattern, replacement, target_column=None):
    """Mirror YAML SUBSTITUTE_VALUES with regex_patterns and create_new_column."""
    if column not in df.columns:
        return df
    target = target_column or column
    df[target] = df[column].astype(str).apply(
        lambda x: re.sub(pattern, replacement, x) if pd.notna(x) else x
    )
    return df


def transform_hole_prefixes(df, source_column, target_column, prefix_mappings):
    """
    Mirror YAML TRANSFORM_HOLE_PREFIXES:
      'B125' -> '100000125'   (prefix B replaced with '100000')
      'C045' -> '200000045'   (prefix C replaced with '200000')
      'D016' -> '016'         (prefix D replaced with '')
      pure digits stay unchanged
    """
    if source_column not in df.columns:
        return df

    def _map(val):
        if pd.isna(val):
            return val
        s = str(val).strip()
        if s == "":
            return s
        m = re.match(r"^([A-Za-z])(\d+)$", s)
        if m:
            letter, digits = m.group(1).upper(), m.group(2)
            if letter in prefix_mappings:
                return prefix_mappings[letter] + digits
            return s
        if s.isdigit():
            return s
        return s

    df[target_column] = df[source_column].apply(_map)
    return df


def fallback_numeric(df, source_column, fallback_column, overwrite=True):
    """Mirror YAML FALLBACK_NUMERIC: use fallback if source is not numeric."""
    if source_column not in df.columns or fallback_column not in df.columns:
        return df
    src = pd.to_numeric(df[source_column], errors="coerce")
    fb = pd.to_numeric(df[fallback_column], errors="coerce")
    cleaned = src.where(src.notna(), fb)
    if overwrite:
        df[source_column] = cleaned
    else:
        df[source_column + "_clean"] = cleaned
    return df


def add_metadata(df):
    """Mirror YAML ADD_CALCULATED_COLUMNS."""
    df["ProcessedDate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["ConfigVersion"] = CONFIG_VERSION
    df["DataSource"] = DATA_SOURCE
    df["Client"] = CLIENT
    df["Site"] = SITE
    return df


def apply_transformations(df, steps_done):
    """Run the full YAML transformations pipeline in order."""
    # T1 — Split Blast → BenchLevel, Expansion (max_split=2 means n=2 splits → 3 parts; pick first 2)
    if "Blast" in df.columns:
        df = split_columns(df, "Blast", "_", ["BenchLevel", "Expansion"], max_split=2)
        steps_done.append("✅ SPLIT Blast → BenchLevel, Expansion.")

    # T1.1 — Extract numeric block of 2 digits after a letter from Expansion
    if "Expansion" in df.columns:
        df = regex_substitute(df, "Expansion", r"[A-Za-z](\d{2})", r"\1", "Expansion")
        steps_done.append("✅ SUBSTITUTE Expansion: regex [A-Za-z](\\d{2}) → \\1.")

    # T2 — Split Borehole → DrillPattern, BoreholeName
    if "Borehole" in df.columns:
        df = split_columns(df, "Borehole", "_", ["DrillPattern", "BoreholeName"], max_split=1)
        steps_done.append("✅ SPLIT Borehole → DrillPattern, BoreholeName.")

    # T3 — BoreholeName → BoreholeCode using prefix mappings
    if "BoreholeName" in df.columns:
        df = transform_hole_prefixes(df, "BoreholeName", "BoreholeCode", PREFIX_MAPPINGS)
        steps_done.append("✅ TRANSFORM_HOLE_PREFIXES BoreholeName → BoreholeCode (B=100000, C=200000, D=∅).")

    # T4 — Rename columns to standardized names
    rename_now = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_now)
    steps_done.append(f"✅ RENAME_COLUMNS: {len(rename_now)} columns renamed.")

    # T5 — Fallback numeric: HoleLengthActual ← HoleLengthDesign
    df = fallback_numeric(df, "HoleLengthActual", "HoleLengthDesign", overwrite=True)
    steps_done.append("✅ FALLBACK_NUMERIC HoleLengthActual ← HoleLengthDesign.")

    # T6 — Substitute Asset: digits after letter
    if "Asset" in df.columns:
        df = regex_substitute(df, "Asset", r"[A-Za-z](\d+)", r"\1", "Asset")
        steps_done.append("✅ SUBSTITUTE Asset: regex [A-Za-z](\\d+) → \\1.")

    # T7 — Fallback numeric: ExplosiveKgActual
    df = fallback_numeric(df, "ExplosiveKgActual", "ExplosiveKgDesign", overwrite=True)
    steps_done.append("✅ FALLBACK_NUMERIC ExplosiveKgActual ← ExplosiveKgDesign.")

    # T8 — Fallback numeric: StemmingActual
    df = fallback_numeric(df, "StemmingActual", "StemmingDesign", overwrite=True)
    steps_done.append("✅ FALLBACK_NUMERIC StemmingActual ← StemmingDesign.")

    # T9 — Add metadata columns
    df = add_metadata(df)
    steps_done.append("✅ ADD_CALCULATED_COLUMNS: ProcessedDate, ConfigVersion, DataSource, Client, Site.")

    return df


def reorder_final_columns(df):
    """Put the YAML-defined fields first; keep any extras at the end."""
    present = [c for c in FINAL_FIELDS if c in df.columns]
    extras = [c for c in df.columns if c not in present]
    return df[present + extras]


def process_file(df):
    """Apply the full QAQC pipeline (validate → filter → transform)."""
    steps_done = []
    df = validate_structure(df, steps_done)
    df = apply_filters(df, steps_done)
    df = apply_transformations(df, steps_done)
    df = reorder_final_columns(df)
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

    # ----- Pipeline log -----
    with st.expander("🔎 Pipeline log (per file)"):
        for fname, steps in all_steps.items():
            st.markdown(f"**{fname}**")
            for s in steps:
                st.write(s)

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

    # Excel (all columns of selection)
    excel_buffer = io.BytesIO()
    export_df.to_excel(excel_buffer, index=False, engine="openpyxl", sheet_name="qaqc_data")
    excel_buffer.seek(0)

    # TXT (TSV) with precision per YAML "tsv_with_precision" (no header, tab separator)
    tsv_df = export_df.copy()
    for col, prec in TSV_PRECISION.items():
        if col in tsv_df.columns:
            tsv_df[col] = pd.to_numeric(tsv_df[col], errors="coerce").round(prec)
    txt_buffer = io.StringIO()
    tsv_df.to_csv(txt_buffer, index=False, header=False, sep="\t")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_name = f"MEL_CLEAN_{DATA_SOURCE}_{CLIENT}_{SITE}_{timestamp}.xlsx"
    txt_name = f"MEL_{DATA_SOURCE}_PRECISION_{timestamp}.txt"

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name=excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📄 Download TXT File",
            txt_buffer.getvalue(),
            file_name=txt_name,
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload Excel or CSV files to begin.")
