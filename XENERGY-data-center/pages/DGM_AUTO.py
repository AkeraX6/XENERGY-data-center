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
st.subheader("📁 Upload Files")

col_upload1, col_upload2 = st.columns(2)

with col_upload1:
    operators_file = st.file_uploader("📋 Upload Operators File (Excel/CSV)", type=["xlsx", "xls", "csv"], key="operators_upload", help="Required: File with Name/Operador and Code/Codigo columns")

with col_upload2:
    uploaded_file = st.file_uploader("📤 Upload Data File (Excel/CSV)", type=["xlsx", "xls", "csv"], key="data_upload")

# ==========================================================
# LOAD OPERATORS FROM FILE (REQUIRED)
# ==========================================================
_operator_names = {}

if operators_file is not None:
    try:
        op_file_name = operators_file.name.lower()
        if op_file_name.endswith(".csv"):
            operators_df = pd.read_csv(operators_file)
        else:
            operators_df = pd.read_excel(operators_file)
        
        # Expect columns: Name (or Operador), Code (or Codigo)
        name_col = None
        code_col = None
        
        for col in operators_df.columns:
            col_lower = col.lower().strip()
            if "name" in col_lower or "operador" in col_lower or "nombre" in col_lower:
                name_col = col
            if "code" in col_lower or "codigo" in col_lower or "cod" in col_lower:
                code_col = col
        
        if name_col and code_col:
            for _, row in operators_df.iterrows():
                if pd.notna(row[name_col]) and pd.notna(row[code_col]):
                    _operator_names[str(row[name_col]).strip()] = int(row[code_col])
            st.success(f"✅ Loaded {len(_operator_names)} operators from file.")
        else:
            st.error("❌ Operators file must have Name/Operador and Code/Codigo columns.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Error reading operators file: {e}")
        st.stop()
else:
    st.warning("⚠️ Please upload an Operators file to continue.")

if uploaded_file is not None and _operator_names:
    file_name = uploaded_file.name.lower()
    if file_name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
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
            """Normalize: lowercase, remove accents, keep letters/spaces, collapse spaces."""
            if pd.isna(text):
                return ""
            s = str(text).lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # remove accents
            s = re.sub(r"[^a-z\s]", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _nospace(s: str) -> str:
            return s.replace(" ", "")

        # ---------- Operator Index (built from loaded _operator_names) ----------
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

        # ---------- Operator Matching ----------
        def _best_operator_match(raw_value: str):
            """Return (code, reason) with dynamic sequential assignment for new operators."""
            if pd.isna(raw_value) or str(raw_value).strip() == "":
                return 25, "empty→25"

            s_ws = _norm_ws(raw_value)
            s_ns = _nospace(s_ws)
            s_tokens = set(s_ws.split())

            # 1️⃣ Exact nospace match (accent-insensitive)
            for rec in _ops_index:
                if s_ns == rec["nospace"]:
                    return rec["code"], "exact-nospace"

            # 2️⃣ Token coverage
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

            # 3️⃣ Fuzzy fallback (small typos)
            best = None
            for rec in _ops_index:
                sim = SequenceMatcher(None, s_ns, rec["nospace"]).ratio()
                if best is None or sim > best["sim"]:
                    best = {"code": rec["code"], "sim": sim}
            if best and best["sim"] >= 0.90:
                return best["code"], f"fuzzy({best['sim']:.2f})"

            # 4️⃣ Unknown → create new sequential code
            norm_name = _nospace(s_ws)

            # Prevent duplicates (Raul ≈ Raúl)
            for known in new_operators.keys():
                if SequenceMatcher(None, norm_name, _nospace(_norm_ws(known))).ratio() >= 0.95:
                    return new_operators[known], "duplicate-new"

            # Persistent counter for sequential numbering
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
                num = int(val)
                if 9000 <= num <= 9300:
                    return 9273
                return num
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

        df.columns = (
            df.columns.astype(str)
            .str.replace(r"[\r\n]+", " ", regex=True)
            .str.replace('"', "", regex=False)
            .str.strip()
        )

        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].apply(convert_turno)
            steps_done.append("✅ Turno values converted (Día→1, Noche→2).")

        if "Operador" in df.columns:
            df["Operador"] = df["Operador"].apply(convert_operador)
            steps_done.append("✅ Operador names mapped and new ones assigned sequentially.")

            # --- Display newly found operators
            if new_operators:
                st.markdown("<h4 style='color:#d97706;'>🆕 New Operators Added During Processing</h4>", unsafe_allow_html=True)
                for name, code in new_operators.items():
                    st.markdown(f"<b>{name}</b> → <span style='color:green;'>Code {code}</span>", unsafe_allow_html=True)
            else:
                st.info("✅ No new operators found — all matched existing records.")

        if "Banco" in df.columns:
            xpansions, nivels = zip(*df["Banco"].apply(extract_xpansion_nivel))
            insert_idx = df.columns.get_loc("Banco") + 1
            df.insert(insert_idx, "Xpansion", xpansions)
            df.insert(insert_idx + 1, "Nivel", nivels)
            steps_done.append("✅ Extracted Xpansion and Nivel columns from Banco.")

        if "Perforadora" in df.columns:
            df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
            steps_done.append("✅ Standardized Perforadora names and numeric codes.")

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

        # ---------- Extract Day, Month, Year from Dia ----------
        if "Dia" in df.columns:
            df["Dia"] = pd.to_datetime(df["Dia"], errors="coerce")
            df["Day"] = df["Dia"].dt.day
            df["Month"] = df["Dia"].dt.month
            df["Year"] = df["Dia"].dt.year
            steps_done.append("✅ Extracted Day, Month, and Year columns from 'Dia'.")
        else:
            steps_done.append("⚠️ Column 'Dia' not found for date extraction.")

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

    # TXT export with specific columns in order
    txt_columns = ["Operador", "Expansion", "Perforadora", "Este Plan", "Norte Plan", "Elev Plan", "Tiempo Perforación [hrs]", "Day", "Month", "Year"]
    txt_available_cols = [col for col in txt_columns if col in df.columns]
    txt_df = df[txt_available_cols] if txt_available_cols else df
    txt_buffer = io.StringIO()
    txt_df.to_csv(txt_buffer, index=False, sep="\t")

    col1, col2, col3 = st.columns(3)
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
    with col3:
        st.download_button(
            "📄 Download TXT File",
            txt_buffer.getvalue(),
            file_name="DGM_Autonomia_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

    # ==========================================================
    # DOWNLOAD UPDATED OPERATORS FILE (if new operators found)
    # ==========================================================
    if new_operators:
        st.markdown("---")
        st.subheader("👥 Download Updated Operators File")
        st.info(f"📋 {len(new_operators)} new operator(s) were added during processing.")
        
        # Create updated operators dataframe
        updated_ops_data = {"Operador": [], "Codigo": []}
        for name, code in _operator_names.items():
            updated_ops_data["Operador"].append(name)
            updated_ops_data["Codigo"].append(code)
        
        updated_ops_df = pd.DataFrame(updated_ops_data)
        updated_ops_df = updated_ops_df.sort_values("Codigo").reset_index(drop=True)
        
        # Prepare Excel buffer for operators
        ops_excel_buffer = io.BytesIO()
        updated_ops_df.to_excel(ops_excel_buffer, index=False, engine="openpyxl")
        ops_excel_buffer.seek(0)
        
        st.download_button(
            "👥 Download Updated Operators (Excel)",
            ops_excel_buffer,
            file_name="DGM_Operators_Updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload a file to begin.")








