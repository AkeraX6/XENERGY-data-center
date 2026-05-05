import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# SMALL HELPERS
# ==========================================================
def normalize_name(name: str) -> str:
    """Uppercase, remove spaces and underscores to compare column names."""
    return re.sub(r"[\s_]+", "", str(name)).upper()

def find_column(df, candidates):
    """Find a column in df whose normalized name matches any of candidates."""
    norm_candidates = {normalize_name(c) for c in candidates}
    for col in df.columns:
        if normalize_name(col) in norm_candidates:
            return col
    return None

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Posición de Palas (ES_POSP)</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Limpieza y transformación de datos de posición de palas (auto-detects input format).</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esposp"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel/CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:

    # ---------- Read file (Excel or CSV) ----------
    file_name = uploaded_file.name.lower()

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

    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    # ---------- Auto-detect format ----------
    col_hcarga = find_column(df, ["H_CARGA", "HCARGA", "H CARGA"])
    col_cuadrilla = find_column(df, ["CUADRILLA"])
    detected_format = "Format 1 (H_CARGA present)" if col_hcarga else "Format 2 (no H_CARGA)"
    st.info(f"🔎 Detected input: **{detected_format}**")

    original_rows = len(df)
    steps = []

    # ==========================================================
    # PROCESSING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # ---------- Detect columns ----------
        col_fecha = find_column(df, ["FECHA"])
        col_turno = find_column(df, ["TURNO"])
        col_pala = find_column(df, ["PALA"])
        col_x = find_column(df, ["DUMPX", "X"])
        col_y = find_column(df, ["DUMPY", "Y"])
        col_z = find_column(df, ["DUMPZ", "CENZ", "Z"])

        # Check minimum required columns
        missing_cols = []
        for name, col in [("FECHA", col_fecha), ("PALA", col_pala), ("X/DUMPX", col_x), ("Y/DUMPY", col_y), ("Z/DUMPZ/CENZ", col_z)]:
            if col is None:
                missing_cols.append(name)

        if missing_cols:
            st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
        else:
            # ---------- 1) FECHA → Dia / Mes / Año ----------
            df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
            before = len(df)
            df = df[df[col_fecha].notna()]
            deleted = before - len(df)
            if deleted > 0:
                steps.append(f"🗑️ FECHA invalid/empty rows removed: {deleted}")

            df["Dia"] = df[col_fecha].dt.day.astype(int)
            df["Mes"] = df[col_fecha].dt.month.astype(int)
            df["Año"] = df[col_fecha].dt.year.astype(int)
            steps.append("✔️ FECHA split into Dia / Mes / Año.")

            # ---------- 2) Turno ----------
            if col_turno is not None:
                turno_str = df[col_turno].astype(str).str.strip().str.upper()
                df["Turno"] = turno_str.map({"D": 1, "N": 2}).fillna(1).astype(int)
                steps.append("✔️ Turno mapped (D→1, N→2, empty→1).")
            else:
                df["Turno"] = 1000
                steps.append("ℹ️ Turno column not found → created and filled with 1000.")

            # ---------- 3) Cuadrilla ----------
            if col_cuadrilla is not None:
                cuadrilla_str = df[col_cuadrilla].astype(str).str.strip().str.upper()
                df["Cuadrilla"] = cuadrilla_str.map({"A": 1, "B": 2, "C": 3, "D": 4})
                before = len(df)
                df = df[df["Cuadrilla"].notna()]
                df["Cuadrilla"] = df["Cuadrilla"].astype(int)
                deleted = before - len(df)
                steps.append(f"✔️ Cuadrilla mapped (A=1..D=4). Invalid rows removed: {deleted}")
            else:
                df["Cuadrilla"] = 1000
                steps.append("ℹ️ Cuadrilla column not found → created and filled with 1000.")

            # ---------- 4) Pala: extract numbers only ----------
            before = len(df)
            mask_she = df[col_pala].astype(str).str.contains(r"SHE\d+", case=False, na=False)
            # Also accept purely numeric pala values
            mask_numeric = df[col_pala].astype(str).str.match(r"^\d+$", na=False)
            df = df[mask_she | mask_numeric]
            deleted = before - len(df)
            if deleted > 0:
                steps.append(f"✔️ Pala filtered for valid patterns. Rows removed: {deleted}")

            df["Pala"] = (
                df[col_pala]
                .astype(str)
                .str.extract(r"(\d+)$")[0]
                .astype(float)
                .fillna(0)
                .astype(int)
            )
            steps.append("✔️ Pala transformed to numeric (SHE0069 → 69).")

            # ---------- 5) Hora / Minuto from H_CARGA ----------
            if col_hcarga is not None:
                hc = df[col_hcarga].astype(str)
                match = hc.str.extract(r"(?P<hora>\d{1,2}):(?P<min>\d{1,2})")
                df["Hora"] = pd.to_numeric(match["hora"], errors="coerce")
                df["Minuto"] = pd.to_numeric(match["min"], errors="coerce")

                before = len(df)
                df = df[df["Hora"].notna() & df["Minuto"].notna()]
                df["Hora"] = df["Hora"].astype(int)
                df["Minuto"] = df["Minuto"].astype(int)
                deleted = before - len(df)
                steps.append(f"✔️ H_CARGA parsed into Hora / Minuto. Invalid rows removed: {deleted}")
            else:
                df["Hora"] = 1000
                df["Minuto"] = 1000
                steps.append("ℹ️ H_CARGA column not found → Hora and Minuto filled with 1000.")

            # ---------- 6) X, Y, Z ----------
            df["X"] = pd.to_numeric(df[col_x], errors="coerce")
            df["Y"] = pd.to_numeric(df[col_y], errors="coerce")
            df["Z"] = pd.to_numeric(df[col_z], errors="coerce")

            before = len(df)
            df = df[df["X"].notna() & df["Y"].notna() & df["Z"].notna()]
            deleted = before - len(df)
            if deleted > 0:
                steps.append(f"🗑️ Rows with invalid X/Y/Z removed: {deleted}")

            # Apply coordinate range filters only for Format 1 (DUMPX/DUMPY/CENZ)
            if col_hcarga is not None and len(df) > 0:
                before = len(df)
                df = df[(df["X"] > 10000) & (df["X"] < 40000)]
                deleted = before - len(df)
                steps.append(f"✔️ X filtered (10,000 < X < 40,000). Rows removed: {deleted}")

                before = len(df)
                df = df[(df["Y"] > 80000) & (df["Y"] < 400000)]
                deleted = before - len(df)
                steps.append(f"✔️ Y filtered (80,000 < Y < 400,000). Rows removed: {deleted}")

                before = len(df)
                df = df[(df["Z"] > 2000) & (df["Z"] < 4000)]
                deleted = before - len(df)
                steps.append(f"✔️ Z filtered (2,000 < Z < 4,000). Rows removed: {deleted}")
            elif col_hcarga is None:
                steps.append("ℹ️ Format 2 detected — X/Y/Z range filters skipped.")

            # ---------- Summary ----------
            total_deleted = original_rows - len(df)
            steps.append(f"📉 Total rows deleted after all filters: {total_deleted}")

        # Show steps
        for step in steps:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:8px;border-radius:6px;margin-bottom:6px;'>"
                f"<span style='color:#137333;font-weight:500;font-size:13px;'>{step}</span></div>",
                unsafe_allow_html=True,
            )

    # ==========================================================
    # AFTER CLEANING — RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Cleaned Data Preview")

    output_cols = ["Dia", "Mes", "Año", "Turno", "Cuadrilla", "Pala", "Hora", "Minuto", "X", "Y", "Z"]
    existing_output_cols = [c for c in output_cols if c in df.columns]
    export_df = df[existing_output_cols].copy()

    st.dataframe(export_df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(export_df)} rows × {len(export_df.columns)} columns.")

    # ==========================================================
    # DATA QUALITY CHECK
    # ==========================================================
    st.markdown("---")
    st.subheader("🔍 Data Quality Check")

    if st.button("▶️ Run Quality Check", use_container_width=True, key="posp_qc"):
        total_rows = len(export_df)

        if total_rows == 0:
            st.error("❌ No data to check — the dataset is empty after cleaning.")
        else:
            issues_found = False
            report_lines = []

            for col in export_df.columns:
                col_issues = []

                # 1) Empty / NaN
                empty_count = int(export_df[col].isna().sum() + (export_df[col].astype(str).str.strip() == "").sum())
                if empty_count > 0:
                    col_issues.append(f"**{empty_count}** empty value(s)")

                # 2) Text (letters)
                non_empty = export_df[col].dropna().astype(str).str.strip()
                non_empty = non_empty[non_empty != ""]
                if len(non_empty) > 0:
                    text_mask = non_empty.apply(lambda x: bool(re.search(r"[A-Za-z]", str(x))))
                    text_count = int(text_mask.sum())
                else:
                    text_count = 0
                if text_count > 0:
                    col_issues.append(f"**{text_count}** cell(s) contain text/letters")

                # 3) Special characters
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
            file_name="Escondida_POSP_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📄 Download TXT (no headers)",
            txt_buffer.getvalue(),
            file_name="Escondida_POSP_Cleaned.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")

