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

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Excavator Performance (ES_EXCA)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Cleaning and structuring excavation shift data (auto-detects input format).</p>",
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

uploaded_files = st.file_uploader(
    "📤 Upload your excavation file(s)",
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
            df_raw = read_csv_smart(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
        all_dfs_raw.append(df_raw)

    merged_raw = pd.concat(all_dfs_raw, ignore_index=True)
    df = merged_raw.copy()

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}  ({len(uploaded_files)} file(s) merged)")

    original_rows = len(df)
    total_deleted = 0
    steps_done = []

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

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
            steps_done.append(f"✅ FECHA: split into Dia/Mes/Año. Invalid rows removed: {deleted}")
        else:
            steps_done.append("⚠️ Column 'FECHA' not found — Dia/Mes/Año not created.")

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
            steps_done.append("✅ TURNO: mapped D→1, N→2, default 1.")
        else:
            df["TURNO"] = 1000
            steps_done.append("ℹ️ TURNO column not found → created and filled with 1000.")

        # STEP 3 – CUADRILLA
        if col_cuadrilla is not None:
            df[col_cuadrilla] = df[col_cuadrilla].astype(str).str.strip().str.upper()
            mapping_cuad = {"A": 1, "B": 2, "C": 3, "D": 4}
            df["CUADRILLA"] = df[col_cuadrilla].replace(mapping_cuad)
            # Try to convert to numeric; rows that can't map stay as-is
            df["CUADRILLA"] = pd.to_numeric(df["CUADRILLA"], errors="coerce")
            before = len(df)
            df = df[df["CUADRILLA"].notna()]
            df["CUADRILLA"] = df["CUADRILLA"].astype(int)
            deleted = before - len(df)
            total_deleted += deleted
            steps_done.append(f"✅ CUADRILLA: mapped A→1, B→2, C→3, D→4. Invalid rows removed: {deleted}")
        else:
            df["CUADRILLA"] = 1000
            steps_done.append("ℹ️ CUADRILLA column not found → created and filled with 1000.")

        # STEP 4 – HORA & HoraReal
        if col_hora is not None:
            if col_hora != "HORA":
                df.rename(columns={col_hora: "HORA"}, inplace=True)
                steps_done.append(f"ℹ️ Detected hour column '{col_hora}' → renamed to 'HORA'.")

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
            steps_done.append(f"✅ HORA/HoraReal: removed {deleted} invalid rows, computed HoraReal from TURNO.")
        else:
            df["HORA"] = 1000
            df["HoraReal"] = 1000
            steps_done.append("ℹ️ HORA column not found → HORA and HoraReal filled with 1000.")

        # STEP 5 – PALA (might be PALA1)
        if col_pala is not None:
            df["PALA"] = df[col_pala].astype(str).str.extract(r"(\d+)", expand=False)
            df["PALA"] = pd.to_numeric(df["PALA"], errors="coerce")
            steps_done.append(f"✅ PALA (from '{col_pala}'): extracted numeric suffix (SHE0097 → 97).")
        else:
            steps_done.append("⚠️ Column 'PALA'/'PALA1' not found.")

        # STEP 6 – Filter TASAEXCA (0, empty, >300000 → delete)
        if col_tasaexca is not None:
            if col_tasaexca != "TASAEXCA":
                df.rename(columns={col_tasaexca: "TASAEXCA"}, inplace=True)

            before = len(df)
            df["TASAEXCA"] = pd.to_numeric(df["TASAEXCA"], errors="coerce")
            df = df[df["TASAEXCA"].notna()]
            df = df[(df["TASAEXCA"] > 0) & (df["TASAEXCA"] <= 300000)]
            deleted = before - len(df)
            total_deleted += deleted
            steps_done.append(f"✅ TASAEXCA: removed {deleted} rows (empty, 0, or >300000).")
        else:
            steps_done.append("⚠️ Column 'TASAEXCA' not found — no filter applied.")

        # STEP 7 – COLA
        if col_cola is not None:
            df["COLA"] = pd.to_numeric(df[col_cola], errors="coerce")
            steps_done.append("✅ COLA: kept as numeric.")
        else:
            df["COLA"] = 1000
            steps_done.append("ℹ️ COLA column not found → created and filled with 1000.")

        # STEP 8 – ACULA / BOTA
        if col_acula is not None:
            df["ACULA"] = pd.to_numeric(df[col_acula], errors="coerce")
            steps_done.append(f"✅ ACULA (from '{col_acula}'): kept as numeric.")
        else:
            df["ACULA"] = 1000
            steps_done.append("ℹ️ ACULA/BOTA column not found → created and filled with 1000.")

        # STEP 9 – CARG
        if col_carg is not None:
            df["CARG"] = pd.to_numeric(df[col_carg], errors="coerce")
            steps_done.append("✅ CARG: kept as numeric.")
        else:
            steps_done.append("⚠️ Column 'CARG' not found.")

        # --- Show all step messages ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:8px 10px;border-radius:8px;margin-bottom:6px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

        final_rows = len(df)
        total_deleted_summary = original_rows - final_rows
        st.markdown(
            f"<div style='background-color:#fff3cd;padding:10px;border-radius:8px;margin-top:10px;'>"
            f"<b>🧮 Summary:</b> Started with <b>{original_rows}</b> rows, "
            f"finished with <b>{final_rows}</b> rows. "
            f"<b>{total_deleted_summary}</b> rows deleted in total.</div>",
            unsafe_allow_html=True
        )

    # ==========================================================
    # OUTPUT
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Cleaned Data Preview")

    output_cols = ["Dia", "Mes", "Año", "TURNO", "CUADRILLA", "HORA", "HoraReal", "PALA", "TASAEXCA", "COLA", "ACULA", "CARG"]
    existing_output_cols = [c for c in output_cols if c in df.columns]
    export_df = df[existing_output_cols].copy()

    # Round all float columns to 2 decimal places
    for col in export_df.columns:
        if pd.api.types.is_float_dtype(export_df[col]):
            export_df[col] = export_df[col].round(2)

    st.dataframe(export_df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(export_df)} rows × {len(export_df.columns)} columns from {len(uploaded_files)} file(s).")

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
            file_name="Escondida_EXCA_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📄 Download TXT (no headers)",
            txt_buffer.getvalue(),
            file_name="Escondida_EXCA_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")


