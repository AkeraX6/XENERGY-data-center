import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import SequenceMatcher
import os

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown("<h2 style='text-align:center;'>Escondida — Autonomía Data Cleaner</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:gray;'>Automatic transformation and validation of drilling autonomy data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        # Read file
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        steps_done = []

        # ==========================================================
        # CLEANING & TRANSFORMATION STEPS
        # ==========================================================
        with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

            # STEP 1 — BASE TRANSFORMATIONS
            df["Perforadora"] = df["Perforadora"].astype(str).str.extract(r"(\d+)$")
            df["Perforadora"] = pd.to_numeric(df["Perforadora"], errors="coerce").astype("Int64")
            df["turno (dia o noche)"] = df["turno (dia o noche)"].replace({"Dia": 1, "Noche": 2})
            df["Coordinacion"] = df["Coordinacion"].replace({"A": 1, "B": 2, "C": 3, "D": 4})
            steps_done.append("✅ Normalized Perforadora, Turno, and Coordinacion columns.")

            # STEP 2 — MALLA SPLIT (Banco, Expansion, MallaID)
            if "Malla" in df.columns:
                m = df["Malla"].astype(str).str.split("-", expand=True)
                banco = m[0].str.replace(r"[^0-9]", "", regex=True).str[:4]
                expansion = m[1].str.replace(r"[^0-9]", "", regex=True) if m.shape[1] > 1 else pd.NA
                mallaid = m[2].str.replace(r"[^0-9]", "", regex=True).str[-4:] if m.shape[1] > 2 else pd.NA

                df["Malla"] = mallaid
                df.rename(columns={"Malla": "MallaID"}, inplace=True)
                idx = df.columns.get_loc("MallaID")
                df.insert(idx, "Banco", banco)
                df.insert(idx + 1, "Expansion", expansion)
                steps_done.append("✅ Extracted Banco, Expansion, and MallaID (letters removed).")
            else:
                steps_done.append("⚠️ Column 'Malla' not found — skipped Banco/Expansion/MallaID extraction.")

            # STEP 3 — POZO CLEANING
            if "Pozo" in df.columns:
                before_rows = len(df)

                def transform_pozo(val):
                    val = str(val).strip()
                    if val.startswith("Aux"): return None
                    if val.startswith("B"): return "100000" + val[1:]
                    if val.startswith("C"): return "200000" + val[1:]
                    if val.startswith("D"): return val[1:]
                    return val

                df["Pozo"] = df["Pozo"].apply(transform_pozo)
                df = df[~df["Pozo"].astype(str).str.contains("aux", case=False, na=False)]
                df["Pozo_num"] = pd.to_numeric(df["Pozo"], errors="coerce")
                df = df[df["Pozo_num"].notna() & (df["Pozo_num"] > 0)]
                df["Pozo"] = df["Pozo_num"].astype(int)
                df.drop(columns=["Pozo_num"], inplace=True)
                steps_done.append(f"✅ Cleaned Pozo (removed {before_rows - len(df)} invalid rows).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # STEP 4 — COORDINATE CLEANING
            before_rows = len(df)
            if "Banco" not in df.columns:
                df["Banco"] = pd.NA

            def cross_fill(a, b):
                a.fillna(b, inplace=True)
                b.fillna(a, inplace=True)

            # X
            if {"Coordenadas diseño X", "Coordenada real inicioX"}.issubset(df.columns):
                cross_fill(df["Coordenadas diseño X"], df["Coordenada real inicioX"])
                df = df[(df["Coordenadas diseño X"] >= 100000) & (df["Coordenada real inicioX"] >= 100000)]
            # Y
            if {"Coordenadas diseño Y", "Coordenada real inicio Y"}.issubset(df.columns):
                cross_fill(df["Coordenadas diseño Y"], df["Coordenada real inicio Y"])
            # Z
            if {"Coordenadas diseño Z", "Coordena real inicio Z"}.issubset(df.columns):
                cross_fill(df["Coordenadas diseño Z"], df["Coordena real inicio Z"])
                both_empty = df["Coordenadas diseño Z"].isna() & df["Coordena real inicio Z"].isna()
                df.loc[both_empty, "Coordenadas diseño Z"] = pd.to_numeric(df.loc[both_empty, "Banco"], errors="coerce") + 15
                df.loc[both_empty, "Coordena real inicio Z"] = df.loc[both_empty, "Coordenadas diseño Z"]

            # Remove negatives
            for col in ["Coordenadas diseño X", "Coordenadas diseño Y", "Coordenadas diseño Z",
                        "Coordenada real inicioX", "Coordenada real inicio Y", "Coordena real inicio Z"]:
                if col in df.columns:
                    df = df[df[col] >= 0]

            steps_done.append(f"✅ Cleaned Coordinates (removed {before_rows - len(df)} invalid rows).")

            # STEP 5 — DRILLING PARAMETERS
            rules = {
                "Dureza": {"fill_zero": True, "delete_zero": False},
                "RPM de perforacion": {"fill_zero": True, "delete_zero": False},
                "Velocidad de penetracion (m/minutos)": {"fill_zero": False, "delete_zero": True},
                "Pulldown KN": {"fill_zero": False, "delete_zero": True},
            }

            before = len(df)
            for col, rule in rules.items():
                if col not in df.columns:
                    steps_done.append(f"⚠️ Column '{col}' not found.")
                    continue
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if rule["fill_zero"]:
                    df[col].fillna(0, inplace=True)
                if rule["delete_zero"]:
                    df = df[df[col].notna() & (df[col] != 0)]

            steps_done.append(f"✅ Cleaned drilling parameters (removed {before - len(df)} invalid rows).")

            # STEP 6 — LARGO DE POZO REAL
            if "Largo de pozo real" in df.columns:
                before_len = len(df)
                df["Largo de pozo real"] = pd.to_numeric(df["Largo de pozo real"], errors="coerce")
                df = df[df["Largo de pozo real"].notna() & (df["Largo de pozo real"] > 0)]
                steps_done.append(f"✅ Removed {before_len - len(df)} rows with empty/zero Largo de pozo real.")
            else:
                steps_done.append("⚠️ Column 'Largo de pozo real' not found.")

            # STEP 7 — ESTATUS + CATEGORIA
            if "Estatus de pozo" in df.columns:
                before = len(df)
                df = df[df["Estatus de pozo"].astype(str).str.strip().str.lower() == "drilled"]
                steps_done.append(f"✅ Kept only 'Drilled' status (removed {before - len(df)} rows).")
            if "Categoria de pozo" in df.columns:
                df["Categoria de pozo"] = df["Categoria de pozo"].replace({"Produccion": 1, "Buffer": 2, "Auxiliar": 3})
                steps_done.append("✅ Coded Categoria de pozo (1–3).")

            # STEP 8 — OPERATOR MAPPING
            ops_path = r"XENERGY-data-center/ES_Operators.xlsx"

            def normalize_text(s):
                return re.sub(r"\s+", "", unicodedata.normalize("NFKD", str(s).lower().strip()))

            if os.path.exists(ops_path):
                ops = pd.read_excel(ops_path)
                ops = ops.dropna(subset=["Nombre", "Codigo"])
                operator_map = dict(zip(ops["Nombre"].apply(normalize_text), ops["Codigo"]))
                new_ops = {}

                def best_operator(value):
                    if pd.isna(value) or not str(value).strip():
                        return 75
                    val_norm = normalize_text(value)
                    if val_norm in operator_map:
                        return operator_map[val_norm]
                    # fuzzy
                    best, score = None, 0
                    for k, code in operator_map.items():
                        sim = SequenceMatcher(None, val_norm, k).ratio()
                        if sim > score:
                            best, score = code, sim
                    if score >= 0.85:
                        return best
                    # new operator
                    next_code = max(operator_map.values()) + 1 if operator_map else 100
                    new_ops[value] = next_code
                    operator_map[val_norm] = next_code
                    return next_code

                if "Operador" in df.columns:
                    df["Operador"] = df["Operador"].apply(best_operator)
                    if new_ops:
                        st.info(f"🆕 New operators found ({len(new_ops)}):")
                        st.dataframe(pd.DataFrame(list(new_ops.items()), columns=["Nombre", "Codigo"]), use_container_width=True)
                    steps_done.append("✅ Operator mapping completed.")
                else:
                    steps_done.append("⚠️ Column 'Operador' not found.")
            else:
                steps_done.append(f"⚠️ File not found: {ops_path}")

            # STEP 9 — BROCA MAPPING
            brocas_path = r"XENERGY-data-center/Brocas.xlsx"
            if os.path.exists(brocas_path):
                brocas_df = pd.read_excel(brocas_path).dropna(subset=["Nombre", "Codigo"])
                broca_map = dict(zip(brocas_df["Nombre"].astype(str).str.lower().str.strip(), brocas_df["Codigo"]))

                def match_broca(value):
                    if pd.isna(value) or not str(value).strip():
                        return 0
                    v = str(value).lower().strip()
                    if v in broca_map:
                        return broca_map[v]
                    for k, code in broca_map.items():
                        if k in v or v in k:
                            return code
                    m = re.search(r"(?:s|sj|cn)?(\d{2,3})", v)
                    if m:
                        return int(m.group(1))
                    return 0

                if "Broca" in df.columns:
                    df["Broca"] = df["Broca"].apply(match_broca).astype(int)
                    steps_done.append("✅ Broca references matched using Brocas.xlsx and pattern extraction.")
                else:
                    steps_done.append("⚠️ Column 'Broca' not found.")
            else:
                steps_done.append(f"⚠️ File not found: {brocas_path}")

            # STEP 10 — MODO DE PERFORACION
            if "Modo de perforacion" in df.columns:
                df["Modo de perforacion"] = df["Modo de perforacion"].replace({"Manual": 1, "Autonomous": 2, "Teleremote": 3})
                steps_done.append("✅ Mapped Modo de perforacion (Manual=1, Autonomous=2, Teleremote=3).")

            # Show steps
            for step in steps_done:
                st.markdown(
                    f"<div style='background:#eefaf3;padding:8px 10px;border-radius:6px;margin-bottom:6px;color:#137333;font-weight:500;'>{step}</div>",
                    unsafe_allow_html=True,
                )

        # ==========================================================
        # FINAL OUTPUT
        # ==========================================================
        st.markdown("---")
        st.subheader("✅ Cleaned Data Preview")
        st.dataframe(df.head(20), use_container_width=True)
        st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

        # ==========================================================
        # DOWNLOAD SECTION
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Cleaned File")
        export_df = df

        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)
        csv_buffer = io.StringIO()
        export_df.to_csv(csv_buffer, index=False)

        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📘 Download Excel", excel_buffer, "Escondida_Autonomia_Cleaned.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with c2:
            st.download_button("📗 Download CSV", csv_buffer.getvalue(), "Escondida_Autonomia_Cleaned.csv",
                               mime="text/csv", use_container_width=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam — Omar El Kendi")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")






