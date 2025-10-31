import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>Mantos Blancos — Autonomía Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning and structuring of Autonomía drilling data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_mbauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_file = st.file_uploader("📤 Upload your Excel file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    # --- READ FILE ---
    df = pd.read_excel(uploaded_file)
    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    df.columns = [c.strip() for c in df.columns]
    steps_done = []

    # ==================================================
    # CLEANING STEPS — SINGLE EXPANDER
    # ==================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):
        # STEP 1 – Remove rows with empty Coord X/Y/Cota
        coord_cols = ["Coord X", "Coord Y", "Cota"]
        if all(col in df.columns for col in coord_cols):
            before = len(df)
            df = df.dropna(subset=coord_cols, how="any")
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows missing Coord X/Y/Cota")
        else:
            steps_done.append("❌ Missing one or more coordinate columns")

        # STEP 2 – Remove unwanted Tipo Pozo rows
        if "Tipo Pozo" in df.columns:
            before = len(df)
            df = df[~df["Tipo Pozo"].astype(str).str.lower().str.contains("aux|auxiliar|hundimiento", na=False)]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with Auxiliar/Hundimiento Tipo Pozo")
        else:
            steps_done.append("⚠️ Column 'Tipo Pozo' not found")

        # STEP 3 – Standardize Grupo values
        if "Grupo" in df.columns:
            df["Grupo"] = df["Grupo"].astype(str).str.upper().replace({
                "G_1": 1, "G1": 1, "G_2": 2, "G2": 2,
                "G_3": 3, "G3": 3, "G_4": 4, "G4": 4
            })
            steps_done.append("✅ Grupo values standardized (G1–G4 → 1–4)")
        else:
            steps_done.append("⚠️ Column 'Grupo' not found")

        # STEP 4 – Replace Turno values
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].astype(str).str.upper().replace({"TA": 1, "TB": 2})
            steps_done.append("✅ Turno values converted (TA→1, TB→2)")
        else:
            steps_done.append("⚠️ Column 'Turno' not found")

        # STEP 5 – Extract numeric part from Fase
        if "Fase" in df.columns:
            df["Fase"] = df["Fase"].astype(str).str.extract(r"(\d+)", expand=False)
            steps_done.append("✅ Extracted numeric part from Fase column")
        else:
            steps_done.append("⚠️ Column 'Fase' not found")

        # STEP 6 – Map Tipo Pozo categories
        if "Tipo Pozo" in df.columns:
            df["Tipo Pozo"] = df["Tipo Pozo"].astype(str).str.title().replace({
                "Produccion": 1, "Buffer": 2, "Alergue": 3, "Repaso": 4, "Relleno": 5
            })
            steps_done.append("✅ Tipo Pozo categories mapped to numeric codes")
        else:
            steps_done.append("⚠️ Column 'Tipo Pozo' not found")

        # STEP 7 – Clean Modelo column
        if "Modelo" in df.columns:
            def clean_modelo(val):
                if pd.isna(val) or str(val).strip() == "":
                    return None
                val = str(val).strip().upper()
                digits = re.findall(r"\d+", val)
                if not digits:
                    return None
                num = digits[0]
                return num[:2] if len(num) >= 3 else num

            df["Modelo"] = df["Modelo"].apply(clean_modelo).fillna("53")
            steps_done.append("✅ Cleaned Modelo values; empty entries filled with 53")
        else:
            steps_done.append("⚠️ Column 'Modelo' not found")

        # STEP 8 – Map Operador names to IDs
        operator_map = {
            "alejandro maldonado m.": 1, "alex diaz d.": 2, "anderson torres": 3,
            "boris cifuentes a.": 4, "celestino lopez": 5, "celestino lopez lopez": 5,
            "christian gallegos g.": 6, "cristhian rivas lopez": 7, "cristian quinteros": 8,
            "cristian yañez g": 9, "daniel julio s.": 10, "danilo manquez c.": 11,
            "eduardo leon p.": 12, "eduardo paredes c.": 13, "emerson gonzalez corona": 14,
            "favian castillo g.": 15, "felix cifuentes a.": 16, "fernando caceres c.": 17,
            "fernando gonzalez g.": 18, "francisco bolta g.": 19, "francisco curin h.": 20,
            "freddy olivares r.": 21, "jaime tirado c.": 22, "javier gaete f.": 23,
            "jorge alday a.": 24, "jorge muñoz": 25, "jorge muñoz v.": 25,
            "julio araya p.": 26, "luis campos d.": 27, "luis flores": 28,
            "manuel valencia r.": 29, "marcelo angel c.": 30, "marco jofre r.": 31,
            "marcos machuca alday": 32, "mario quintana g.": 33, "mauricio salazar": 34,
            "miguel carrasco m.": 35, "mirto canivilo b.": 36, "nicolas muñoz": 37,
            "oscar carrizo f.": 38, "oscar ocayo c.": 39, "oscar ocayo carmona": 39,
            "oscar perez g.": 40, "patricio faundes": 41, "rene zarricueta": 42,
            "ruben saez a.": 43, "solange hernández": 44, "vincent veliz a.": 45,
            "yasna mena": 46
        }

        if "Operador" in df.columns:
            df["Operador_original"] = df["Operador"]
            df["Operador_clean"] = df["Operador"].astype(str).str.lower().str.strip()
            df["Operador_ID"] = df["Operador_clean"].map(operator_map).fillna(47)
            unknown = df[df["Operador_ID"] == 47]["Operador"].unique()
            df["Operador"] = df["Operador_ID"]
            df.drop(columns=["Operador_clean", "Operador_ID"], inplace=True)
            steps_done.append(f"✅ Operator names mapped; {len(unknown)} unknowns set to ID 47")
        else:
            steps_done.append("⚠️ Column 'Operador' not found")

        # --- Display Steps ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

    # ==================================================
    # AFTER CLEANING — SHOW RESULTS
    # ==================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(15), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    # ==================================================
    # DOWNLOAD SECTION
    # ==================================================
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
            file_name="MB_Autonomia_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="MB_Autonomia_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam -Omar El Kendi-")

else:
    st.info("📂 Please upload an Excel file to begin.")

