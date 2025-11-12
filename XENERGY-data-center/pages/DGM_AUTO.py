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
    # Robust CSV read (supports ; and ,)
    if file_name.endswith(".csv"):
        try:
            df = pd.read_csv(uploaded_file, sep=";", engine="python")
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, engine="python")
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    # For reporting
    delete_counts = {
        "tiempo_perforacion_empty": 0,
        "pairs_both_empty": 0,
    }
    steps_done = []   # transformations summary (no counts)
    deletes_log = []  # deletions summary (with counts)

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Summary (what the code did)", expanded=False):

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
            """Return (code, reason) with dynamic sequential assignment for new operators."""
            if pd.isna(raw_value) or str(raw_value).strip() == "":
                return 25, "empty→25"

            s_ws = _norm_ws(raw_value)
            s_ns = _nospace(s_ws)
            s_tokens = set(s_ws.split())

            # Exact nospace match
            for rec in _ops_index:
                if s_ns == rec["nospace"]:
                    return rec["code"], "exact-nospace"

            # Token coverage
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

            # Fuzzy fallback
            best = None
            for rec in _ops_index:
                sim = SequenceMatcher(None, s_ns, rec["nospace"]).ratio()
                if best is None or sim > best["sim"]:
                    best = {"code": rec["code"], "sim": sim}
            if best and best["sim"] >= 0.90:
                return best["code"], f"fuzzy({best['sim']:.2f})"

            # Unknown → create new sequential code
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

        # ---------- Expansion & Level from Banco ----------
        def extract_expansion_level(text):
            if pd.isna(text):
                return None, None
            text = str(text).upper()
            xp_match = re.search(r"F0*(\d+)", text)
            expansion = int(xp_match.group(1)) if xp_match else None
            nivel = None
            nv_match = re.search(r"B0*(\d{3,4})", text)
            if nv_match:
                nivel = int(nv_match.group(1))
            else:
                # common 4-digit level between separators
                nv_match = re.search(r"[_\-](2\d{3}|3\d{3}|4\d{3})[_\-]", text)
                if nv_match:
                    nivel = int(nv_match.group(1))
            return expansion, nivel

        # ---------- Perforadora ----------
        def clean_perforadora(value):
            """Only map PE_01→1, PE_02→2, PD_02→22, Trepsa→4. Keep numeric values as-is."""
            if pd.isna(value):
                return value
            val = normalize_text(value)
            if val.isdigit():
                return int(val)  # keep as-is, even 9100 etc.
            if "pe_01" in val or "pe01" in val:
                return 1
            if "pe_02" in val or "pe02" in val:
                return 2
            if "pd_02" in val or "pd02" in val:
                return 22
            if "trepsa" in val:
                return 4
            return value

        # ---------- Cross-fill two columns ----------
        def cross_fill_pair(df_in, col1, col2):
            """Cross-fill between two numeric columns and drop rows if both empty/<=0."""
            def fix_values(a, b):
                a = pd.to_numeric(a, errors="coerce")
                b = pd.to_numeric(b, errors="coerce")
                if pd.isna(a) or a <= 0:
                    a = b
                if pd.isna(b) or b <= 0:
                    b = a
                return a, b

            df_local = df_in.copy()
            filled = df_local[[col1, col2]].apply(lambda r: fix_values(r[col1], r[col2]), axis=1)
            df_local[col1], df_local[col2] = zip(*filled)

            before = len(df_local)
            df_local = df_local.dropna(subset=[col1, col2], how="all")
            removed = before - len(df_local)
            return df_local, removed

        # ---------- Cleaning Starts ----------
        # Remove duplicate/numbered duplicate columns and tidy headers
        df = df.loc[:, ~df.columns.duplicated()]
        df = df.loc[:, ~df.columns.str.contains(r"\.\d+$", regex=True)]
        df.columns = (
            df.columns.astype(str)
            .str.replace(r"[\r\n]+", " ", regex=True)
            .str.replace('"', "", regex=False)
            .str.strip()
        )

        # --- 0) Ensure Tiempo Perforación header is consistent if garbled
        # Fix common corrupted header variants (e.g., "Tiempo PerforaciÃ³n [hrs]")
        for col in df.columns:
            if "tiempo" in col.lower() and "perfor" in col.lower():
                df.rename(columns={col: "Tiempo Perforación [hrs]"}, inplace=True)
                break

        # --- 1) Delete rows with empty "Tiempo Perforación [hrs]"
        if "Tiempo Perforación [hrs]" in df.columns:
            before = len(df)
            df = df.dropna(subset=["Tiempo Perforación [hrs]"])
            removed = before - len(df)
            delete_counts["tiempo_perforacion_empty"] += removed
            steps_done.append("• Deleted rows with empty 'Tiempo Perforación [hrs]'.")
        else:
            steps_done.append("• Column 'Tiempo Perforación [hrs]' not found (no deletion applied).")

        # --- 2) Turno conversion
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].apply(convert_turno)
            steps_done.append("• Converted Turno values (Día→1, Noche→2).")

        # --- 3) Operador mapping (with dynamic new codes)
        if "Operador" in df.columns:
            df["Operador"] = df["Operador"].apply(convert_operador)
            steps_done.append("• Mapped Operador names (added new operators sequentially if needed).")
            # Show newly added operators if any
            if new_operators:
                st.markdown("<b>🆕 New Operators Added:</b>", unsafe_allow_html=True)
                for name, code in new_operators.items():
                    st.markdown(f"- {name} → <span style='color:green;'>Code {code}</span>", unsafe_allow_html=True)

        # --- 4) Banco → Expansion + Nivel (insert right after Banco)
        if "Banco" in df.columns:
            expansions, nivels = zip(*df["Banco"].apply(extract_expansion_level))
            insert_idx = df.columns.get_loc("Banco") + 1
            df.insert(insert_idx, "Expansion", expansions)
            df.insert(insert_idx + 1, "Nivel", nivels)
            steps_done.append("• Extracted Expansion and Nivel from Banco (added next to Banco).")

        # --- 5) Perforadora mapping (keep numerics as-is)
        if "Perforadora" in df.columns:
            df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
            steps_done.append("• Standardized Perforadora (PE_01→1, PE_02→2, PD_02→22, Trepsa→4; numeric kept).")

        # --- 6) Cross-fill Plan/Real pairs and delete rows if both empty
        pairs = [
            ("Este Plan", "Este Real"),
            ("Norte Plan", "Norte Real"),
            ("Elev Plan", "Elev Real"),
            ("Profundidad Objetivo", "Profundidad Real"),
        ]
        total_removed_pairs = 0
        for col1, col2 in pairs:
            if col1 in df.columns and col2 in df.columns:
                df, removed = cross_fill_pair(df, col1, col2)
                total_removed_pairs += removed
        delete_counts["pairs_both_empty"] += total_removed_pairs
        steps_done.append("• Cross-filled Plan/Real pairs (Este, Norte, Elev, Profundidad).")

        # --- Print transformations summary
        st.markdown("### 🛠️ Transformations Applied")
        for step in steps_done:
            st.markdown(
                f"<div style='background:#eef6ff;padding:8px;border-radius:6px;margin-bottom:6px;color:#0b5394;'>{step}</div>",
                unsafe_allow_html=True
            )

        # --- Print deletions summary
        st.markdown("### 🗑️ Rows Deleted (by rule)")
        st.markdown(
            f"<div style='background:#fdeaea;padding:8px;border-radius:6px;margin-bottom:6px;color:#a61b1b;'>"
            f"• Empty 'Tiempo Perforación [hrs]': <b>{delete_counts['tiempo_perforacion_empty']}</b><br>"
            f"• Both values empty in Plan/Real pairs (after cross-fill): <b>{delete_counts['pairs_both_empty']}</b>"
            f"</div>",
            unsafe_allow_html=True
        )
        total_deleted = sum(delete_counts.values())
        st.markdown(
            f"<div style='background:#f0fff0;padding:10px;border-radius:8px;margin-top:6px;color:#0b6b3a;'>"
            f"<b>Total deleted rows: {total_deleted}</b>"
            f"</div>",
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
            "Select columns (click in the order you want):",
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


