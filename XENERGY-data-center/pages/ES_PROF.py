import streamlit as st
import pandas as pd
import io
import re

# ==========================================================
# SMALL HELPERS
# ==========================================================
def normalize_name(name: str) -> str:
    return re.sub(r"[\s_]+", "", str(name)).strip().upper()

def find_column(df, candidates):
    norm_candidates = {normalize_name(c) for c in candidates}
    for col in df.columns:
        if normalize_name(col) in norm_candidates:
            return col
    # Fallback: partial match
    for col in df.columns:
        for cand in candidates:
            if cand.lower() in col.lower():
                return col
    return None

def read_csv_smart(file_obj):
    sample = file_obj.read(8192).decode(errors="replace")
    file_obj.seek(0)
    try:
        return pd.read_csv(file_obj, sep=None, engine="python")
    except Exception:
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

def read_file_smart(file_obj):
    name = file_obj.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_obj)
    else:
        return read_csv_smart(file_obj)

# ==========================================================
# DRILL RIG MAPPINGS
# ==========================================================
DRILL_RIG_MAP = {
    "6 1/2":  {"Diammeter": 165,  "Stemming": 8.0},
    "10 5/8": {"Diammeter": 270,  "Stemming": 5.0},
    "12 1/4": {"Diammeter": 311,  "Stemming": 5.5},
}

def map_drill_rig(val):
    """Return (Diammeter, Stemming) based on Drill Rig value."""
    s = str(val).strip()
    for key, mapping in DRILL_RIG_MAP.items():
        if key in s:
            return mapping["Diammeter"], mapping["Stemming"]
    return None, None

# ==========================================================
# NÐ POZO TRANSFORMATION
# ==========================================================
def transform_pozo(val):
    """
    P120 → 10000120, B75 → 1000075, C75 → 2000075, D18 → 18.
    P/B prefix → 10000 + number, C prefix → 20000 + number, D → just number.
    Pure numeric → keep as-is.
    """
    s = str(val).strip().upper()
    if not s or s.lower() == "nan":
        return None

    # Already pure numeric
    if re.match(r"^\d+$", s):
        return int(s)

    m = re.match(r"^([A-Z])(\d+)$", s)
    if m:
        prefix = m.group(1)
        num = int(m.group(2))
        if prefix in ("P", "B"):
            return 10000000 + num
        elif prefix == "C":
            return 20000000 + num
        elif prefix == "D":
            return num
        else:
            return num
    return None

# ==========================================================
# CORE PROCESSING FUNCTION
# ==========================================================
def process_file(df):
    """Clean one dataframe and return (cleaned_df, steps, error_msg)."""
    steps = []
    original_rows = len(df)

    # --- Detect columns ---
    col_pozo       = find_column(df, ["NÐ POZO", "Nº POZO", "NO POZO", "N POZO", "NPOZO", "ND POZO"])
    col_este       = find_column(df, ["COORDENADA ESTE", "COORD ESTE", "ESTE"])
    col_norte      = find_column(df, ["COORDENADA NORTE", "COORD NORTE", "NORTE"])
    col_collar_z   = find_column(df, ["Collar Z", "COLLARZ", "COLLAR_Z"])
    col_length     = find_column(df, ["Length", "LENGTH"])
    col_blast      = find_column(df, ["Blast Name", "BLASTNAME", "BLAST_NAME"])
    col_subdrill   = find_column(df, ["Subdrill Length", "SUBDRILLLENGTH", "SUBDRILL_LENGTH"])
    col_burden     = find_column(df, ["Burden", "BURDEN"])
    col_spacing    = find_column(df, ["Spacing", "SPACING"])
    col_drill_rig  = find_column(df, ["Drill Rig", "DRILLRIG", "DRILL_RIG"])

    # Check required columns
    missing = []
    for name, col in [("NÐ POZO", col_pozo), ("COORDENADA ESTE", col_este),
                       ("COORDENADA NORTE", col_norte), ("Collar Z", col_collar_z),
                       ("Length", col_length), ("Blast Name", col_blast),
                       ("Drill Rig", col_drill_rig)]:
        if col is None:
            missing.append(name)
    if missing:
        return None, steps, f"Missing required columns: {', '.join(missing)}"

    # STEP 1 — NÐ POZO: transform prefix codes
    df["NÐ POZO"] = df[col_pozo].apply(transform_pozo)
    before = len(df)
    df = df[df["NÐ POZO"].notna()]
    deleted = before - len(df)
    df["NÐ POZO"] = df["NÐ POZO"].astype(int)
    steps.append(f"✅ NÐ POZO: transformed (P→10000000+n, B→10000000+n, C→20000000+n, D→n). Invalid rows removed: {deleted}")

    # STEP 2 — Drill Rig → Diammeter & Stemming
    rig_results = df[col_drill_rig].apply(lambda x: pd.Series(map_drill_rig(x), index=["Diammeter", "Stemming"]))
    df["Diammeter"] = rig_results["Diammeter"]
    df["Stemming"] = rig_results["Stemming"]
    unmapped = int(df["Diammeter"].isna().sum())
    before = len(df)
    df = df[df["Diammeter"].notna()]
    deleted = before - len(df)
    df["Diammeter"] = df["Diammeter"].astype(int)
    steps.append(f"✅ Drill Rig → Diammeter & Stemming. Rows with unknown Drill Rig removed: {deleted}")

    # STEP 3 — Numeric columns: convert and remove text rows
    numeric_cols_map = {
        "COORDENADA ESTE": col_este,
        "COORDENADA NORTE": col_norte,
        "Collar Z": col_collar_z,
        "Length": col_length,
        "Subdrill Length": col_subdrill,
        "Burden": col_burden,
        "Spacing": col_spacing,
    }

    for out_name, src_col in numeric_cols_map.items():
        if src_col is not None:
            df[out_name] = pd.to_numeric(df[src_col], errors="coerce")
        else:
            df[out_name] = 0
            steps.append(f"ℹ️ {out_name} not found → filled with 0.")

    # Remove rows where core numeric cols have text (non-numeric)
    core_numeric = ["COORDENADA ESTE", "COORDENADA NORTE", "Collar Z", "Length"]
    before = len(df)
    df = df.dropna(subset=core_numeric)
    deleted = before - len(df)
    if deleted > 0:
        steps.append(f"🗑️ Removed {deleted} rows with text/invalid values in numeric columns.")

    # STEP 4 — Blast Name: keep as-is
    df["Blast Name"] = df[col_blast].astype(str).str.strip()
    steps.append("✅ Blast Name: kept as-is.")

    # Fill NaN in optional numeric columns with 0
    for col_name in ["Subdrill Length", "Burden", "Spacing"]:
        n_empty = int(df[col_name].isna().sum())
        if n_empty > 0:
            df[col_name] = df[col_name].fillna(0)
            steps.append(f"ℹ️ {col_name}: filled {n_empty} empty values with 0.")

    # Summary
    total_deleted = original_rows - len(df)
    steps.append(f"📉 Total rows deleted: {total_deleted} | Remaining: {len(df)}")

    # Select & order output columns
    output_cols = ["Blast Name", "NÐ POZO", "COORDENADA ESTE", "COORDENADA NORTE",
                   "Collar Z", "Length", "Subdrill Length", "Burden", "Spacing",
                   "Diammeter", "Stemming"]
    df = df[[c for c in output_cols if c in df.columns]].copy()

    # Round floats to 2 decimals
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].round(2)

    return df, steps, None


# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Drill Profile (ES_PROF)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Cleaning and structuring drill profile data. Supports multiple files.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_esprof"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload your drill profile file(s)",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True,
)

if uploaded_files:

    all_cleaned = []
    total_original = 0

    for idx, uploaded_file in enumerate(uploaded_files):
        file_label = uploaded_file.name
        st.markdown(f"### 📁 File {idx + 1}: `{file_label}`")

        df_raw = read_file_smart(uploaded_file)
        total_original += len(df_raw)

        st.dataframe(df_raw.head(10), use_container_width=True)
        st.info(f"📏 Rows in this file: {len(df_raw)}")

        cleaned, steps, error = process_file(df_raw)

        with st.expander(f"⚙️ Processing Steps — {file_label}", expanded=False):
            for step in steps:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:8px 10px;border-radius:8px;margin-bottom:6px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True,
                )

        if error:
            st.error(f"❌ {file_label}: {error}")
        elif cleaned is not None and len(cleaned) > 0:
            st.success(f"✅ {file_label}: {len(cleaned)} rows after cleaning.")
            all_cleaned.append(cleaned)
        else:
            st.warning(f"⚠️ {file_label}: 0 rows after cleaning.")

        st.markdown("---")

    # ==========================================================
    # MERGE ALL FILES
    # ==========================================================
    if all_cleaned:
        export_df = pd.concat(all_cleaned, ignore_index=True)

        st.subheader("✅ Merged Cleaned Data Preview")
        st.dataframe(export_df.head(20), use_container_width=True)
        st.success(
            f"✅ Final merged dataset: **{len(export_df)}** rows × **{len(export_df.columns)}** columns "
            f"(from {len(all_cleaned)} file(s), {total_original} original rows total)."
        )

        # ==========================================================
        # DATA QUALITY CHECK
        # ==========================================================
        st.markdown("---")
        st.subheader("🔍 Data Quality Check")

        if st.button("▶️ Run Quality Check", use_container_width=True, key="prof_qc"):
            total_rows = len(export_df)

            if total_rows == 0:
                st.error("❌ No data to check — the dataset is empty after cleaning.")
            else:
                issues_found = False
                report_lines = []

                for col in export_df.columns:
                    col_issues = []

                    empty_count = int(export_df[col].isna().sum() + (export_df[col].astype(str).str.strip() == "").sum())
                    if empty_count > 0:
                        col_issues.append(f"**{empty_count}** empty value(s)")

                    non_empty = export_df[col].dropna().astype(str).str.strip()
                    non_empty = non_empty[non_empty != ""]

                    if len(non_empty) > 0:
                        text_mask = non_empty.apply(lambda x: bool(re.search(r"[A-Za-z]", str(x))))
                        text_count = int(text_mask.sum())
                    else:
                        text_count = 0
                    if text_count > 0:
                        col_issues.append(f"**{text_count}** cell(s) contain text/letters")

                    if len(non_empty) > 0:
                        special_mask = non_empty.apply(lambda x: bool(re.search(r"[^0-9eE.\-+\s]", str(x))))
                        special_count = int(special_mask.sum())
                    else:
                        special_count = 0
                    if special_count > 0:
                        examples = non_empty[special_mask].head(3).tolist()
                        col_issues.append(f"**{special_count}** cell(s) with special characters (e.g. {examples})")

                    if col_issues:
                        issues_found = True
                        report_lines.append(f"⚠️ **{col}**: " + " | ".join(col_issues))
                    else:
                        report_lines.append(f"✅ **{col}**: OK ({total_rows} values, all numeric)")

                if not issues_found:
                    st.success("✅ All columns are clean — no empty values, no text, no special characters. Ready to download!")
                else:
                    st.warning("⚠️ Some columns have issues. Review the report below:")

                for line in report_lines:
                    st.markdown(line)

        # ==========================================================
        # DOWNLOAD SECTION
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Cleaned File")

        # Excel (with headers)
        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        # TXT (space-separated, no headers)
        txt_buffer = io.StringIO()
        export_df.to_csv(txt_buffer, index=False, header=False, sep=" ")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel",
                excel_buffer,
                file_name="ES_PROF_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "📄 Download TXT (no headers)",
                txt_buffer.getvalue(),
                file_name="ES_PROF_Cleaned.txt",
                mime="text/plain",
                use_container_width=True,
            )
    else:
        st.error("❌ No valid data produced from any uploaded file.")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload one or more Excel/CSV/TXT files to begin.")
