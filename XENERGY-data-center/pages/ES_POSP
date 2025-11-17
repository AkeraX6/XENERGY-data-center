import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Posición de Palas (ES_POSP)</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Limpieza automática y preparación de datos de posición de palas.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esposp"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your file", type=["xlsx", "xls", "csv"])

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

if uploaded_file is not None:
    file_name = uploaded_file.name.lower()

    # Read Excel or CSV
    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    original_rows = len(df)
    st.info(f"📏 Total rows before cleaning: {original_rows}")

    steps_done = []

    # ==========================================================
    # CLEANING & TRANSFORMATION STEPS
    # ==========================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):

        # STEP 1 – Split Fecha into Día / Mes / Año
        if "Fecha" in df.columns:
            before = len(df)

            # Parse date safely (assume day-first, typical in Escondida export)
            fecha_parsed = pd.to_datetime(df["Fecha"], errors="coerce", dayfirst=True)

            # Drop rows where Fecha can't be parsed
            df = df[fecha_parsed.notna()].copy()
            fecha_parsed = fecha_parsed.loc[df.index]

            df["Dia"] = fecha_parsed.dt.day
            df["Mes"] = fecha_parsed.dt.month
            df["Año"] = fecha_parsed.dt.year

            deleted = before - len(df)
            steps_done.append(
                f"✅ Split 'Fecha' into 'Dia', 'Mes', 'Año' and removed {deleted} rows with invalid dates."
            )
        else:
            steps_done.append("❌ Column 'Fecha' not found — skipping date split.")

        # STEP 2 – Turno: N→2, D→1
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].astype(str).str.strip().str.upper()
            df["Turno"] = df["Turno"].replace({"D": 1, "N": 2})
            steps_done.append("✅ Converted 'Turno': D→1, N→2.")
        else:
            steps_done.append("❌ Column 'Turno' not found.")

        # STEP 3 – Cuadrilla: A→1, B→2, C→3, D→4
        if "Cuadrilla" in df.columns:
            df["Cuadrilla"] = df["Cuadrilla"].astype(str).str.strip().str.upper()
            df["Cuadrilla"] = df["Cuadrilla"].replace({"A": 1, "B": 2, "C": 3, "D": 4})
            steps_done.append("✅ Converted 'Cuadrilla': A→1, B→2, C→3, D→4.")
        else:
            steps_done.append("❌ Column 'Cuadrilla' not found.")

        # STEP 4 – Pala: keep SHE00XX and convert SHE0067 → 67
        if "PALA" in df.columns:
            before = len(df)

            # Normalize
            df["PALA"] = df["PALA"].astype(str).str.strip().str.upper()

            # Keep only rows matching SHE00XX (2 digits at the end)
            mask_pattern = df["PALA"].str.match(r"^SHE00\d{2}$", na=False)
            df = df[mask_pattern].copy()

            # Extract last two digits
            df["Pala_clean"] = df["PALA"].str.extract(r"(\d{2})", expand=False)
            df["Pala_clean"] = pd.to_numeric(df["Pala_clean"], errors="coerce")
            df = df[df["Pala_clean"].notna()].copy()
            df["Pala_clean"] = df["Pala_clean"].astype(int)

            # Overwrite PALA with cleaned numeric value
            df["Pala"] = df["Pala_clean"]
            df.drop(columns=["Pala_clean"], inplace=True)

            deleted = before - len(df)
            steps_done.append(
                f"✅ Filtered 'PALA' to SHE00XX pattern and converted to numeric (deleted {deleted} non-matching rows)."
            )
        else:
            steps_done.append("❌ Column 'PALA' not found.")

        # STEP 5 – H_CARGA → split into Hora, Minuto
        if "H_CARGA" in df.columns:
            before = len(df)

            def parse_time(val):
                if pd.isna(val):
                    return None, None
                text = str(val)
                # Match HH:MM:SS or HH:MM with optional millis
                m = re.match(r"\s*(\d{1,2}):(\d{1,2})", text)
                if not m:
                    return None, None
                h = int(m.group(1))
                mnt = int(m.group(2))
                return h, mnt

            hours = []
            minutes = []
            for v in df["H_CARGA"]:
                h, mnt = parse_time(v)
                hours.append(h)
                minutes.append(mnt)

            df["Hora"] = hours
            df["Minuto"] = minutes

            # Drop rows where hour or minute could not be parsed
            df = df[df["Hora"].notna() & df["Minuto"].notna()].copy()
            df["Hora"] = df["Hora"].astype(int)
            df["Minuto"] = df["Minuto"].astype(int)

            deleted = before - len(df)
            steps_done.append(
                f"✅ Parsed 'H_CARGA' into 'Hora' and 'Minuto' (removed {deleted} rows with invalid time)."
            )
        else:
            steps_done.append("❌ Column 'H_CARGA' not found — cannot create Hora/Minuto.")

        # STEP 6 – DUMPX: keep 16000 ≤ DUMPX ≤ 40000
        if "DUMPX" in df.columns:
            before = len(df)
            df["DUMPX"] = pd.to_numeric(df["DUMPX"], errors="coerce")
            df = df[df["DUMPX"].notna()].copy()
            df = df[(df["DUMPX"] >= 16000) & (df["DUMPX"] <= 40000)]
            deleted = before - len(df)
            steps_done.append(
                f"✅ Filtered 'DUMPX' to [16000, 40000] (deleted {deleted} rows outside range or invalid)."
            )
        else:
            steps_done.append("❌ Column 'DUMPX' not found.")

        # STEP 7 – DUMPY: keep DUMPY ≥ 110000
        if "DUMPY" in df.columns:
            before = len(df)
            df["DUMPY"] = pd.to_numeric(df["DUMPY"], errors="coerce")
            df = df[df["DUMPY"].notna()].copy()
            df = df[df["DUMPY"] >= 110000]
            deleted = before - len(df)
            steps_done.append(
                f"✅ Filtered 'DUMPY' to ≥ 110000 (deleted {deleted} rows outside range or invalid)."
            )
        else:
            steps_done.append("❌ Column 'DUMPY' not found.")

        # STEP 8 – DUMPZ: keep 2000 ≤ DUMPZ ≤ 5000
        # (assuming the Z coordinate column is named 'DUMPZ')
        if "DUMPZ" in df.columns:
            before = len(df)
            df["DUMPZ"] = pd.to_numeric(df["DUMPZ"], errors="coerce")
            df = df[df["DUMPZ"].notna()].copy()
            df = df[(df["DUMPZ"] >= 2000) & (df["DUMPZ"] <= 5000)]
            deleted = before - len(df)
            steps_done.append(
                f"✅ Filtered 'DUMPZ' to [2000, 5000] (deleted {deleted} rows outside range or invalid)."
            )
        else:
            steps_done.append("❌ Column 'DUMPZ' not found (expected Z coordinate).")

        # STEP 9 – Prepare final columns & rename X/Y/Z
        # Map X/Y/Z from dump coordinates
        if all(col in df.columns for col in ["DUMPX", "DUMPY", "DUMPZ"]):
            df["X"] = df["DUMPX"]
            df["Y"] = df["DUMPY"]
            df["Z"] = df["DUMPZ"]
            steps_done.append("✅ Renamed dump coordinates to X, Y, Z.")
        else:
            steps_done.append("⚠️ Could not map DUMPX/DUMPY/DUMPZ to X/Y/Z (one or more missing).")

        # Desired output column order
        final_cols = ["Dia", "Mes", "Año", "Turno", "Cuadrilla", "Pala", "Hora", "Minuto", "X", "Y", "Z"]
        existing_final_cols = [c for c in final_cols if c in df.columns]
        df_final = df[existing_final_cols].copy()

        # --- Display Steps in Green Cards ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

        # Total deleted rows
        final_rows = len(df_final)
        total_deleted = original_rows - final_rows
        st.info(
            f"🧮 Total rows deleted from original to final output: {total_deleted} "
            f"(Final dataset: {final_rows} rows)."
        )

    # ==========================================================
    # AFTER CLEANING — RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df_final.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df_final)} rows × {len(df_final.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    option = st.radio("Choose download option:", ["⬇️ Download All Final Columns", "🧩 Download Selected Columns"])

    if option == "⬇️ Download All Final Columns":
        export_df = df_final
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(df_final.columns),
            default=list(df_final.columns)
        )
        export_df = df_final[selected_columns] if selected_columns else df_final

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
            file_name="Escondida_POSP_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="Escondida_POSP_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")
