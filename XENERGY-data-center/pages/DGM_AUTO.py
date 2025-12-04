import streamlit as st
import pandas as pd
import io
import unicodedata
import re
from difflib import SequenceMatcher

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — Autonomía Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning, structuring, and export of DGM drilling data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_dgmauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, sep=";", engine="python")
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    steps_done = []
    total_deleted = 0

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):

        # Operator mapping base
        operator_mapping = {
            "Alberto Flores": 1, "Alex Nunez": 2, "Carla Vargas": 3, "Carlos Bugueno": 4, "Carlos Medina": 5,
            "Cristian Herrera": 6, "Francisco Pasten": 7, "Freddy Pena": 8, "German Leyton": 9, "German Vidal": 10,
            "Hugo Garcia": 11, "Jhonny Dubo": 12, "Jose Perez": 13, "Juan Gonzalez": 14, "Leonardo Ramirez": 15,
            "Miguel Guamparito": 16, "Oscar Arancibia": 17, "Pamela Ruiz": 18, "Patricio Plaza": 19, "Renan Bugueno": 20,
            "Rodrigo Cataldo": 21, "Sergio Gutierrez": 22, "Trepsa": 23, "Victor Rojas Chavez": 24,
            "Hernan Munoz": 26, "Jose Vallejos": 27, "Jose Villegas": 28, "Marcelo Villegas": 29, "Fabian Gallardo": 30,
            "Humberto Meneses": 32, "Mario Maya": 33, "Mario Rivera": 34, "Mauricio Villegas": 35,
            "Fabian Guerrero": 36, "Ricardo Ortiz": 37,
        }

        def normalize_name(n):
            if pd.isna(n): return ""
            return unicodedata.normalize('NFD', str(n).lower()).encode('ascii', 'ignore').decode()

        def match_operator(name):
            if pd.isna(name) or str(name).strip() == "":
                return 25
            clean = normalize_name(name)
            for o, code in operator_mapping.items():
                if normalize_name(o) == clean:
                    return code
            return 25

        # Operator conversion
        if "Operador" in df.columns:
            df["Operador"] = df["Operador"].apply(match_operator)
            steps_done.append("✅ Operador values mapped to numeric codes.")
        else:
            steps_done.append("⚠️ Column 'Operador' not found.")

        # Turno
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].astype(str).str.lower()
            df["Turno"] = df["Turno"].replace({"dia": 1, "día": 1, "noche": 2})
            steps_done.append("✅ Turno values mapped: Día → 1, Noche → 2")

        # Xpansion & Nivel extraction
        def extract_blast(text):
            text = str(text).upper()
            xp = re.search(r"F0*(\d+)", text)
            lvl = re.search(r"B0*(\d{3,4})", text)
            return xp.group(1) if xp else None, lvl.group(1) if lvl else None

        if "Banco" in df.columns:
            blast = df["Banco"].apply(extract_blast)
            df["Expansion"] = [x[0] for x in blast]
            df["Nivel"] = pd.to_numeric([x[1] for x in blast], errors="coerce")

            insert_idx = df.columns.get_loc("Banco") + 1
            df.insert(insert_idx, "Nivel", df.pop("Nivel"))
            steps_done.append("✅ Extracted Expansion and Nivel from Banco")

        # Perforadora mapping
        def perf_map(x):
            x = str(x).lower()
            if "pe_01" in x: return 1
            if "pe_02" in x: return 2
            if "pd_02" in x: return 22
            if "trepsa" in x: return 4
            return x

        if "Perforadora" in df.columns:
            df["Perforadora"] = df["Perforadora"].apply(perf_map)
            steps_done.append("✅ Perforadora values normalized.")

        # --------------------------------------------------------------
        # NEW: Cross-fill Plan/Real pairs correctly 
        # --------------------------------------------------------------
        def cross_fill(col_a, col_b):
            if col_a in df.columns and col_b in df.columns:
                before = len(df)
                df[col_a] = pd.to_numeric(df[col_a], errors="coerce")
                df[col_b] = pd.to_numeric(df[col_b], errors="coerce")

                df[col_a] = df[col_a].fillna(df[col_b])
                df[col_b] = df[col_b].fillna(df[col_a])

                deleted = before - len(df)
                return deleted
            return 0

        total_deleted += cross_fill("Este Plan", "Este Real")
        total_deleted += cross_fill("Norte Plan", "Norte Real")

        # Elev Plan + Elev Real using Nivel
        if "Elev Plan" in df.columns and "Elev Real" in df.columns:
            df["Elev Plan"] = pd.to_numeric(df["Elev Plan"], errors="coerce")
            df["Elev Real"] = pd.to_numeric(df["Elev Real"], errors="coerce")

            # First normal cross fill
            df["Elev Plan"] = df["Elev Plan"].fillna(df["Elev Real"])
            df["Elev Real"] = df["Elev Real"].fillna(df["Elev Plan"])

            # Fill remaining from Nivel
            if "Nivel" in df.columns:
                mask = df["Elev Plan"].isna()
                df.loc[mask, "Elev Plan"] = df.loc[mask, "Nivel"]

                mask = df["Elev Real"].isna()
                df.loc[mask, "Elev Real"] = df.loc[mask, "Nivel"]

            # Delete if both empty
            before = len(df)
            df = df.dropna(subset=["Elev Plan", "Elev Real"], how="all")
            total_deleted += before - len(df)
            steps_done.append("🛠 Elev columns filled using Nivel support.")

        # Profundidad cross fill
        if "Profundidad Objetivo" in df.columns and "Profundidad Real" in df.columns:
            df["Profundidad Objetivo"] = pd.to_numeric(df["Profundidad Objetivo"], errors="coerce")
            df["Profundidad Real"] = pd.to_numeric(df["Profundidad Real"], errors="coerce")

            df["Profundidad Objetivo"] = df["Profundidad Objetivo"].fillna(df["Profundidad Real"])
            df["Profundidad Real"] = df["Profundidad Real"].fillna(df["Profundidad Objetivo"])

            before = len(df)
            df = df.dropna(subset=["Profundidad Objetivo", "Profundidad Real"], how="all")
            total_deleted += before - len(df)
            steps_done.append("🛠 Fixed Profundidad Objetivo/Real by cross-fill.")

        steps_done.append(f"📉 Total rows removed during Plan/Real cleanup: {total_deleted}")

        # Show steps
        for step in steps_done:
            st.markdown(
                f"<div style='background:#e5ffee;padding:8px;border-radius:6px;margin-bottom:6px;'>{step}</div>",
                unsafe_allow_html=True
            )

    # ==========================================================
    # RESULTS DISPLAY
    # ==========================================================
    st.markdown("---")
    st.subheader("📌 Cleaned Output Preview")
    st.dataframe(df.head(20), use_container_width=True)
    st.success(f"📊 Final dataset: {len(df)} rows × {len(df.columns)} columns")

    # ==========================================================
    # EXPORT
    # ==========================================================
    st.markdown("---")
    export = st.radio("Save:", ["All columns", "Select columns"])

    if export == "Select columns":
        cols = st.multiselect("Choose columns:", df.columns, default=list(df.columns))
        df_export = df[cols]
    else:
        df_export = df

    excel = io.BytesIO()
    df_export.to_excel(excel, index=False, engine="openpyxl")
    excel.seek(0)

    st.download_button("📥 Download Excel", excel, file_name="DGM_Autonomia_Cleaned.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)

else:
    st.info("📂 Upload a file to begin.")





