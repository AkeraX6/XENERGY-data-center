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
    "<p style='text-align:center; color:gray;'>Limpieza y transformación de datos de posición de palas.</p>",
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

    original_rows = len(df)
    steps = []

    # ==========================================================
    # PROCESSING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # ---------- Detect columns (case/space-insensitive) ----------
        col_fecha = find_column(df, ["FECHA"])
        col_turno = find_column(df, ["TURNO"])
        col_cuadrilla = find_column(df, ["CUADRILLA"])
        col_pala = find_column(df, ["PALA"])
        col_hcarga = find_column(df, ["H_CARGA", "HCARGA", "H CARGA"])
        col_dumpx = find_column(df, ["DUMPX"])
        col_dumpy = find_column(df, ["DUMPY"])
        col_dumpz = find_column(df, ["DUMPZ", "CENZ"])

        missing_cols = []
        for name, col in [
            ("FECHA", col_fecha),
            ("TURNO", col_turno),
            ("CUADRILLA", col_cuadrilla),
            ("PALA", col_pala),
            ("H_CARGA", col_hcarga),
            ("DUMPX", col_dumpx),
            ("DUMPY", col_dumpy),
            ("DUMPZ/CENZ", col_dumpz),
        ]:
            if col is None:
                missing_cols.append(name)

        if missing_cols:
            st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
        else:
            # ---------- 1) Split FECHA into Dia / Mes / Año ----------
            # Assumes FECHA is a valid date or string convertible to date
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

            # ---------- 2) Turno: D→1, N→2, default 1 ----------
            before = len(df)
            turno_str = df[col_turno].astype(str).str.strip().str.upper()
            df["Turno"] = turno_str.map({"D": 1, "N": 2}).fillna(1).astype(int)
            steps.append("✔️ Turno normalized (D→1, N→2, empty→1). (No rows deleted here)")

            # ---------- 3) Cuadrilla: A→1, B→2, C→3, D→4 ----------
            cuadrilla_str = df[col_cuadrilla].astype(str).str.strip().str.upper()
            df["Cuadrilla"] = cuadrilla_str.map({"A": 1, "B": 2, "C": 3, "D": 4})
            # If something is not A–D, mark as NaN and drop those rows
            before = len(df)
            df = df[df["Cuadrilla"].notna()]
            df["Cuadrilla"] = df["Cuadrilla"].astype(int)
            deleted = before - len(df)
            steps.append(f"✔️ Cuadrilla mapped (A=1..D=4). Rows with invalid cuadrilla removed: {deleted}")

            # ---------- 4) PALA: keep only SHE00XX and transform to numeric (e.g., SHE0068→68) ----------
            before = len(df)
            mask_she = df[col_pala].astype(str).str.contains(r"SHE00", case=False, na=False)
            df = df[mask_she]
            deleted = before - len(df)
            steps.append(f"✔️ Pala filtered for SHE00XX pattern. Rows removed: {deleted}")

            # Extract numeric suffix
            df["Pala"] = (
                df[col_pala]
                .astype(str)
                .str.extract(r"(\d+)$")[0]
                .astype(float)
                .fillna(0)
                .astype(int)
            )
            steps.append("✔️ Pala transformed to numeric (SHE0067 → 67).")

            # ---------- 5) H_CARGA → Hora / Minuto ----------
            # Expect format like '02:31:41.0000000'
            before = len(df)
            hc = df[col_hcarga].astype(str)

            # Parse hours/minutes with regex
            match = hc.str.extract(r"(?P<hora>\d{1,2}):(?P<min>\d{1,2})")
            df["Hora"] = pd.to_numeric(match["hora"], errors="coerce")
            df["Minuto"] = pd.to_numeric(match["min"], errors="coerce")

            # Drop rows where we could not parse
            df = df[df["Hora"].notna() & df["Minuto"].notna()]
            df["Hora"] = df["Hora"].astype(int)
            df["Minuto"] = df["Minuto"].astype(int)
            deleted = before - len(df)
            steps.append(f"✔️ H_CARGA parsed into Hora / Minuto. Rows with invalid time removed: {deleted}")

            # ---------- 6) DUMPX filter: keep 10,000 < X < 40,000 ----------
            before = len(df)
            df["X"] = pd.to_numeric(df[col_dumpx], errors="coerce")
            df = df[df["X"].notna()]
            df = df[(df["X"] > 10000) & (df["X"] < 40000)]
            deleted = before - len(df)
            steps.append(f"✔️ DUMPX filtered (10,000 < X < 40,000). Rows removed: {deleted}")

            # ---------- 7) DUMPY filter: keep 80,000 < Y < 400,000 ----------
            before = len(df)
            df["Y"] = pd.to_numeric(df[col_dumpy], errors="coerce")
            df = df[df["Y"].notna()]
            df = df[(df["Y"] > 80000) & (df["Y"] < 400000)]
            deleted = before - len(df)
            steps.append(f"✔️ DUMPY filtered (80,000 < Y < 400,000). Rows removed: {deleted}")

            # ---------- 8) DUMPZ / CENZ filter: keep 2,000 < Z < 4,000 ----------
            before = len(df)
            df["Z"] = pd.to_numeric(df[col_dumpz], errors="coerce")
            df = df[df["Z"].notna()]
            df = df[(df["Z"] > 2000) & (df["Z"] < 4000)]
            deleted = before - len(df)
            steps.append(f"✔️ Z (DUMPZ/CENZ) filtered (2,000 < Z < 4,000). Rows removed: {deleted}")

            # ---------- Summary deleted ----------
            total_deleted = original_rows - len(df)
            steps.append(f"📉 Total rows deleted after all filters: {total_deleted}")

        # Show steps in green cards
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

    # Final output in required order
    output_cols = ["Dia", "Mes", "Año", "Turno", "Cuadrilla", "Pala", "Hora", "Minuto", "X", "Y", "Z"]
    existing_output_cols = [c for c in output_cols if c in df.columns]
    export_df = df[existing_output_cols].copy()

    st.dataframe(export_df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(export_df)} rows × {len(export_df.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    option = st.radio("Choose download option:", ["⬇️ Download All Output Columns", "🧩 Download Custom Columns"])

    if option == "⬇️ Download All Output Columns":
        final_df = export_df
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(export_df.columns),
            default=list(export_df.columns),
        )
        final_df = export_df[selected_columns] if selected_columns else export_df

    # Excel
    excel_buffer = io.BytesIO()
    final_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    # TXT (semicolon-separated)
    txt_buffer = io.StringIO()
    final_df.to_csv(txt_buffer, index=False, sep=";")

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
            "📄 Download TXT (; separated)",
            txt_buffer.getvalue(),
            file_name="Escondida_POSP_Cleaned.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")
