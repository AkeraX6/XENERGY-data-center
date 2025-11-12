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

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):

        # ---------- Text Normalization ----------
        def normalize_text(s):
            if pd.isna(s):
                return ""
            s = str(s).strip().lower()
            s = unicodedata.normalize("NFD", s)
            s = s.encode("ascii", "ignore").decode("utf-8")
            return s

        def _norm_ws(text: str) -> str:
            if pd.isna(text):
                return ""
            s = str(text).lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
            s = re.sub(r"[^a-z\s]", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _nospace(s: str) -> str:
            return s.replace(" ", "")

        # ---------- Operator Mapping ----------
        _operator_names = {
            "Alberto Flores": 1, "Alex Nunez": 2, "Carla Vargas": 3, "Carlos Bugueno": 4, "Carlos Medina": 5,
            "Cristian Herrera": 6, "Francisco Pasten": 7, "Freddy Pena": 8, "German Leyton": 9, "German Vidal": 10,
            "Hugo Garcia": 11, "Jhonny Dubo": 12, "Jose Perez": 13, "Juan Gonzalez": 14, "Leonardo Ramirez": 15,
            "Miguel Guamparito": 16, "Oscar Arancibia": 17, "Pamela Ruiz": 18, "Patricio Plaza": 19, "Renan Bugueno": 20,
            "Rodrigo Cataldo": 21, "Sergio Gutierrez": 22, "Trepsa": 23, "Victor Rojas Chavez": 24,
            "Hernan Munoz": 26, "Jose Vallejos": 27, "Jose Villegas": 28, "Marcelo Villegas": 29, "Fabian Gallardo": 30,
            "Humberto Meneses": 32, "Mario Maya": 33, "Mario Rivera": 34, "Mauricio Villegas": 35,
            "Fabian Guerrero": 36, "Ricardo Ortiz": 37,
        }

        _ops_index = []
        for full_name, code in _operator_names.items():
            norm_ws = _norm_ws(full_name)
            tokens = norm_ws.split()
            nospace = _nospace(norm_ws)
            _ops_index.append({
                "code": code,
                "full_name": full_name,
                "norm_ws": norm_ws,
                "nospace": nospace,
                "tokens": tokens,
                "ntok": len(tokens),
            })

        new_operators = {}

        def _best_operator_match(raw_value: str):
            if pd.isna(raw_value) or str(raw_value).strip() == "":
                return 25, "empty→25"

            s_ws = _norm_ws(raw_value)
            s_ns = _nospace(s_ws)
            s_tokens = set(s_ws.split())

            for rec in _ops_index:
                if s_ns == rec["nospace"]:
                    return rec["code"], "exact-nospace"

            best = None
            for rec in _ops_index:
                req = rec["tokens"]
                have = sum(1 for t in req if t in s_tokens)
                need = 2 if rec["ntok"] >= 3 else rec["ntok"]
                if have >= need:
                    cov = have / max(rec["ntok"], 1)
                    sim = SequenceMatcher(None, s_ns, rec["nospace"]).ratio()
                    score = 0.7 * cov + 0.3 * sim
                    if best is None or score > best["score"]:
                        best = {"code": rec["code"], "score": score}

            if best and best["score"] >= 0.80:
                return best["code"], "token-cover"

            best = None
            for rec in _ops_index:
                sim = SequenceMatcher(None, s_ns, rec["nospace"]).ratio()
                if best is None or sim > best["sim"]:
                    best = {"code": rec["code"], "sim": sim}
            if best and best["sim"] >= 0.90:
                return best["code"], f"fuzzy({best['sim']:.2f})"

            if not hasattr(_best_operator_match, "next_code"):
                _best_operator_match.next_code = max(_operator_names.values()) + 1

            new_code = _best_operator_match.next_code
            _best_operator_match.next_code += 1
            new_operators[raw_value] = new_code
            _operator_names[raw_value] = new_code
            return new_code, "new-operator"

        def convert_operador(value):
            code, _ = _best_operator_match(value)
            return code

        # ---------- Turno ----------
        def convert_turno(value):
            if pd.isna(value):
                return value
            val = str(value).strip().lower()
            if "dia" in val or "día" in val:
                return 1
            elif "noche" in val:
                return 2
            return value

        # ---------- Expansion & Nivel ----------
        def extract_xpansion_nivel(text):
            if pd.isna(text):
                return None, None
            text = str(text).upper()
            xp_match = re.search(r"F0*(\d+)", text)
            xpansion = int(xp_match.group(1)) if xp_match else None
            nivel = None
            nv_match = re.search(r"B0*(\d{3,4})", text)
            if nv_match:
                nivel = int(nv_match.group(1))
            else:
                nv_match = re.search(r"[_\-](2\d{3}|3\d{3}|4\d{3})[_\-]", text)
                if nv_match:
                    nivel = int(nv_match.group(1))
            return xpansion, nivel

        # ---------- Perforadora ----------
        def clean_perforadora(value):
            if pd.isna(value):
                return value
            val = normalize_text(value)
            if val.isdigit():
                return int(val)
            if "pe_01" in val or "pe01" in val:
                return 1
            if "pe_02" in val or "pe02" in val:
                return 2
            if "pd_02" in val or "pd02" in val:
                return 22
            if "trepsa" in val:
                return 4
            return value

        # ---------- Pair Cleaning ----------
        def clean_pair(df, col1, col2):
            def replace_vals(a, b):
                try:
                    a = float(a)
                except:
                    a = None
                try:
                    b = float(b)
                except:
                    b = None
                if a is None or a <= 0:
                    a = b
                if b is None or b <= 0:
                    b = a
                return a, b

            new1, new2 = zip(*[replace_vals(a, b) for a, b in zip(df[col1], df[col2])])
            df[col1], df[col2] = new1, new2
            df = df.dropna(subset=[col1, col2], how="all")
            return df

        # ---------- Cleaning Starts ----------
        df = df.loc[:, ~df.columns.duplicated()]
        df = df.loc[:, ~df.columns.str.contains(r"\.1$|\.2$|\.3$", regex=True)]

        # Delete rows with empty "Tiempo Perforación [hrs]"
        if "Tiempo Perforación [hrs]" in df.columns:
            before = len(df)
            df = df.dropna(subset=["Tiempo Perforación [hrs]"])
            after = len(df)
            steps_done.append(f"✅ Removed {before - after} rows with empty 'Tiempo Perforación [hrs]'.")

        # Turno conversion
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].apply(convert_turno)
            steps_done.append("✅ Turno values converted (Día→1, Noche→2).")

        # Operador mapping
        if "Operador" in df.columns:
            df["Operador"] = df["Operador"].apply(convert_operador)
            steps_done.append("✅ Operador names mapped and new ones assigned sequentially.")

        # Banco → Expansion + Nivel
        if "Banco" in df.columns:
            xpansions, nivels = zip(*df["Banco"].apply(extract_xpansion_nivel))
            insert_idx = df.columns.get_loc("Banco") + 1
            df.insert(insert_idx, "Xpansion", xpansions)
            df.insert(insert_idx + 1, "Nivel", nivels)
            steps_done.append("✅ Extracted Xpansion and Nivel columns from Banco.")

        # Perforadora cleaning
        if "Perforadora" in df.columns:
            df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
            steps_done.append("✅ Cleaned Perforadora: PE_01→1, PE_02→2, PD_02→22, Trepsa→4.")

        # Pair columns
        pairs = [
            ("Este Plan", "Este Real"),
            ("Norte Plan", "Norte Real"),
            ("Elev Plan", "Elev Real"),
            ("Profundidad Objetivo", "Profundidad Real"),
        ]
        count_pairs = 0
        for col1, col2 in pairs:
            if col1 in df.columns and col2 in df.columns:
                df = clean_pair(df, col1, col2)
                count_pairs += 1
        steps_done.append(f"✅ Cross-filled {count_pairs} Plan/Real column pairs.")

        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

    # ==========================================================
    # AFTER CLEANING — RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(15), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
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

    excel_buffer = io.BytesIO()
    export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    csv_buffer = io.StringIO()
    export_df.to_csv(csv_buffer, index=False, sep=";")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name="DGM_Autonomia_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="DGM_Autonomia_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload a file to begin.")





