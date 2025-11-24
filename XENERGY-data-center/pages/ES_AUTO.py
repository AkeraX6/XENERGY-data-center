import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime

# ==========================================================
# SMALL HELPERS
# ==========================================================

def normalize_text(s: str) -> str:
    """Lowercase, strip, remove accents and collapse spaces."""
    s = str(s).replace("\xa0", " ")
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_header(col: str) -> str:
    """Header normalization: used to match input columns to expected names."""
    return normalize_text(col)

# Canonical column list (what we expect to work with INSIDE the code)
EXPECTED_COLUMNS = [
    "Id", "Perforadora", "ShiftIndex", "tiempo incio de turno", "Tiempo final de turno",
    "turno (dia o noche)", "Coordinacion", "Malla", "Pozo", "tiempo de inicio de ciclo",
    "Tiempo final de ciclo", "Tiempo total de ciclo (en segundos)", "tiempo de inicio de pozo",
    "Tiempo final de pozo", "Tiempo total de pozo (segundos)", "Coordenadas diseño X",
    "Coordenadas diseño Y", "Coordenadas diseño Z", "Coordenada real inicioX",
    "Coordenada real inicio Y", "Coordena real inicio Z", "Coordenada real final X",
    "Coordenada real final Y", "Coordenada real final Z", "GPS calidad", "Dureza",
    "Velocidad de penetracion (m/minutos)", "RPM de perforacion", "Pulldown KN",
    "Largo de pozo planeado", "Largo de pozo real", "Desviacion XY", "Desviacion Z",
    "Desviacion en largo", "Estatus de pozo", "Categoria de pozo", "Operador", "Broca",
    "Tiempo en modo autonomo (segundos)", "Tiempo en modo manual (segundos)",
    "Tiempo en modo teleremoto (segundos)", "Tiempo en modo Switched (segundos)",
    "Tiempo en parada de emergencia (segundos)", "Modo de perforacion",
    "Tiempo en modo configuracion (segundos)", "Tiempo en modo parqueo (segundos)",
    "Tiempo en propulcion (segundos)", "Tiempo en perforacion (segundos)",
    "Tiempo en demora (segundos)", "Velocidad efectiva ciclo (mt/hrs)",
    "Velocidad de penetracion (mts/hrs)"
]

expected_norm_map = {normalize_header(c): c for c in EXPECTED_COLUMNS}

# -------- Pozo transformation helper (case + spaces robust) ----------
def transform_pozo_value(val):
    """Apply B/C/D logic, remove Aux & invalids, return int or None."""
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    s = s.replace(" ", "")  # "b 125" -> "b125"

    # Remove Aux or similar
    if s.startswith("aux"):
        return None

    # Only letters → invalid
    if re.fullmatch(r"[a-z]+", s):
        return None

    # Pattern letter + digits (b002, c120, d15...)
    m = re.match(r"([a-z])(\d+)", s)
    if m:
        letter = m.group(1)
        num = m.group(2)
        if letter == "b":
            return int("100000" + num)
        elif letter == "c":
            return int("200000" + num)
        elif letter == "d":
            return int(num)
        else:
            return int(num)

    # Only digits
    if s.isdigit():
        return int(s)

    # Mixed weird stuff → discard
    return None

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Autonomía Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automatic transformation and validation of drilling autonomy data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOADS
# ==========================================================
uploaded_file = st.file_uploader(
    "📤 Upload Autonomía Excel file",
    type=["xlsx", "xls"],
    key="auto_file"
)

uploaded_ops = st.file_uploader(
    "📤 Upload Operators mapping file (ES_Operators.xlsx)",
    type=["xlsx", "xls"],
    key="ops_file"
)

if uploaded_file is not None:
    try:
        # ---------------- Read main data file ----------------
        df = pd.read_excel(uploaded_file)

        # ---------------- Normalize headers ------------------
        original_cols = list(df.columns)
        rename_map = {}
        for col in original_cols:
            norm = normalize_header(col)
            if norm in expected_norm_map:
                rename_map[col] = expected_norm_map[norm]

        df = df.rename(columns=rename_map)

        steps_done = []

        # Check which expected columns are missing (but do NOT stop)
        normalized_present = {normalize_header(c) for c in df.columns}
        missing = [
            col for col in EXPECTED_COLUMNS
            if normalize_header(col) not in normalized_present
        ]
        if missing:
            steps_done.append(
                "⚠️ Some expected columns are missing or misnamed: " +
                ", ".join(missing)
            )
        else:
            steps_done.append(
                "✅ File column structure validated (ignoring spaces/accents/case)."
            )

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        # ==========================================================
        # CLEANING & TRANSFORMATION STEPS
        # ==========================================================
        with st.expander("⚙️ See Processing Steps", expanded=False):

            # ------------------------------------------------------
            # STEP 1 – Perforadora: keep only numeric value
            # ------------------------------------------------------
            if "Perforadora" in df.columns:
                def parse_perforadora(val):
                    s = str(val)
                    digits = re.findall(r"(\d+)", s)
                    if digits:
                        return int(digits[-1])
                    return pd.NA

                df["Perforadora"] = df["Perforadora"].apply(parse_perforadora)
                steps_done.append("✅ Transformed 'Perforadora' → numeric ID (PE_01 → 1).")
            else:
                steps_done.append("⚠️ Column 'Perforadora' not found.")

            # ------------------------------------------------------
            # STEP 2 – Turno (dia o noche): Dia → 1, Noche → 2 (TurnoNew)
            # ------------------------------------------------------
            if "turno (dia o noche)" in df.columns:
                def map_turno(val):
                    s = str(val).strip().lower()
                    if s.startswith("d"):
                        return 1
                    if s.startswith("n"):
                        return 2
                    return pd.NA

                idx = df.columns.get_loc("turno (dia o noche)")
                df.insert(idx + 1, "TurnoNew", df["turno (dia o noche)"].apply(map_turno))
                steps_done.append("✅ Created 'TurnoNew': Día→1, Noche→2 (original kept).")
            else:
                steps_done.append("⚠️ Column 'turno (dia o noche)' not found.")

            # ------------------------------------------------------
            # STEP 3 – Coordinacion: A=1, B=2, C=3, D=4 (CoordinacionNew)
            # ------------------------------------------------------
            if "Coordinacion" in df.columns:
                def map_coord(val):
                    s = str(val).strip().upper()
                    if s == "A":
                        return 1
                    if s == "B":
                        return 2
                    if s == "C":
                        return 3
                    if s == "D":
                        return 4
                    return pd.NA

                idx = df.columns.get_loc("Coordinacion")
                df.insert(idx + 1, "CoordinacionNew", df["Coordinacion"].apply(map_coord))
                steps_done.append("✅ Created 'CoordinacionNew': A→1, B→2, C→3, D→4 (original kept).")
            else:
                steps_done.append("⚠️ Column 'Coordinacion' not found.")

            # ------------------------------------------------------
            # STEP 4 – Malla → Banco (Level), Expansion, MallaID
            # Format always: 3040-N17B-5018, 3010-S04-6018, etc.
            # ------------------------------------------------------
            if "Malla" in df.columns:
                def parse_malla(text):
                    if pd.isna(text):
                        return (None, None, None)
                    txt = str(text).strip()
                    parts = txt.split("-")

                    # Banco/Level = first 4-digit number anywhere
                    m_level = re.search(r"(\d{4})", txt)
                    banco = int(m_level.group(1)) if m_level else None

                    # Expansion = numeric part of middle segment (N17B → 17, S04 → 4, PL1S → 1)
                    expansion = None
                    if len(parts) >= 2:
                        mid = parts[1]
                        m_exp = re.search(r"(\d{1,2})", mid)
                        if m_exp:
                            expansion = int(m_exp.group(1))

                    # MallaID = last 4-digit number (usually third segment)
                    mallaid = None
                    if len(parts) >= 3:
                        last = parts[-1]
                        m_mid = re.search(r"(\d{4})", last)
                        if m_mid:
                            mallaid = int(m_mid.group(1))
                    else:
                        # fallback: last 4-digit sequence anywhere
                        m_all = re.findall(r"(\d{4})", txt)
                        if m_all:
                            mallaid = int(m_all[-1])

                    return banco, expansion, mallaid

                bancos = []
                expansions = []
                mallaids = []

                for val in df["Malla"]:
                    b, e, mid = parse_malla(val)
                    bancos.append(b)
                    expansions.append(e)
                    mallaids.append(mid)

                # Original Malla preserved; MallaID added
                idx_malla = df.columns.get_loc("Malla")
                df.insert(idx_malla + 1, "Banco", bancos)
                df.insert(idx_malla + 2, "Expansion", expansions)
                df.insert(idx_malla + 3, "MallaID", mallaids)

                steps_done.append("✅ Parsed 'Malla' → Banco(Level), Expansion, MallaID (no separate Grid).")
            else:
                steps_done.append("⚠️ Column 'Malla' not found in the dataset.")

            # ------------------------------------------------------
            # STEP 5 – Pozo: B/C/D logic, remove Aux, letters, <=0
            # ------------------------------------------------------
            if "Pozo" in df.columns:
                before_rows = len(df)

                df["Pozo"] = df["Pozo"].apply(transform_pozo_value)
                df = df[df["Pozo"].notna()]
                df = df[df["Pozo"] > 0]

                deleted_rows = before_rows - len(df)
                steps_done.append(f"✅ Cleaned 'Pozo' with B/C/D logic ({deleted_rows} invalid rows deleted).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # ------------------------------------------------------
            # STEP 6 – Coordinates: cross-fill + remove negatives + X >= 100000
            # ------------------------------------------------------
            before_rows = len(df)

            # Ensure Banco exists for Z fallback
            if "Banco" not in df.columns:
                df["Banco"] = pd.NA
                st.warning("⚠️ 'Banco' column missing — Z fallback (Banco+15) may be incomplete.")

            coord_cols = [
                "Coordenadas diseño X", "Coordenadas diseño Y", "Coordenadas diseño Z",
                "Coordenada real inicioX", "Coordenada real inicio Y", "Coordena real inicio Z"
            ]
            existing_coord = [c for c in coord_cols if c in df.columns]
            if existing_coord:
                df[existing_coord] = df[existing_coord].apply(
                    lambda s: pd.to_numeric(s, errors="coerce")
                )

            # X
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df["Coordenadas diseño X"] = df["Coordenadas diseño X"].fillna(df["Coordenada real inicioX"])
                df["Coordenada real inicioX"] = df["Coordenada real inicioX"].fillna(df["Coordenadas diseño X"])
                mask_x_empty = df["Coordenadas diseño X"].isna() & df["Coordenada real inicioX"].isna()
                df = df[~mask_x_empty]

            # Y
            if "Coordenadas diseño Y" in df.columns and "Coordenada real inicio Y" in df.columns:
                df["Coordenadas diseño Y"] = df["Coordenadas diseño Y"].fillna(df["Coordenada real inicio Y"])
                df["Coordenada real inicio Y"] = df["Coordenada real inicio Y"].fillna(df["Coordenadas diseño Y"])
                mask_y_empty = df["Coordenadas diseño Y"].isna() & df["Coordenada real inicio Y"].isna()
                df = df[~mask_y_empty]

            # Z
            if "Coordenadas diseño Z" in df.columns and "Coordena real inicio Z" in df.columns:
                df["Coordenadas diseño Z"] = df["Coordenadas diseño Z"].fillna(df["Coordena real inicio Z"])
                df["Coordena real inicio Z"] = df["Coordena real inicio Z"].fillna(df["Coordenadas diseño Z"])
                both_empty_mask = df["Coordenadas diseño Z"].isna() & df["Coordena real inicio Z"].isna()
                if both_empty_mask.any():
                    df.loc[both_empty_mask, "Coordenadas diseño Z"] = (
                        pd.to_numeric(df.loc[both_empty_mask, "Banco"], errors="coerce") + 15
                    )
                    df.loc[both_empty_mask, "Coordena real inicio Z"] = df.loc[both_empty_mask, "Coordenadas diseño Z"]

            # Remove rows with any negative coordinate (design or real)
            neg_mask = pd.Series(False, index=df.index)
            for c in ["Coordenadas diseño X", "Coordenadas diseño Y", "Coordenadas diseño Z",
                      "Coordenada real inicioX", "Coordenada real inicio Y", "Coordena real inicio Z"]:
                if c in df.columns:
                    neg_mask = neg_mask | (df[c] < 0)

            df = df[~neg_mask]

            # Remove rows where any X < 100000 (design or real)
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df = df[
                    (df["Coordenadas diseño X"] >= 100000) &
                    (df["Coordenada real inicioX"] >= 100000)
                ]

            deleted_rows_coord = before_rows - len(df)
            steps_done.append(
                f"✅ Cleaned coordinates: cross-filled, removed negatives/X<100000 "
                f"({deleted_rows_coord} rows deleted)."
            )

            # ------------------------------------------------------
            # STEP 7 – Dureza / RPM / Velocidad / Pulldown rules
            # ------------------------------------------------------
            # Dureza: empty → 0
            if "Dureza" in df.columns:
                df["Dureza"] = pd.to_numeric(df["Dureza"], errors="coerce").fillna(0)
                steps_done.append("✅ 'Dureza': empty values filled with 0.")
            else:
                steps_done.append("⚠️ Column 'Dureza' not found.")

            # RPM de perforacion: empty → 0
            if "RPM de perforacion" in df.columns:
                df["RPM de perforacion"] = pd.to_numeric(df["RPM de perforacion"], errors="coerce").fillna(0)
                steps_done.append("✅ 'RPM de perforacion': empty values filled with 0.")
            else:
                steps_done.append("⚠️ Column 'RPM de perforacion' not found.")

            # Velocidad de penetracion (m/minutos): empty or 0 → delete row
            if "Velocidad de penetracion (m/minutos)" in df.columns:
                before = len(df)
                df["Velocidad de penetracion (m/minutos)"] = pd.to_numeric(
                    df["Velocidad de penetracion (m/minutos)"], errors="coerce"
                )
                df = df[df["Velocidad de penetracion (m/minutos)"] > 0]
                deleted = before - len(df)
                steps_done.append(
                    f"✅ 'Velocidad de penetracion (m/minutos)': removed {deleted} rows (empty or 0)."
                )
            else:
                steps_done.append("⚠️ Column 'Velocidad de penetracion (m/minutos)' not found.")

            # Pulldown KN: empty or 0 → delete row
            if "Pulldown KN" in df.columns:
                before = len(df)
                df["Pulldown KN"] = pd.to_numeric(df["Pulldown KN"], errors="coerce")
                df = df[df["Pulldown KN"] > 0]
                deleted = before - len(df)
                steps_done.append(
                    f"✅ 'Pulldown KN': removed {deleted} rows (empty or 0)."
                )
            else:
                steps_done.append("⚠️ Column 'Pulldown KN' not found.")

            # ------------------------------------------------------
            # STEP 8 – Remove empty or zero Largo de pozo real
            # ------------------------------------------------------
            if "Largo de pozo real" in df.columns:
                before_len = len(df)
                df["Largo de pozo real"] = pd.to_numeric(df["Largo de pozo real"], errors="coerce")
                df = df[df["Largo de pozo real"].notna()]
                df = df[df["Largo de pozo real"] != 0]
                deleted_len = before_len - len(df)
                steps_done.append(
                    f"✅ Removed {deleted_len} rows with empty or zero 'Largo de pozo real'."
                )
            else:
                steps_done.append("⚠️ Column 'Largo de pozo real' not found.")

            # ------------------------------------------------------
            # STEP 9 – Categoria de pozo → CategoriaNew (1,2,3)
            # ------------------------------------------------------
            if "Categoria de pozo" in df.columns:
                def map_cat(val):
                    s = str(val).strip().lower()
                    if s.startswith("prod"):
                        return 1
                    if s.startswith("buff"):
                        return 2
                    if s.startswith("aux"):
                        return 3
                    if s in ["1", "2", "3"]:
                        return int(s)
                    return pd.NA

                idx_cat = df.columns.get_loc("Categoria de pozo")
                df.insert(idx_cat + 1, "CategoriaNew", df["Categoria de pozo"].apply(map_cat))
                steps_done.append("✅ Created 'CategoriaNew': Producción→1, Buffer→2, Auxiliar→3 (original kept).")
            else:
                steps_done.append("⚠️ Column 'Categoria de pozo' not found.")

            # ------------------------------------------------------
            # STEP 10 – Estatus de pozo: NO FILTER in cleaning
            # (Filter will be applied ONLY in TXT export)
            # ------------------------------------------------------
            if "Estatus de pozo" in df.columns:
                steps_done.append("ℹ️ 'Estatus de pozo' kept as-is. Drilled-only filter will be applied only for TXT export.")
            else:
                steps_done.append("⚠️ Column 'Estatus de pozo' not found.")

            # ------------------------------------------------------
            # STEP 11 – Operator Mapping (from uploaded mapping file) → OperadorNew
            # ------------------------------------------------------
            new_ops_df = None
            if "Operador" in df.columns:
                if uploaded_ops is None:
                    steps_done.append("⚠️ No operators mapping file uploaded — skipping operator mapping.")
                else:
                    try:
                        ops_df = pd.read_excel(uploaded_ops)

                        # Normalize headers in operators file
                        ops_rename = {}
                        for c in ops_df.columns:
                            n = normalize_header(c)
                            if n == "nombre":
                                ops_rename[c] = "Nombre"
                            elif n == "codigo":
                                ops_rename[c] = "Codigo"
                        ops_df = ops_df.rename(columns=ops_rename)

                        if "Nombre" not in ops_df.columns or "Codigo" not in ops_df.columns:
                            steps_done.append("⚠️ Operators file must contain 'Nombre' and 'Codigo' columns.")
                        else:
                            # Normalize names and build map
                            ops_df["Nombre"] = ops_df["Nombre"].astype(str).str.strip()
                            ops_df["Codigo"] = pd.to_numeric(ops_df["Codigo"], errors="coerce").astype("Int64")
                            ops_df = ops_df.dropna(subset=["Codigo"])

                            ops_df["Norm"] = ops_df["Nombre"].apply(
                                lambda x: re.sub(r"\s+", "", normalize_text(x))
                            )
                            norm_to_code = dict(zip(ops_df["Norm"], ops_df["Codigo"]))

                            max_code = int(ops_df["Codigo"].max() or 0)
                            next_code_box = [max_code + 1]

                            new_norm_to_code = {}
                            new_ops = []

                            def map_operator(raw):
                                # Empty → 75
                                if pd.isna(raw) or str(raw).strip() == "":
                                    return 75
                                s_norm = re.sub(r"\s+", "", normalize_text(raw))

                                # Exact normalized match
                                if s_norm in norm_to_code:
                                    return int(norm_to_code[s_norm])

                                # Fuzzy against existing operators
                                candidates = list(norm_to_code.keys())
                                if candidates:
                                    best = None
                                    best_sim = 0.0
                                    for key in candidates:
                                        sim = SequenceMatcher(None, s_norm, key).ratio()
                                        if sim > best_sim:
                                            best_sim = sim
                                            best = key
                                    if best is not None and best_sim >= 0.90:
                                        return int(norm_to_code[best])

                                # Check among new operators we've already created
                                for known_norm, code in new_norm_to_code.items():
                                    sim = SequenceMatcher(None, s_norm, known_norm).ratio()
                                    if sim >= 0.95:
                                        return int(code)

                                # New operator → assign next code
                                code = next_code_box[0]
                                next_code_box[0] += 1
                                new_norm_to_code[s_norm] = code
                                new_ops.append((str(raw).strip(), code))
                                return int(code)

                            # Create OperadorNew next to Operador
                            idx_op = df.columns.get_loc("Operador")
                            operador_new_series = df["Operador"].apply(map_operator)
                            df.insert(idx_op + 1, "OperadorNew", operador_new_series)

                            if new_ops:
                                new_ops_df = pd.DataFrame(new_ops, columns=["Nombre", "Codigo"])
                                steps_done.append(f"🆕 New operators detected: {len(new_ops)}")
                            else:
                                steps_done.append("✅ All operators matched existing mapping — no new ones added.")

                    except Exception as e:
                        steps_done.append(f"⚠️ Operator mapping error: {e}")
            else:
                steps_done.append("⚠️ Column 'Operador' not found.")

            # ------------------------------------------------------
            # STEP 12 – Modo de perforacion → ModoNew
            # Autonomous=1, Manual=2, Teleremote=3
            # ------------------------------------------------------
            if "Modo de perforacion" in df.columns:
                def map_modo(val):
                    s = str(val).strip().lower()
                    if s.startswith("auton"):
                        return 1
                    if s.startswith("manu"):
                        return 2
                    if s.startswith("tele"):
                        return 3
                    if s in ["1", "2", "3"]:
                        return int(s)
                    return pd.NA

                idx_modo = df.columns.get_loc("Modo de perforacion")
                df.insert(idx_modo + 1, "ModoNew", df["Modo de perforacion"].apply(map_modo))
                steps_done.append("✅ Created 'ModoNew': Autonomous→1, Manual→2, Teleremote→3 (original kept).")
            else:
                steps_done.append("⚠️ Column 'Modo de perforacion' not found.")

            # --- Display Steps in Green Cards ---
            for step in steps_done:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )

            # If there are new operators, show them in a small table
            if uploaded_ops is not None and 'new_ops_df' in locals() and new_ops_df is not None and not new_ops_df.empty:
                st.markdown("### 🆕 New operators suggested")
                st.dataframe(new_ops_df, use_container_width=True)

        # ==========================================================
        # AFTER CLEANING
        # ==========================================================
        st.markdown("---")
        st.subheader("✅ Cleaned Data Preview")
        st.dataframe(df.head(15), use_container_width=True)
        st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

        # ==========================================================
        # DOWNLOAD SECTION (EXCEL + CSV)
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Cleaned Autonomía File")

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
        export_df.to_csv(csv_buffer, index=False)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel File",
                excel_buffer,
                file_name="Escondida_Autonomia_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📗 Download CSV File",
                csv_buffer.getvalue(),
                file_name="Escondida_Autonomia_Cleaned.csv",
                mime="text/csv",
                use_container_width=True
            )

        # ==========================================================
        # DOWNLOAD UPDATED OPERATORS (IF ANY)
        # ==========================================================
        if uploaded_ops is not None and 'new_ops_df' in locals() and new_ops_df is not None and not new_ops_df.empty:
            try:
                ops_base = pd.read_excel(uploaded_ops)
                # Normalize headers like before
                ops_rename2 = {}
                for c in ops_base.columns:
                    n = normalize_header(c)
                    if n == "nombre":
                        ops_rename2[c] = "Nombre"
                    elif n == "codigo":
                        ops_rename2[c] = "Codigo"
                ops_base = ops_base.rename(columns=ops_rename2)

                # Append new operators
                updated_ops = pd.concat(
                    [ops_base[["Nombre", "Codigo"]], new_ops_df],
                    ignore_index=True
                )

                ops_buffer = io.BytesIO()
                updated_ops.to_excel(ops_buffer, index=False, engine="openpyxl")
                ops_buffer.seek(0)

                today_str = datetime.now().strftime("%d_%m_%Y")
                ops_filename = f"ES_Operators_{today_str}.xlsx"

                st.markdown("---")
                st.subheader("💾 Export Updated Operators Mapping")
                st.download_button(
                    "📘 Download Updated ES_Operators File",
                    ops_buffer,
                    file_name=ops_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.warning(f"⚠️ Could not build updated operators file: {e}")

        # ==========================================================
        # TXT EXPORT — ONLY DRILLED + CategoriaNew 1–2
        # ==========================================================
        st.markdown("---")
        st.subheader("📄 Export TXT (Drilled + Categoria 1–2)")

        # Work from full cleaned df, not from export_df
        df_txt = df.copy()
        if "Estatus de pozo" in df_txt.columns:
            df_txt = df_txt[df_txt["Estatus de pozo"].astype(str).str.strip().str.lower() == "drilled"]
        if "CategoriaNew" in df_txt.columns:
            df_txt = df_txt[df_txt["CategoriaNew"].isin([1, 2])]

        txt_buffer = io.StringIO()
        df_txt.to_csv(txt_buffer, index=False, sep="|")

        st.download_button(
            "📄 Download TXT (Drilled Only)",
            txt_buffer.getvalue(),
            file_name="Escondida_Autonomia_Drilled.txt",
            mime="text/plain",
            use_container_width=True
        )

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi -")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

else:
    st.info("📂 Please upload the Autonomía Excel file (and optionally the Operators mapping file) to begin.")

