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
    return None

def read_file_smart(file_obj, file_name):
    """Read CSV/TXT/Excel with auto-detection."""
    import csv
    name = file_name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_obj)

    sample_bytes = file_obj.read(8192)
    file_obj.seek(0)
    encodings = ("utf-8", "cp1252", "latin1", "iso-8859-1")
    delimiters = [",", ";", "\t", "|"]

    for enc in encodings:
        try:
            text = sample_bytes.decode(enc, errors="replace")
        except Exception:
            continue
        sep = None
        try:
            dialect = csv.Sniffer().sniff(text, delimiters="".join(delimiters))
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

def pct_to_number(val):
    """Convert '40.5%' → 40.5, '11.4%' → 11.4. Leave numeric as-is."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s == "-":
        return None
    s = s.replace(",", ".")
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Drone Fragmentation (ES_DRONE)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Cleaning and structuring drone fragmentation data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_esdrone"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD (MULTIPLE FILES)
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload your drone fragmentation file(s)",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True
)

if uploaded_files:

    all_dfs_raw = []
    for uploaded_file in uploaded_files:
        df_raw = read_file_smart(uploaded_file, uploaded_file.name)
        all_dfs_raw.append(df_raw)

    merged_raw = pd.concat(all_dfs_raw, ignore_index=True)
    df = merged_raw.copy()

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}  ({len(uploaded_files)} file(s) merged)")

    original_rows = len(df)
    steps_done = []

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # --- Detect columns ---
        col_fecha = find_column(df, ["FECHA"])
        col_pala = find_column(df, ["PALA"])
        col_p80 = find_column(df, ["P80"])
        col_p50 = find_column(df, ["P50"])
        col_p20 = find_column(df, ["P20"])
        col_grueso = find_column(df, ["Material Grueso (>4\")", "MaterialGrueso(>4\")", "MATERIALGRUESO(>4\")"])
        col_intermedio = find_column(df, ["Material Intermedio (2-4\")", "MaterialIntermedio(2-4\")", "MATERIALINTERMEDIO(2-4\")"])
        col_finos = find_column(df, ["Finos generados (<2\")", "FinosGenerados(<2\")", "FINOSGENERADOS(<2\")"])

        # Fallback: partial match for Grueso/Intermedio/Finos
        if col_grueso is None:
            for c in df.columns:
                if "grueso" in c.lower() or ">4" in c:
                    col_grueso = c
                    break
        if col_intermedio is None:
            for c in df.columns:
                if "intermedio" in c.lower() or "2-4" in c.lower():
                    col_intermedio = c
                    break
        if col_finos is None:
            for c in df.columns:
                if "fino" in c.lower() or "<2" in c.lower():
                    col_finos = c
                    break

        # STEP 1 – FECHA → Day, Month, Year
        if col_fecha is not None:
            df[col_fecha] = pd.to_datetime(df[col_fecha], dayfirst=True, errors="coerce")
            before = len(df)
            df = df[df[col_fecha].notna()]
            deleted = before - len(df)
            df["Day"] = df[col_fecha].dt.day.astype(int)
            df["Month"] = df[col_fecha].dt.month.astype(int)
            df["Year"] = df[col_fecha].dt.year.astype(int)
            steps_done.append(f"✅ FECHA: split into Day/Month/Year. Invalid rows removed: {deleted}")
        else:
            steps_done.append("⚠️ Column 'Fecha' not found — Day/Month/Year not created.")

        # STEP 2 – PALA: extract numeric (SHE0073 → 73)
        if col_pala is not None:
            df["Pala"] = df[col_pala].astype(str).str.extract(r"(\d+)", expand=False)
            df["Pala"] = pd.to_numeric(df["Pala"], errors="coerce")
            steps_done.append(f"✅ PALA (from '{col_pala}'): extracted numeric (SHE0073 → 73).")
        else:
            steps_done.append("⚠️ Column 'PALA' not found.")

        # STEP 3 – P80, P50, P20: convert to numeric
        for label, col_ref in [("P80", col_p80), ("P50", col_p50), ("P20", col_p20)]:
            if col_ref is not None:
                df[label] = df[col_ref].apply(pct_to_number)
                steps_done.append(f"✅ {label} (from '{col_ref}'): converted to numeric.")
            else:
                steps_done.append(f"⚠️ Column '{label}' not found.")

        # STEP 3a – Clean P80: empty → P50*2, else P20*4, else 0
        if "P80" in df.columns:
            p80_bad = df["P80"].isna() | (df["P80"] == 0)
            p80_fixed = 0

            # First try: P80 = P50 * 2
            if "P50" in df.columns:
                fix1 = p80_bad & df["P50"].notna() & (df["P50"] > 0)
                df.loc[fix1, "P80"] = (df.loc[fix1, "P50"] * 2).round(2)
                p80_fixed += int(fix1.sum())
                p80_bad = df["P80"].isna() | (df["P80"] == 0)

            # Second try: P80 = P20 * 4
            if "P20" in df.columns:
                fix2 = p80_bad & df["P20"].notna() & (df["P20"] > 0)
                df.loc[fix2, "P80"] = (df.loc[fix2, "P20"] * 4).round(2)
                p80_fixed += int(fix2.sum())
                p80_bad = df["P80"].isna() | (df["P80"] == 0)

            # Remaining: fill with 0
            still_empty = int(p80_bad.sum())
            df["P80"] = df["P80"].fillna(0)
            steps_done.append(
                f"✅ P80: refilled {p80_fixed} empty values (P50×2 then P20×4). "
                f"{still_empty} remaining set to 0."
            )

        # STEP 3b – Clean P50: invalid/text/>50/0/empty → P80/2; if both bad → delete row
        if "P50" in df.columns:
            p50_bad = df["P50"].isna() | (df["P50"] == 0) | (df["P50"] > 50)
            p50_fixed = 0
            if "P80" in df.columns:
                # Refill bad P50 with P80 / 2
                can_fix = p50_bad & df["P80"].notna() & (df["P80"] > 0)
                df.loc[can_fix, "P50"] = (df.loc[can_fix, "P80"] / 2).round(2)
                p50_fixed = int(can_fix.sum())

                # Delete rows where both P50 and P80 are still bad
                still_bad = df["P50"].isna() | (df["P50"] == 0)
                p80_bad = df["P80"].isna() | (df["P80"] == 0)
                before = len(df)
                df = df[~(still_bad & p80_bad)]
                deleted_both = before - len(df)
                steps_done.append(
                    f"✅ P50: refilled {p50_fixed} invalid values with P80/2. "
                    f"Deleted {deleted_both} rows where both P50 and P80 were empty/invalid."
                )
            else:
                before = len(df)
                df = df[~p50_bad]
                deleted_both = before - len(df)
                steps_done.append(f"✅ P50: removed {deleted_both} invalid rows (P80 not available for fallback).")

        # STEP 3c – Clean P20: invalid/text/0/empty → P50/2
        if "P20" in df.columns and "P50" in df.columns:
            p20_bad = df["P20"].isna() | (df["P20"] == 0)
            can_fix = p20_bad & df["P50"].notna() & (df["P50"] > 0)
            df.loc[can_fix, "P20"] = (df.loc[can_fix, "P50"] / 2).round(2)
            p20_fixed = int(can_fix.sum())
            steps_done.append(f"✅ P20: refilled {p20_fixed} invalid values with P50/2.")

        # STEP 4 – Material Grueso, Intermedio, Finos: percentage → number
        for label, col_ref, out_name in [
            ("Material Grueso (>4\")", col_grueso, "Grueso"),
            ("Material Intermedio (2-4\")", col_intermedio, "Intermedio"),
            ("Finos generados (<2\")", col_finos, "Finos"),
        ]:
            if col_ref is not None:
                df[out_name] = df[col_ref].apply(pct_to_number)
                steps_done.append(f"✅ {label} (from '{col_ref}'): percentage → number (40% → 40).")
            else:
                steps_done.append(f"⚠️ Column '{label}' not found.")

        # STEP 5 – Delete rows where all key values are empty
        key_cols = [c for c in ["Pala", "P80", "P50", "P20", "Grueso", "Intermedio", "Finos"] if c in df.columns]
        if key_cols:
            before = len(df)
            df.dropna(subset=key_cols, how="all", inplace=True)
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows where all key columns were empty.")

        # --- Show steps ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:8px 10px;border-radius:8px;margin-bottom:6px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

        final_rows = len(df)
        total_deleted = original_rows - final_rows
        st.markdown(
            f"<div style='background-color:#fff3cd;padding:10px;border-radius:8px;margin-top:10px;'>"
            f"<b>🧮 Summary:</b> Started with <b>{original_rows}</b> rows, "
            f"finished with <b>{final_rows}</b> rows. "
            f"<b>{total_deleted}</b> rows deleted in total.</div>",
            unsafe_allow_html=True
        )

    # ==========================================================
    # OUTPUT
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Cleaned Data Preview")

    output_cols = ["Pala", "Day", "Month", "Year", "P80", "P50", "P20", "Grueso", "Intermedio", "Finos"]
    existing_cols = [c for c in output_cols if c in df.columns]
    export_df = df[existing_cols].copy()

    # Drop columns that are entirely empty
    empty_cols = [c for c in export_df.columns if export_df[c].isna().all()]
    if empty_cols:
        export_df.drop(columns=empty_cols, inplace=True)

    # Round all float columns to 2 decimal places
    for col in export_df.columns:
        if pd.api.types.is_float_dtype(export_df[col]):
            export_df[col] = export_df[col].round(2)

    st.dataframe(export_df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(export_df)} rows × {len(export_df.columns)} columns from {len(uploaded_files)} file(s).")

    if empty_cols:
        st.info(f"ℹ️ Removed entirely empty column(s): {', '.join(empty_cols)}")

    # ==========================================================
    # DATA QUALITY CHECK
    # ==========================================================
    st.markdown("---")
    st.subheader("🔍 Data Quality Check")

    if st.button("▶️ Run Quality Check", use_container_width=True, key="drone_qc"):
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
            file_name="Escondida_DRONE_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📄 Download TXT (no headers)",
            txt_buffer.getvalue(),
            file_name="Escondida_DRONE_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload Excel, CSV, or TXT file(s) to begin.")
