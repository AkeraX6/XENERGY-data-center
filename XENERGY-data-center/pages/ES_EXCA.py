import streamlit as st
import pandas as pd
import io
import re

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Excavator Performance (ES_EXCA)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Cleaning and structuring excavation shift data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esexca"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your excavation file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:

    file_name = uploaded_file.name.lower()

    def read_csv_smart(file_obj):
        """Detect delimiter automatically for CSVs."""
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

    # Read file
    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    original_rows = len(df)
    total_deleted = 0
    steps_done = []

    # ==========================================================
    # NORMALIZE KEY COLUMN NAMES (HORA variants, CUADRILLA)
    # ==========================================================

    # --- Find HORA column (HORA, Hora, HORA 1, HORA1, etc.) ---
    hora_col = None
    for c in df.columns:
        cname = re.sub(r"\s+", "", str(c)).upper()   # remove spaces, uppercase
        if cname.startswith("HORA"):                 # HORA, HORA1, HORA_1, etc.
            hora_col = c
            break
    if hora_col and hora_col != "HORA":
        df.rename(columns={hora_col: "HORA"}, inplace=True)
        steps_done.append(f"ℹ️ Detected hour column '{hora_col}' and normalized name to 'HORA'.")
    elif hora_col == "HORA":
        steps_done.append("ℹ️ Using existing 'HORA' column as hour field.")
    else:
        steps_done.append("⚠️ No column matching HORA / HORA1 / HORA 1 found.")

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # STEP 1 – Clean TURNO (D/N → 1/2, default 1)
        if "TURNO" in df.columns:
            df["TURNO"] = df["TURNO"].astype(str).str.strip().str.upper()

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

            df["TURNO"] = df["TURNO"].apply(map_turno)
            steps_done.append("✅ TURNO: mapped D→1, N→2, default 1 for empty/invalid values.")
        else:
            steps_done.append("⚠️ Column 'TURNO' not found — cannot map shifts.")

        # STEP 2 – Map CUADRILLA (A–D → 1–4)
        cuadrilla_col = None
        for c in df.columns:
            if str(c).upper().startswith("CUADRILL"):
                cuadrilla_col = c
                break

        if cuadrilla_col:
            df[cuadrilla_col] = df[cuadrilla_col].astype(str).str.strip().str.upper()
            mapping_cuad = {"A": 1, "B": 2, "C": 3, "D": 4}
            df[cuadrilla_col] = df[cuadrilla_col].replace(mapping_cuad)
            df.rename(columns={cuadrilla_col: "CUADRILLA"}, inplace=True)
            steps_done.append("✅ CUADRILLA: mapped A→1, B→2, C→3, D→4.")
        else:
            steps_done.append("⚠️ CUADRILLA column not found.")

        # STEP 3 – Clean HORA and create HoraReal
        if "HORA" in df.columns:
            before = len(df)
            df["HORA"] = pd.to_numeric(df["HORA"], errors="coerce")
            df = df[df["HORA"].notna()]  # delete rows with empty/invalid HORA
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
                # Day shift: 0→8, 1→9, 2→10...
                if t == 1:
                    return 8 + h
                # Night shift: 0→20,1→21,2→22,3→23,4→0, etc.
                return (20 + h) % 24

            df["HoraReal"] = df.apply(compute_hora_real, axis=1)
            steps_done.append(
                f"✅ HORA / HoraReal: removed {deleted} rows with empty/invalid HORA and computed HoraReal using TURNO."
            )
        else:
            steps_done.append("⚠️ No usable HORA column found — HoraReal not created.")

        # STEP 4 – Clean PALA (keep numeric suffix only)
        if "PALA" in df.columns:
            df["PALA"] = df["PALA"].astype(str).str.extract(r"(\d+)", expand=False)
            df["PALA"] = pd.to_numeric(df["PALA"], errors="coerce")
            steps_done.append("✅ PALA: extracted numeric suffix (e.g. SHE0097 → 97).")
        else:
            steps_done.append("⚠️ Column 'PALA' not found.")

        # STEP 5 – Filter TASAEXCA (0, empty, >300000 → delete)
        if "TASAEXCA" in df.columns:
            before = len(df)
            df["TASAEXCA"] = pd.to_numeric(df["TASAEXCA"], errors="coerce")
            df = df[df["TASAEXCA"].notna()]
            df = df[(df["TASAEXCA"] > 0) & (df["TASAEXCA"] <= 300000)]
            deleted = before - len(df)
            total_deleted += deleted
            steps_done.append(
                f"✅ TASAEXCA: removed {deleted} rows (empty, 0, or >300000)."
            )
        else:
            steps_done.append("⚠️ Column 'TASAEXCA' not found — no filter applied.")

        # STEP 6 – Split FECHA into Dia, Mes, Año
        if "FECHA" in df.columns:
            before = len(df)
            df["FECHA_dt"] = pd.to_datetime(df["FECHA"], errors="coerce")
            df = df[df["FECHA_dt"].notna()]
            deleted = before - len(df)
            total_deleted += deleted

            df["Dia"] = df["FECHA_dt"].dt.day
            df["Mes"] = df["FECHA_dt"].dt.month
            df["Año"] = df["FECHA_dt"].dt.year
            steps_done.append(
                f"✅ FECHA: converted to date, removed {deleted} invalid rows, and created Dia/Mes/Año."
            )
        else:
            steps_done.append("⚠️ Column 'FECHA' not found — Dia/Mes/Año not created.")

        # --- Show all step messages ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:8px 10px;border-radius:8px;margin-bottom:6px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

        # Total deleted summary
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
    # SELECT & ORDER OUTPUT COLUMNS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    st.markdown("---")
    st.subheader("📌 Choose Output Columns & Order")

    # Desired default order
    desired_cols = [
        "Dia", "Mes", "Año",
        "TURNO", "CUADRILLA",
        "HORA", "HoraReal",
        "PALA",
        "TASAEXCA",
        "COLA", "ACULA", "CARG"
    ]
    existing_defaults = [c for c in desired_cols if c in df.columns]

    selected_columns = st.multiselect(
        "Select columns for export (drag to reorder):",
        options=list(df.columns),
        default=existing_defaults
    )

    export_df = df[selected_columns] if selected_columns else df

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    # Excel
    excel_buffer = io.BytesIO()
    export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    # TXT (semicolon-separated)
    txt_buffer = io.StringIO()
    export_df.to_csv(txt_buffer, index=False, sep=";")

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
            "📄 Download TXT",
            txt_buffer.getvalue(),
            file_name="Escondida_EXCA_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")

