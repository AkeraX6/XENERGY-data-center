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

def normalize_header(col: str) -> str:
    """
    Normaliza nombres de columnas:
    - pasa a str
    - elimina NBSP
    - strip
    - minúsculas
    - elimina acentos
    - deja solo letras y números (sin espacios)
    """
    s = str(col).replace("\xa0", " ")
    s = s.strip().lower()
    s = ''.join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s


def build_colmap(df: pd.DataFrame):
    """Devuelve un dict {normalized_name: original_name} para el DataFrame."""
    colmap = {}
    for c in df.columns:
        key = normalize_header(c)
        # En caso de duplicados, nos quedamos con el primero
        if key not in colmap:
            colmap[key] = c
    return colmap


def get_col(colmap: dict, logical_name: str):
    """
    Dado un mapa normalizado y un nombre lógico (por ejemplo 'Perforadora'),
    devuelve el nombre real de la columna en el DataFrame o None si no existe.
    """
    key = normalize_header(logical_name)
    return colmap.get(key)


def _strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm_ws(s: str) -> str:
    """Quita espacios repetidos, deja uno, y trim."""
    return re.sub(r'\s+', ' ', str(s)).strip()


def _nospace(s: str) -> str:
    """Quita todos los espacios."""
    return re.sub(r'\s+', '', str(s))


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
st.subheader("📤 Upload Files")

uploaded_auto = st.file_uploader(
    "1️⃣ Upload Autonomía file",
    type=["xlsx", "xls", "csv"],
    key="auto_file"
)

uploaded_ops = st.file_uploader(
    "2️⃣ Upload Operators mapping file (Excel with Nombre & Codigo)",
    type=["xlsx", "xls"],
    key="ops_file"
)

if uploaded_auto is not None:
    try:
        # --------- READ MAIN FILE (simple: Excel or CSV) ----------
        name = uploaded_auto.name.lower()
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_auto)
        else:
            df = pd.read_excel(uploaded_auto)

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        steps_done = []

        # Build header normalization map
        colmap = build_colmap(df)

        # ==========================================================
        # CLEANING & TRANSFORMATION STEPS
        # ==========================================================
        with st.expander("⚙️ See Processing Steps", expanded=False):

            # ------------------------------------------------------
            # STEP 1 – Validate Column Structure (tolerant headers)
            # ------------------------------------------------------
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

            missing_cols = []
            for cname in EXPECTED_COLUMNS:
                if get_col(colmap, cname) is None:
                    missing_cols.append(cname)

            if missing_cols:
                steps_done.append(
                    f"⚠️ Some expected columns not found (after normalization): {', '.join(missing_cols)}"
                )
            else:
                steps_done.append("✅ File column structure validated (headers matched with normalization).")

            # ------------------------------------------------------
            # STEP 2 – Transform Base Columns
            # ------------------------------------------------------
            # Perforadora: keep only numeric (e.g. PE_01 → 1)
            col_perfo = get_col(colmap, "Perforadora")
            if col_perfo:
                df[col_perfo] = df[col_perfo].astype(str)
                df[col_perfo] = df[col_perfo].str.extract(r'(\d+)', expand=False)
                df[col_perfo] = pd.to_numeric(df[col_perfo], errors="coerce")
                steps_done.append("✅ Perforadora: extracted numeric value (e.g. PE_01 → 1).")
            else:
                steps_done.append("⚠️ Column 'Perforadora' not found.")

            # Turno: Dia/Noche → 1/2
            col_turno = get_col(colmap, "turno (dia o noche)")
            if col_turno:
                turn_lower = df[col_turno].astype(str).str.strip().str.lower()
                df[col_turno] = turn_lower.replace({
                    "dia": 1, "día": 1, "d": 1, "1": 1,
                    "noche": 2, "n": 2, "2": 2
                })
                steps_done.append("✅ Turno: mapped Dia→1, Noche→2 (tolerant to spelling).")
            else:
                steps_done.append("⚠️ Column 'turno (dia o noche)' not found.")

            # Coordinacion: A,B,C,D → 1,2,3,4
            col_coord = get_col(colmap, "Coordinacion")
            if col_coord:
                df[col_coord] = df[col_coord].astype(str).str.strip().str.upper()
                df[col_coord] = df[col_coord].replace({"A": 1, "B": 2, "C": 3, "D": 4})
                steps_done.append("✅ Coordinacion: mapped A/B/C/D → 1/2/3/4.")
            else:
                steps_done.append("⚠️ Column 'Coordinacion' not found.")

            # ------------------------------------------------------
            # STEP 3 – Split and Extract Banco / Expansion / MallaID
            # ------------------------------------------------------
            col_malla = get_col(colmap, "Malla")
            if col_malla:
                malla_split = df[col_malla].astype(str).str.split("-", expand=True)

                banco = malla_split[0].str[:4]
                expansion = malla_split[1].str.extract(r'(\d+)', expand=True)
                mallaid = malla_split[2].str[-4:]

                # Clean non-numeric
                banco = banco.astype(str).str.replace(r'[^0-9]', '', regex=True)
                expansion = expansion.astype(str).str.replace(r'[^0-9]', '', regex=True)
                mallaid = mallaid.astype(str).str.replace(r'[^0-9]', '', regex=True)

                df[col_malla] = mallaid
                df.rename(columns={col_malla: "MallaID"}, inplace=True)

                # Rebuild colmap after rename
                colmap = build_colmap(df)
                col_mallaid = get_col(colmap, "MallaID")

                # Insert Banco & Expansion before MallaID
                if col_mallaid:
                    idx = df.columns.get_loc(col_mallaid)
                    df.insert(idx, "Banco", banco)
                    df.insert(idx + 1, "Expansion", expansion)
                    colmap = build_colmap(df)
                    steps_done.append("✅ Extracted Banco, Expansion, and MallaID from Malla (letters removed).")
                else:
                    steps_done.append("⚠️ MallaID not found after renaming.")
            else:
                steps_done.append("⚠️ Column 'Malla' not found in the dataset.")

            # ------------------------------------------------------
            # STEP 4 – Transform and clean Pozo values
            # ------------------------------------------------------
            col_pozo = get_col(colmap, "Pozo")
            if col_pozo:
                before_rows = len(df)

                def transform_pozo(val):
                    val = str(val).strip()
                    if val.startswith("Aux") or val.startswith("aux"):
                        return val  # we'll drop later
                    elif val.startswith("B"):
                        return "100000" + val[1:]
                    elif val.startswith("C"):
                        return "200000" + val[1:]
                    elif val.startswith("D"):
                        return val[1:]
                    else:
                        return val

                df[col_pozo] = df[col_pozo].apply(transform_pozo)

                # Remove Aux and pure letters
                df = df[~df[col_pozo].astype(str).str.contains("Aux", case=False, na=False)]
                df = df[~df[col_pozo].astype(str).str.fullmatch(r'[A-Za-z]+', na=False)]

                # Convert to numeric and drop <= 0
                df["__Pozo_num"] = pd.to_numeric(df[col_pozo], errors="coerce")
                df = df[df["__Pozo_num"].notna()]
                df = df[df["__Pozo_num"] > 0]
                df[col_pozo] = df["__Pozo_num"].astype(int)
                df.drop(columns=["__Pozo_num"], inplace=True)

                deleted_rows = before_rows - len(df)
                steps_done.append(f"✅ Cleaned Pozo: removed Aux, letters, and non-positive values ({deleted_rows} rows).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # ------------------------------------------------------
            # STEP 5 – Cross-fill and clean Coordinates (X, Y, Z)
            #         + delete negative coordinates
            # ------------------------------------------------------
            before_rows = len(df)

            # Ensure Banco exists for Z fallback rule
            if get_col(colmap, "Banco") is None:
                df["Banco"] = pd.NA
                colmap = build_colmap(df)

            col_xd = get_col(colmap, "Coordenadas diseño X")
            col_yd = get_col(colmap, "Coordenadas diseño Y")
            col_zd = get_col(colmap, "Coordenadas diseño Z")
            col_xr = get_col(colmap, "Coordenada real inicioX")
            col_yr = get_col(colmap, "Coordenada real inicio Y")
            col_zr = get_col(colmap, "Coordena real inicio Z")
            col_banco = get_col(colmap, "Banco")

            # X
            if col_xd and col_xr:
                df[col_xd] = df[col_xd].fillna(df[col_xr])
                df[col_xr] = df[col_xr].fillna(df[col_xd])
                mask_x_empty = df[col_xd].isna() & df[col_xr].isna()
                df = df[~mask_x_empty]

            # Y
            if col_yd and col_yr:
                df[col_yd] = df[col_yd].fillna(df[col_yr])
                df[col_yr] = df[col_yr].fillna(df[col_yd])
                mask_y_empty = df[col_yd].isna() & df[col_yr].isna()
                df = df[~mask_y_empty]

            # Z
            if col_zd and col_zr:
                df[col_zd] = df[col_zd].fillna(df[col_zr])
                df[col_zr] = df[col_zr].fillna(df[col_zd])
                both_empty_mask = df[col_zd].isna() & df[col_zr].isna()
                if both_empty_mask.any() and col_banco:
                    banco_numeric = pd.to_numeric(df[col_banco], errors="coerce")
                    df.loc[both_empty_mask, col_zd] = banco_numeric[both_empty_mask] + 15
                    df.loc[both_empty_mask, col_zr] = df.loc[both_empty_mask, col_zd]

            # Convert coords to numeric for comparisons
            for c in [col_xd, col_xr, col_yd, col_yr, col_zd, col_zr]:
                if c:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            # Remove rows with X < 100000 or negative coords
            coord_mask = pd.Series(True, index=df.index)

            if col_xd and col_xr:
                coord_mask &= df[col_xd].notna() & df[col_xr].notna()
                coord_mask &= df[col_xd] >= 100000
                coord_mask &= df[col_xr] >= 100000

            # Negative check (X,Y,Z design/real inicio)
            for c in [col_xd, col_xr, col_yd, col_yr, col_zd, col_zr]:
                if c:
                    coord_mask &= (df[c].isna() | (df[c] >= 0))

            df = df[coord_mask]

            deleted_rows = before_rows - len(df)
            steps_done.append(
                f"✅ Cleaned Coordinates: cross-filled, applied Banco+15 rule, "
                f"and deleted {deleted_rows} rows with invalid/negative coords or X<100000."
            )

            # ------------------------------------------------------
            # STEP 6 – Remove empty or zero Largo de pozo real
            # ------------------------------------------------------
            col_largo_real = get_col(colmap, "Largo de pozo real")
            if col_largo_real:
                before_len = len(df)
                df = df[df[col_largo_real].notna()]
                df = df[df[col_largo_real] != 0]
                deleted_len = before_len - len(df)
                steps_done.append(f"✅ Removed {deleted_len} rows with empty or zero 'Largo de pozo real'.")
            else:
                steps_done.append("⚠️ Column 'Largo de pozo real' not found.")

            # ------------------------------------------------------
            # STEP 7 – Dureza, RPM, Velocidad, Pulldown rules
            # ------------------------------------------------------
            col_dureza = get_col(colmap, "Dureza")
            col_vel_pen = get_col(colmap, "Velocidad de penetracion (m/minutos)")
            col_rpm = get_col(colmap, "RPM de perforacion")
            col_pull = get_col(colmap, "Pulldown KN")

            # Dureza: empty → 0
            if col_dureza:
                df[col_dureza] = df[col_dureza].fillna(0)
            # RPM: empty → 0
            if col_rpm:
                df[col_rpm] = df[col_rpm].fillna(0)

            deleted_vp = deleted_pd = 0

            # Velocidad de penetracion (m/minutos): empty or 0 → delete row
            if col_vel_pen:
                before_len = len(df)
                df = df[df[col_vel_pen].notna()]
                df = df[df[col_vel_pen] != 0]
                deleted_vp = before_len - len(df)

            # Pulldown KN: empty or 0 → delete row
            if col_pull:
                before_len2 = len(df)
                df = df[df[col_pull].notna()]
                df = df[df[col_pull] != 0]
                deleted_pd = before_len2 - len(df)

            steps_done.append(
                f"✅ Dureza/RPM: empty→0; "
                f"Velocidad de penetracion & Pulldown KN: removed {deleted_vp + deleted_pd} invalid rows."
            )

            # ------------------------------------------------------
            # STEP 8 – Estatus de pozo: keep only 'Drilled'
            # ------------------------------------------------------
            col_status = get_col(colmap, "Estatus de pozo")
            if col_status:
                before_len = len(df)
                status_norm = df[col_status].astype(str).str.strip().str.lower()
                df = df[status_norm == "drilled"]
                deleted_status = before_len - len(df)
                steps_done.append(f"✅ Estatus de pozo: kept only 'Drilled' ({deleted_status} rows removed).")
            else:
                steps_done.append("⚠️ Column 'Estatus de pozo' not found.")

            # ------------------------------------------------------
            # STEP 9 – Categoria de Pozo mapping
            # ------------------------------------------------------
            col_cat = get_col(colmap, "Categoria de pozo")
            if col_cat:
                cat_norm = df[col_cat].astype(str).str.strip().str.lower()
                df[col_cat] = cat_norm.replace({
                    "produccion": 1,
                    "producción": 1,
                    "production": 1,
                    "buffer": 2,
                    "auxiliar": 3,
                    "aux": 3
                })
                steps_done.append("✅ Categoria de pozo: mapped Produccion/Buffer/Auxiliar → 1/2/3.")
            else:
                steps_done.append("⚠️ Column 'Categoria de pozo' not found.")

            # ------------------------------------------------------
            # STEP 10 – Operator Mapping (using uploaded mapping file)
            # ------------------------------------------------------
            col_oper = get_col(colmap, "Operador")
            EMPTY_OPERATOR_CODE = 75

            if col_oper:
                if uploaded_ops is None:
                    steps_done.append("⚠️ No operators mapping file uploaded — Operador column left as is.")
                else:
                    try:
                        ops_df = pd.read_excel(uploaded_ops)

                        # Normalize headers in ops_df to find Nombre & Codigo
                        ops_colmap = build_colmap(ops_df)
                        col_name = None
                        col_code = None
                        # try to detect logical columns
                        for cand in ["Nombre", "Operador", "Operator", "Name"]:
                            col_name = get_col(ops_colmap, cand)
                            if col_name:
                                break
                        for cand in ["Codigo", "Código", "Code", "ID", "Id"]:
                            col_code = get_col(ops_colmap, cand)
                            if col_code:
                                break

                        if not col_name or not col_code:
                            steps_done.append("⚠️ Operators mapping file does not contain identifiable 'Nombre' and 'Codigo' columns.")
                        else:
                            ops_df = ops_df[[col_name, col_code]].copy()
                            ops_df.columns = ["Nombre", "Codigo"]

                            # Build operator index
                            _operator_names = {}
                            _ops_index = []

                            for _, row in ops_df.iterrows():
                                raw_name = str(row["Nombre"]).strip()
                                code = row["Codigo"]
                                if pd.isna(code):
                                    continue
                                try:
                                    code = int(code)
                                except Exception:
                                    continue

                                norm_ws = _norm_ws(_strip_accents(raw_name).lower())
                                nosp = _nospace(norm_ws)
                                tokens = set(norm_ws.split())
                                _operator_names[raw_name] = code
                                _ops_index.append({
                                    "raw": raw_name,
                                    "code": code,
                                    "nospace": nosp,
                                    "tokens": tokens,
                                    "ntok": len(tokens)
                                })

                            new_operators = {}

                            def _best_operator_match(raw_value: str):
                                """Return (code, reason) with dynamic sequential assignment for new operators."""
                                # Empty → default code
                                if pd.isna(raw_value) or str(raw_value).strip() == "":
                                    return EMPTY_OPERATOR_CODE, "empty→default"

                                s_ws = _norm_ws(_strip_accents(str(raw_value)).lower())
                                s_ns = _nospace(s_ws)
                                s_tokens = set(s_ws.split())

                                # 1️⃣ Exact nospace match
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
                                norm_name = s_ns

                                # Prevent duplicates among new_operators
                                for known_name, known_code in new_operators.items():
                                    known_norm = _nospace(
                                        _norm_ws(_strip_accents(str(known_name)).lower())
                                    )
                                    sim = SequenceMatcher(None, norm_name, known_norm).ratio()
                                    if sim >= 0.95:
                                        return known_code, "duplicate-new"

                                # Initialize counter if not present
                                if not hasattr(_best_operator_match, "next_code"):
                                    if _operator_names:
                                        max_code = max(_operator_names.values())
                                    else:
                                        max_code = EMPTY_OPERATOR_CODE + 1
                                    _best_operator_match.next_code = max_code + 1

                                new_code = _best_operator_match.next_code
                                _best_operator_match.next_code += 1

                                new_operators[raw_value] = new_code
                                _operator_names[raw_value] = new_code
                                return new_code, "new-operator"

                            def convert_operador(value):
                                code, _reason = _best_operator_match(value)
                                return code

                            # Apply mapping to df
                            before_unique = df[col_oper].nunique(dropna=True)
                            df[col_oper] = df[col_oper].apply(convert_operador)
                            after_unique = df[col_oper].nunique(dropna=True)

                            steps_done.append(
                                f"✅ Operador: converted names to numeric IDs "
                                f"(unique operators before: {before_unique}, after: {after_unique})."
                            )

                            # Show new operators and provide download of updated mapping
                            if new_operators:
                                new_ops_df = pd.DataFrame(
                                    [{"Nombre": k, "Codigo": v} for k, v in new_operators.items()]
                                )
                                st.info(f"🆕 New operators detected: {len(new_operators)}")
                                st.dataframe(new_ops_df, use_container_width=True)

                                updated_ops = pd.concat([ops_df, new_ops_df], ignore_index=True)

                                # Download button for updated operators mapping
                                date_str = datetime.now().strftime("%d_%m_%Y")
                                ops_buffer = io.BytesIO()
                                updated_ops.to_excel(ops_buffer, index=False, engine="openpyxl")
                                ops_buffer.seek(0)

                                st.download_button(
                                    "📥 Download updated Operators mapping",
                                    ops_buffer,
                                    file_name=f"ES_Operators_{date_str}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            else:
                                steps_done.append("✅ All operators matched existing records — no new ones detected.")

                    except Exception as e:
                        steps_done.append(f"⚠️ Error processing operators mapping file: {e}")
            else:
                steps_done.append("⚠️ Column 'Operador' not found.")

            # ------------------------------------------------------
            # STEP 11 – Modo de perforacion mapping
            # Autonomous=1; Manual=2; Teleremote=3
            # ------------------------------------------------------
            col_modo = get_col(colmap, "Modo de perforacion")
            if col_modo:
                modo_norm = df[col_modo].astype(str).str.strip().str.lower()
                df[col_modo] = modo_norm.replace({
                    "autonomous": 1,
                    "autónomo": 1,
                    "autonomo": 1,
                    "manual": 2,
                    "teleremote": 3,
                    "tele-remote": 3
                })
                steps_done.append("✅ Modo de perforacion: mapped Autonomous=1, Manual=2, Teleremote=3.")
            else:
                steps_done.append("⚠️ Column 'Modo de perforacion' not found.")

            # --- Display Steps in Green Cards ---
            for step in steps_done:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )

        # ==========================================================
        # AFTER CLEANING
        # ==========================================================
        st.markdown("---")
        st.subheader("✅ Cleaned Data Preview")
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

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi -")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

else:
    st.info("📂 Please upload the Autonomía file (and optionally Operators mapping) to begin.")

