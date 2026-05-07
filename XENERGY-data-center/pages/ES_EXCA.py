import streamlit as st
import pandas as pd
import io
import re

# ==========================================================
# SMALL HELPERS
# ==========================================================
def normalize_name(name: str) -> str:
    return re.sub(r"[\s_]+", "", str(name)).upper()

def find_column(df, candidates):
    norm_candidates = {normalize_name(c) for c in candidates}
    for col in df.columns:
        if normalize_name(col) in norm_candidates:
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
    if name.endswith(".csv"):
        return read_csv_smart(file_obj)
    else:
        return pd.read_excel(file_obj)

# ==========================================================
# CORE PROCESSING FUNCTION (one file at a time)
# ==========================================================
def process_file(df):
    """Clean one dataframe and return (cleaned_df, steps, error_msg)."""
    steps = []
    original_rows = len(df)
    total_deleted = 0

    # ---------- Detect key columns ----------
    col_fecha = find_column(df, ["FECHA", "FECHA1"])
    col_turno = find_column(df, ["TURNO"])
    col_cuadrilla = find_column(df, ["CUADRILLA", "CUADRILL"])
    col_hora = find_column(df, ["HORA", "HORA1", "HORA 1"])
    col_pala = find_column(df, ["PALA", "PALA1"])
    col_tasaexca = find_column(df, ["TASAEXCA", "TASAEXC", "TASA_EXCA", "TASA EXCA"])
    col_cola = find_column(df, ["COLA"])
    col_acula = find_column(df, ["ACULA", "BOTA"])
    col_carg = find_column(df, ["CARG"])

    # STEP 1 – FECHA → Dia, Mes, Año
    if col_fecha is not None:
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
        before = len(df)
        df = df[df[col_fecha].notna()]
        deleted = before - len(df)
        total_deleted += deleted
        df["Dia"] = df[col_fecha].dt.day.astype(int)
        df["Mes"] = df[col_fecha].dt.month.astype(int)
        df["Año"] = df[col_fecha].dt.year.astype(int)
        steps.append(f"✅ FECHA: split into Dia/Mes/Año. Invalid rows removed: {deleted}")
    else:
        return None, steps, "Column 'FECHA' not found."

    # STEP 2 – TURNO
    if col_turno is not None:
        df[col_turno] = df[col_turno].astype(str).str.strip().str.upper()
        def map_turno(val):
            if val in ["D", "1"]:
                return 1
            if val in ["N", "2"]:
                return 2
            if val == "" or val.lower() == "nan":
                return 1
            try:
                return int(val)
            except Exception:
                return 1
        df["TURNO"] = df[col_turno].apply(map_turno)
        steps.append("✅ TURNO: mapped D→1, N→2, default 1.")
    else:
        df["TURNO"] = 1000
        steps.append("ℹ️ TURNO not found → filled with 1000.")

    # STEP 3 – CUADRILLA
    if col_cuadrilla is not None:
        df[col_cuadrilla] = df[col_cuadrilla].astype(str).str.strip().str.upper()
        mapping_cuad = {"A": 1, "B": 2, "C": 3, "D": 4}
        df["CUADRILLA"] = df[col_cuadrilla].replace(mapping_cuad)
        df["CUADRILLA"] = pd.to_numeric(df["CUADRILLA"], errors="coerce")
        before = len(df)
        df = df[df["CUADRILLA"].notna()]
        df["CUADRILLA"] = df["CUADRILLA"].astype(int)
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"✅ CUADRILLA: mapped A→1..D→4. Invalid rows removed: {deleted}")
    else:
        df["CUADRILLA"] = 1000
        steps.append("ℹ️ CUADRILLA not found → filled with 1000.")

    # STEP 4 – HORA & HoraReal
    if col_hora is not None:
        if col_hora != "HORA":
            df.rename(columns={col_hora: "HORA"}, inplace=True)
        before = len(df)
        df["HORA"] = pd.to_numeric(df["HORA"], errors="coerce")
        df = df[df["HORA"].notna()]
        deleted = before - len(df)
        total_deleted += deleted

        def compute_hora_real(row):
            h = row["HORA"]
            t = row.get("TURNO", 1)
            try:
                t = int(t)
            except Exception:
                t = 1
            if pd.isna(h):
                return None
            if t == 1:
                return 8 + h
            return (20 + h) % 24

        df["HoraReal"] = df.apply(compute_hora_real, axis=1)
        steps.append(f"✅ HORA/HoraReal: removed {deleted} invalid rows.")
    else:
        df["HORA"] = 1000
        df["HoraReal"] = 1000
        steps.append("ℹ️ HORA not found → HORA and HoraReal filled with 1000.")

    # STEP 5 – PALA
    if col_pala is not None:
        df["PALA"] = df[col_pala].astype(str).str.extract(r"(\d+)", expand=False)
        df["PALA"] = pd.to_numeric(df["PALA"], errors="coerce")
        steps.append(f"✅ PALA (from '{col_pala}'): extracted numeric.")
    else:
        return None, steps, "Column 'PALA' not found."

    # STEP 6 – TASAEXCA filter
    if col_tasaexca is not None:
        if col_tasaexca != "TASAEXCA":
            df.rename(columns={col_tasaexca: "TASAEXCA"}, inplace=True)
        before = len(df)
        df["TASAEXCA"] = pd.to_numeric(df["TASAEXCA"], errors="coerce")
        df = df[df["TASAEXCA"].notna()]
        df = df[(df["TASAEXCA"] > 0) & (df["TASAEXCA"] <= 300000)]
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"✅ TASAEXCA: removed {deleted} rows (empty, 0, or >300000).")
    else:
        steps.append("⚠️ TASAEXCA not found — no filter applied.")

    # STEP 7 – COLA
    if col_cola is not None:
        df["COLA"] = pd.to_numeric(df[col_cola], errors="coerce")
        steps.append("✅ COLA: kept as numeric.")
    else:
        df["COLA"] = 1000
        steps.append("ℹ️ COLA not found → filled with 1000.")

    # STEP 8 – ACULA / BOTA
    if col_acula is not None:
        df["ACULA"] = pd.to_numeric(df[col_acula], errors="coerce")
        steps.append(f"✅ ACULA (from '{col_acula}'): kept as numeric.")
    else:
        df["ACULA"] = 1000
        steps.append("ℹ️ ACULA/BOTA not found → filled with 1000.")

    # STEP 9 – CARG
    if col_carg is not None:
        df["CARG"] = pd.to_numeric(df[col_carg], errors="coerce")
        steps.append("✅ CARG: kept as numeric.")
    else:
        df["CARG"] = 1000
        steps.append("ℹ️ CARG not found → filled with 1000.")

    # --- Summary ---
    final_rows = len(df)
    steps.append(f"📉 Total rows deleted: {total_deleted} | Remaining: {final_rows}")

    # Select output columns
    output_cols = ["Dia", "Mes", "Año", "TURNO", "CUADRILLA", "HORA", "HoraReal", "PALA", "TASAEXCA", "COLA", "ACULA", "CARG"]
    df = df[[c for c in output_cols if c in df.columns]].copy()

    # Round floats
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].round(2)

    return df, steps, None

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Excavator Performance (ES_EXCA)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Cleaning and structuring excavation shift data (auto-detects input format). Supports multiple files.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esexca"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD (MULTIPLE FILES)
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload your excavation file(s)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
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

        if st.button("▶️ Run Quality Check", use_container_width=True, key="exca_qc"):
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

        # Build date range string from the data (oldest_newest)
        try:
            dates = pd.to_datetime(
                export_df[["Dia", "Mes", "Año"]].rename(columns={"Dia": "day", "Mes": "month", "Año": "year"})
            )
            oldest = dates.min().strftime("%d%m%Y")
            newest = dates.max().strftime("%d%m%Y")
            date_tag = f"{oldest}_{newest}"
        except Exception:
            date_tag = "unknown"

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
                file_name=f"ES_EXCA_{date_tag}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📄 Download TXT (no headers)",
                txt_buffer.getvalue(),
                file_name=f"ES_EXCA_{date_tag}.txt",
                mime="text/plain",
                use_container_width=True
            )
    else:
        st.error("❌ No valid data produced from any uploaded file.")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload one or more Excel/CSV files to begin.")


