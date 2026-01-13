import streamlit as st
import pandas as pd
import re
import io
from difflib import SequenceMatcher
from unicodedata import normalize

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
# HELPER FUNCTIONS FOR OPERATOR MATCHING
# ==================================================
def strip_accents_lower_spaces(s):
    """Remove accents and convert to lowercase."""
    if pd.isna(s):
        return ""
    s = str(s).strip()
    s = normalize("NFD", s)
    s = "".join(c for c in s if normalize("NFD", c)[0] == c)
    return s.lower()

def nospace(s):
    """Remove spaces."""
    return s.replace(" ", "")

def clean_modelo(val):
    """
    Transform Modelo column with these mappings (ignoring case, spaces, special chars):
    TNXXX=10XXX
    TMGXXX=100XXX
    TMXXX=10XXX
    XXXM=20XXX
    MXXX=20XXX
    GSXXX=300XXX
    XXXGS=300XXX
    GXXX=30XXX
    XXXTH=400XXX
    THXXX=400XXX
    XXXR=50XXX
    RXXX=50XXX
    XXXTM=10XXX
    XXXTN=10XXX
    XXXG=30XXX
    XXXTMG=100XXX
    """
    if pd.isna(val) or str(val).strip() == "":
        return None
    
    # Normalize: remove spaces, uppercase, remove special chars except letters/digits
    s = str(val).strip().upper().replace(" ", "")
    s = re.sub(r"[^A-Z0-9]", "", s)
    
    if not s:
        return None
    
    # Extract the numeric part
    digits = re.findall(r"\d+", s)
    if not digits:
        return None
    
    numeric_part = digits[0]
    
    # Check prefixes first (order matters - more specific first)
    if s.startswith("TMG"):
        return f"100{numeric_part}"
    elif s.startswith("TM"):
        return f"10{numeric_part}"
    elif s.startswith("TN"):
        return f"10{numeric_part}"
    elif s.startswith("GS"):
        return f"300{numeric_part}"
    elif s.startswith("G"):
        return f"30{numeric_part}"
    elif s.startswith("TH"):
        return f"400{numeric_part}"
    elif s.startswith("M"):
        return f"20{numeric_part}"
    elif s.startswith("R"):
        return f"50{numeric_part}"
    # Check suffixes (order matters - more specific first)
    elif s.endswith("TMG"):
        return f"100{numeric_part}"
    elif s.endswith("TM"):
        return f"10{numeric_part}"
    elif s.endswith("TN"):
        return f"10{numeric_part}"
    elif s.endswith("GS"):
        return f"300{numeric_part}"
    elif s.endswith("G"):
        return f"30{numeric_part}"
    elif s.endswith("TH"):
        return f"400{numeric_part}"
    elif s.endswith("M"):
        return f"20{numeric_part}"
    elif s.endswith("R"):
        return f"50{numeric_part}"
    else:
        # If no pattern matches, return numeric part as-is
        return numeric_part

# ==================================================
# FILE UPLOAD — DATA AND OPERATORS
# ==================================================
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader("📤 Upload your Excel file (Data)", type=["xlsx", "xls", "csv"])

with col2:
    st.markdown("**Operator Mapping:**")
    operator_mapping_file = st.file_uploader("📋 Upload operator mapping (optional)", type=["xlsx", "xls", "csv"], key="operator_map")

# Initialize operator index
ops_index = []
new_ops_norm_to_code = {}
next_code = 100
new_operators_found = []

if operator_mapping_file is not None:
    try:
        if operator_mapping_file.name.endswith(".csv"):
            ops_df = pd.read_csv(operator_mapping_file)
        else:
            ops_df = pd.read_excel(operator_mapping_file)
        
        # Assuming columns: "name" and "code"
        for idx, row in ops_df.iterrows():
            name = str(row.get("name", "")).strip()
            code = int(row.get("code", 0))
            if name and code:
                s_ws = strip_accents_lower_spaces(name)
                s_ns = nospace(s_ws)
                s_tokens = set(s_ws.split())
                ops_index.append({
                    "name": name,
                    "code": code,
                    "ws": s_ws,
                    "ns": s_ns,
                    "tokens": s_tokens,
                    "ntok": len(s_tokens)
                })
    except Exception as e:
        st.warning(f"⚠️ Could not read operator mapping file: {e}")

if uploaded_file is not None:
    # --- READ FILE ---
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
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
        # STEP 1 – Remove rows with empty Coord X/Y
        if "Coord X" in df.columns and "Coord Y" in df.columns:
            before = len(df)
            df = df.dropna(subset=["Coord X", "Coord Y"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows missing both Coord X and Coord Y")
        else:
            steps_done.append("⚠️ Missing Coord X or Coord Y columns")

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
                "G_4": 4, "G4": 4,
                "G_2": 2, "G2": 2,
                "G_1": 1, "G1": 1,
                "G_3": 3, "G3": 3
            })
            steps_done.append("✅ Grupo values standardized (G_4→4, G_2→2, G_1→1, G_3→3)")
        else:
            steps_done.append("⚠️ Column 'Grupo' not found")

        # STEP 4 – Replace Turno values
        if "Turno" in df.columns:
            df["Turno"] = df["Turno"].astype(str).str.upper().replace({"TA": 1, "TB": 2})
            steps_done.append("✅ Turno values converted (TA→1, TB→2)")
        else:
            steps_done.append("⚠️ Column 'Turno' not found")

        # STEP 5 – Extract numeric part from Fase (remove F prefix)
        if "Fase" in df.columns:
            df["Fase"] = df["Fase"].astype(str).str.upper().str.replace("F", "", regex=False).str.extract(r"(\d+)", expand=False)
            steps_done.append("✅ Extracted numeric part from Fase (F17→17, F20→20, etc.)")
        else:
            steps_done.append("⚠️ Column 'Fase' not found")

        # STEP 6 – Map Tipo Pozo categories
        if "Tipo Pozo" in df.columns:
            def map_tipo_pozo(val):
                val_lower = str(val).lower().strip()
                if "produccion" in val_lower:
                    return 1
                elif "buffer" in val_lower:
                    return 2
                elif any(x in val_lower for x in ["aux", "auxiliar", "relleno", "repaso", "alargue", "hundimiento"]):
                    return 3
                return val
            df["Tipo Pozo"] = df["Tipo Pozo"].apply(map_tipo_pozo)
            steps_done.append("✅ Tipo Pozo mapped (Produccion→1, Buffer→2, aux/Auxiliar/relleno/repaso/alargue/hundimiento→3)")
        else:
            steps_done.append("⚠️ Column 'Tipo Pozo' not found")

        # STEP 7 – Clean Perforadora column (remove 85 prefix, keep last 2 digits, remove leading 0)
        if "Perforadora" in df.columns:
            def clean_perforadora(val):
                if pd.isna(val) or str(val).strip() == "":
                    return None
                val = str(val).strip()
                # Remove 85 prefix if present
                if val.startswith("85"):
                    val = val[2:]
                # Convert to int to remove leading zeros, then back to string
                try:
                    return str(int(val))
                except:
                    return None

            df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
            steps_done.append("✅ Cleaned Perforadora values (8504→4, 8510→10, 8514→14, etc.)")
        else:
            steps_done.append("⚠️ Column 'Perforadora' not found")

        # STEP 8 – Transform Modelo column with prefix/suffix mappings
        if "Modelo" in df.columns:
            df["Modelo"] = df["Modelo"].apply(clean_modelo)
            steps_done.append("✅ Transformed Modelo values (TMG74→10074, TN55→1055, M32→2032, etc.)")
        else:
            steps_done.append("⚠️ Column 'Modelo' not found")

        # STEP 8b – Fill empty Modelo values by matching Fecha + N° Tricono
        if "Modelo" in df.columns and "Fecha" in df.columns and "N° Tricono" in df.columns:
            empty_count = df["Modelo"].isna().sum()
            if empty_count > 0:
                # Create a reference dict: (Fecha, N° Tricono) -> Modelo
                modelo_ref = {}
                for idx, row in df.iterrows():
                    if pd.notna(row["Modelo"]) and pd.notna(row["Fecha"]) and pd.notna(row["N° Tricono"]):
                        key = (str(row["Fecha"]).strip(), str(row["N° Tricono"]).strip())
                        if key not in modelo_ref:
                            modelo_ref[key] = row["Modelo"]
                
                # Fill empty Modelo values
                filled_count = 0
                for idx, row in df.iterrows():
                    if pd.isna(row["Modelo"]) and pd.notna(row["Fecha"]) and pd.notna(row["N° Tricono"]):
                        key = (str(row["Fecha"]).strip(), str(row["N° Tricono"]).strip())
                        if key in modelo_ref:
                            df.at[idx, "Modelo"] = modelo_ref[key]
                            filled_count += 1
                
                steps_done.append(f"✅ Filled {filled_count} empty Modelo values using Fecha + N° Tricono matching")
            else:
                steps_done.append("ℹ️ No empty Modelo values to fill")
        else:
            steps_done.append("⚠️ Cannot fill Modelo: missing Modelo, Fecha, or N° Tricono columns")

        # STEP 9 – Map Operador names to IDs (with custom mapping or auto-detection)
        if "Operador" in df.columns:
            def best_operator_code_assign(raw_value: str):
                global next_code
                if pd.isna(raw_value) or str(raw_value).strip() == "":
                    return 25, "empty→25"

                s_ws = strip_accents_lower_spaces(raw_value)
                s_ns = nospace(s_ws)
                s_tokens = set(s_ws.split())

                # 1️⃣ Exact nospace match
                for rec in ops_index:
                    if s_ns == rec["ns"]:
                        return rec["code"], "exact-nospace"

                # 2️⃣ Token coverage + similarity
                best = None
                for rec in ops_index:
                    have = sum(1 for t in rec["tokens"] if t in s_tokens)
                    need = 2 if rec["ntok"] >= 3 else rec["ntok"]
                    if have >= need:
                        cov = have / max(rec["ntok"], 1)
                        sim = SequenceMatcher(None, s_ns, rec["ns"]).ratio()
                        score = 0.7 * cov + 0.3 * sim
                        if best is None or score > best["score"]:
                            best = {"code": rec["code"], "score": score}
                if best and best["score"] >= 0.80:
                    return best["code"], "token-cover"

                # 3️⃣ Fuzzy fallback
                best = None
                for rec in ops_index:
                    sim = SequenceMatcher(None, s_ns, rec["ns"]).ratio()
                    if best is None or sim > best["sim"]:
                        best = {"code": rec["code"], "sim": sim}
                if best and best["sim"] >= 0.90:
                    return best["code"], f"fuzzy({best['sim']:.2f})"

                # 4️⃣ Unknown → assign new sequential code
                if s_ns in new_ops_norm_to_code:
                    return new_ops_norm_to_code[s_ns], "new-reuse"

                new_code = next_code
                next_code += 1
                new_ops_norm_to_code[s_ns] = new_code
                new_operators_found.append({"name": raw_value, "code": new_code})
                return new_code, "new-assign"

            df["Operador"] = df["Operador"].apply(lambda x: best_operator_code_assign(x)[0])
            
            # Show new operators found
            if new_operators_found:
                steps_done.append(f"✅ Operador mapping applied; {len(new_operators_found)} new operators assigned")
            else:
                steps_done.append("✅ Operador mapping applied")
        else:
            steps_done.append("⚠️ Column 'Operador' not found")
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )
    
    # Display new operators if any were found
    if new_operators_found:
        with st.expander("📋 New Operators Detected", expanded=True):
            new_ops_df = pd.DataFrame(new_operators_found)
            st.dataframe(new_ops_df, use_container_width=True)

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

    col1, col2, col3 = st.columns(3)
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
    
    # Download new operators mapping if new operators were found
    if new_operators_found:
        with col3:
            new_ops_df = pd.DataFrame(new_operators_found)
            new_ops_buffer = io.BytesIO()
            new_ops_df.to_excel(new_ops_buffer, index=False, engine="openpyxl")
            new_ops_buffer.seek(0)
            st.download_button(
                "📋 Download New Operators",
                new_ops_buffer,
                file_name="MB_New_Operators.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam -Omar El Kendi-")

else:
    st.info("📂 Please upload an Excel file to begin.")
