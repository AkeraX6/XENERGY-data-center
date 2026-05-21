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
        def extract_expansion_nivel(text):
            if pd.isna(text):
                return None, None
            text = str(text).upper()
            # Extract expansion from F## pattern (e.g., F12 → 12, F12W → 12, F07B → 7)
            xp_match = re.search(r"F0*(\d+)", text)
            expansion = int(xp_match.group(1)) if xp_match else None
            
            nivel = None
            nv_match = re.search(r"B0*(\d{3,4})", text)
            if nv_match:
                nivel = int(nv_match.group(1))
            else:
                nv_match = re.search(r"[_\-](2\d{3}|3\d{3}|4\d{3})[_\-]", text)
                if nv_match:
                    nivel = int(nv_match.group(1))
            return expansion, nivel

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
            if "pe_03" in val or "pe03" in val:
                return 3
            if "trepsa" in val:
                return 4
            return value

        # ---------- Cross-fill Plan/Real columns ----------
        def crossfill_columns(df, plan_names, real_names):
            """
            Cross-fill between Plan and Real columns.
            - If Plan is empty, copy from Real
            - If Real is empty, copy from Plan  
            - If both are empty, mark for deletion
            Returns: (df, plan_col_used, real_col_used) or (df, None, None) if not found
            """
            # Find the actual Plan column name in the dataframe
            plan_col = None
            for name in plan_names:
                if name in df.columns:
                    plan_col = name
                    break
            
            # Find the actual Real column name in the dataframe
            real_col = None
            for name in real_names:
                if name in df.columns:
                    real_col = name
                    break
            
            if plan_col is None or real_col is None:
                return df, None, None
            
            # Cross-fill row by row
            rows_to_delete = []
            for idx in df.index:
                plan_val = df.at[idx, plan_col]
                real_val = df.at[idx, real_col]
                
                # Check if Plan is empty/invalid
                plan_empty = pd.isna(plan_val) or str(plan_val).strip() == "" or str(plan_val).strip() == "-"
                try:
                    if float(plan_val) == 0:
                        plan_empty = True
                except:
                    pass
                
                # Check if Real is empty/invalid
                real_empty = pd.isna(real_val) or str(real_val).strip() == "" or str(real_val).strip() == "-"
                try:
                    if float(real_val) == 0:
                        real_empty = True
                except:
                    pass
                
                # Cross-fill logic
                if plan_empty and not real_empty:
                    df.at[idx, plan_col] = real_val  # Copy Real to Plan
                elif real_empty and not plan_empty:
                    df.at[idx, real_col] = plan_val  # Copy Plan to Real
                elif plan_empty and real_empty:
                    rows_to_delete.append(idx)  # Both empty, mark for deletion
            
            # Delete rows where both are empty
            if rows_to_delete:
                df = df.drop(rows_to_delete)
            
            return df, plan_col, real_col

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
            expansions, nivels = zip(*df["Banco"].apply(extract_expansion_nivel))
            insert_idx = df.columns.get_loc("Banco") + 1
            df.insert(insert_idx, "Expansion", expansions)
            df.insert(insert_idx + 1, "Nivel", nivels)
            steps_done.append("✅ Extracted Expansion and Nivel columns from Banco.")

        if "Perforadora" in df.columns:
            df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
            steps_done.append("✅ Standardized Perforadora names and numeric codes.")

        # ---------- Cross-fill Este, Norte, Elev columns ----------
        rows_before = len(df)
        crossfill_pairs = [
            (["Este Plan", "Este.Plan"], ["Este Real", "Este.Real"]),
            (["Norte Plan", "Norte.Plan"], ["Norte Real", "Norte.Real"]),
            (["Elev Plan", "Elev.Plan"], ["Elev Real", "Elev.Real"]),
        ]
        
        pairs_processed = []
        for plan_names, real_names in crossfill_pairs:
            df, plan_used, real_used = crossfill_columns(df, plan_names, real_names)
            if plan_used and real_used:
                pairs_processed.append(f"{plan_used} ↔ {real_used}")
        
        rows_after = len(df)
        rows_deleted = rows_before - rows_after
        
        if pairs_processed:
            steps_done.append(f"✅ Cross-filled: {', '.join(pairs_processed)}. Deleted {rows_deleted} rows with empty coordinates.")
        else:
            steps_done.append("⚠️ No Plan/Real column pairs found for cross-filling.")

        # ---------- Fix Elev Plan / Elev Real: empty, negative, zero, or under 2000 ----------
        elev_plan_col = next((c for c in ["Elev Plan", "Elev.Plan"] if c in df.columns), None)
        elev_real_col = next((c for c in ["Elev Real", "Elev.Real"] if c in df.columns), None)

        if elev_plan_col and elev_real_col:
            df[elev_plan_col] = pd.to_numeric(df[elev_plan_col], errors="coerce")
            df[elev_real_col] = pd.to_numeric(df[elev_real_col], errors="coerce")
            elev_fixes = 0

            for idx in df.index:
                plan_v = df.at[idx, elev_plan_col]
                real_v = df.at[idx, elev_real_col]

                plan_bad = pd.isna(plan_v) or plan_v <= 0 or plan_v < 2000
                real_bad = pd.isna(real_v) or real_v <= 0

                if plan_bad and not real_bad:
                    df.at[idx, elev_plan_col] = real_v
                    elev_fixes += 1
                if real_bad and not plan_bad:
                    df.at[idx, elev_real_col] = plan_v
                    elev_fixes += 1

            if elev_fixes > 0:
                steps_done.append(f"✅ Fixed {elev_fixes} Elev values (empty/negative/zero/under 2000 replaced from counterpart).")

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

    # TXT export with specific columns in order
    txt_columns = ["Operador", "Expansion", "Perforadora", "Este Plan", "Norte Plan", "Elev Plan", "Tiempo Perforación [hrs]", "Day", "Month", "Year"]
    txt_available_cols = [col for col in txt_columns if col in df.columns]
    txt_df = df[txt_available_cols].copy() if txt_available_cols else df.copy()
    
    # Convert Day, Month, Year to integers (remove .0)
    for col in ["Day", "Month", "Year"]:
        if col in txt_df.columns:
            txt_df[col] = txt_df[col].fillna(0).astype(int)
    
    # Format decimal columns to 2 decimal places
    for col in txt_df.columns:
        if txt_df[col].dtype in ["float64", "float32"]:
            txt_df[col] = txt_df[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    
    txt_buffer = io.StringIO()
    txt_df.to_csv(txt_buffer, index=False, header=False, sep="\t")

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
            "📄 Download TXT File",
            txt_buffer.getvalue(),
            file_name="DGM_Autonomia_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

    # ==========================================================
    # DATA QUALITY CHECK
    # ==========================================================
    st.markdown("---")
    st.subheader("🔍 Data Quality Check")

    # Build the TXT dataframe for quality checking (same columns as TXT export)
    qc_txt_columns = ["Operador", "Expansion", "Perforadora", "Este Plan", "Norte Plan", "Elev Plan", "Tiempo Perforación [hrs]", "Day", "Month", "Year"]
    qc_available_cols = [col for col in qc_txt_columns if col in df.columns]
    qc_df = df[qc_available_cols].copy() if qc_available_cols else df.copy()

    if st.button("▶️ Run Quality Check", use_container_width=True, key="dgm_auto_qc"):
        total_rows = len(qc_df)

        if total_rows == 0:
            st.error("❌ No data to check — the dataset is empty after cleaning.")
        else:
            issues_found = False
            report_lines = []

            for col in qc_df.columns:
                col_issues = []

                empty_count = int(qc_df[col].isna().sum() + (qc_df[col].astype(str).str.strip() == "").sum())
                if empty_count > 0:
                    col_issues.append(f"**{empty_count}** empty value(s)")

                non_empty = qc_df[col].dropna().astype(str).str.strip()
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





