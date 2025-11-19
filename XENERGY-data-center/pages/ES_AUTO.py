import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime

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
    "📤 Upload AUTONOMÍA data file",
    type=["xlsx", "xls", "csv"],
    key="auto_file"
)

uploaded_ops = st.file_uploader(
    "📤 Upload Operators mapping file (Excel with columns 'Nombre' and 'Codigo')",
    type=["xlsx", "xls"],
    key="ops_file"
)

def read_csv_smart(file_obj):
    """Detect CSV delimiter automatically."""
    sample = file_obj.read(8192).decode(errors="replace")
    file_obj.seek(0)
    try:
        return pd.read_csv(file_obj, sep=None, engine="python")
    except Exception:
        if sample.count(";") > sample.count(","):
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep=";")
        elif sample.count("\t") > 0:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep="\t")
        elif sample.count("|") > 0:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep="|")
        else:
            file_obj.seek(0)
            return pd.read_csv(file_obj)

if uploaded_file is not None:
    try:
        file_name = uploaded_file.name.lower()
        if file_name.endswith(".csv"):
            df = read_csv_smart(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        steps_done = []
        updated_ops = None   # Will hold updated operators mapping if we build it
        new_ops_df = None

        # ==========================================================
        # CLEANING & TRANSFORMATION STEPS
        # ==========================================================
        with st.expander("⚙️ See Processing Steps", expanded=False):

            # STEP 1 – Validate Column Structure
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

            if list(df.columns) != EXPECTED_COLUMNS:
                steps_done.append("⚠️ Column names or order do not match the expected format.")
            else:
                steps_done.append("✅ File column structure validated successfully.")

            # STEP 2 – Transform Base Columns
            # 2.1 Perforadora → keep only numeric, e.g. 'PE_01' → 1
            if "Perforadora" in df.columns:
                df["Perforadora"] = (
                    df["Perforadora"]
                    .astype(str)
                    .str.extract(r"(\d+)", expand=False)
                )
                df["Perforadora"] = pd.to_numeric(df["Perforadora"], errors="coerce").fillna(0).astype(int)
                steps_done.append("✅ Perforadora: extracted numeric value (e.g. PE_01 → 1).")
            else:
                steps_done.append("⚠️ Column 'Perforadora' not found.")

            # 2.2 Turno → Dia/Noche to 1/2
            if "turno (dia o noche)" in df.columns:
                df["turno (dia o noche)"] = df["turno (dia o noche)"].replace({"Dia": 1, "Noche": 2})
                steps_done.append("✅ Normalized 'turno (dia o noche)': Dia→1, Noche→2.")
            else:
                steps_done.append("⚠️ Column 'turno (dia o noche)' not found.")

            # 2.3 Coordinacion → A/B/C/D to 1/2/3/4
            if "Coordinacion" in df.columns:
                df["Coordinacion"] = df["Coordinacion"].replace({"A": 1, "B": 2, "C": 3, "D": 4})
                steps_done.append("✅ Normalized 'Coordinacion': A/B/C/D → 1/2/3/4.")
            else:
                steps_done.append("⚠️ Column 'Coordinacion' not found.")

            # STEP 3 – Split and Extract Banco / Expansion / MallaID
            if "Malla" in df.columns:
                malla_split = df["Malla"].astype(str).str.split("-", expand=True)

                banco = malla_split[0].str[:4]
                expansion = malla_split[1].str.extract(r'(\d+)', expand=False)
                mallaid = malla_split[2].str[-4:]

                # Remove letters → keep only digits
                banco = banco.astype(str).str.replace(r"[^0-9]", "", regex=True)
                expansion = expansion.astype(str).str.replace(r"[^0-9]", "", regex=True)
                mallaid = mallaid.astype(str).str.replace(r"[^0-9]", "", regex=True)

                df["Malla"] = mallaid
                df = df.rename(columns={"Malla": "MallaID"})
                col_index = df.columns.get_loc("MallaID")
                df.insert(col_index, "Banco", banco)
                df.insert(col_index + 1, "Expansion", expansion)

                steps_done.append("✅ Extracted Banco, Expansion, and MallaID from 'Malla' (letters removed).")
            else:
                steps_done.append("⚠️ Column 'Malla' not found in the dataset.")

            # STEP 4 – Transform and clean Pozo values
            if "Pozo" in df.columns:
                before_rows = len(df)

                def transform_pozo(val):
                    val = str(val).strip()
                    if val.startswith("Aux"):
                        return val
                    elif val.startswith("B"):
                        return "100000" + val[1:]
                    elif val.startswith("C"):
                        return "200000" + val[1:]
                    elif val.startswith("D"):
                        return val[1:]
                    else:
                        return val

                df["Pozo"] = df["Pozo"].apply(transform_pozo)

                # Remove pozos with 'Aux' and pure letters
                df = df[~df["Pozo"].astype(str).str.contains("Aux", case=False, na=False)]
                df = df[~df["Pozo"].astype(str).str.fullmatch(r"[A-Za-z]+", na=False)]

                # Convert to numeric, drop non-positive
                df["Pozo_num"] = pd.to_numeric(df["Pozo"], errors="coerce")
                df = df[df["Pozo_num"].notna()]
                df = df[df["Pozo_num"] > 0]
                df["Pozo"] = df["Pozo_num"].astype(int)
                df = df.drop(columns=["Pozo_num"])

                deleted_rows = before_rows - len(df)
                steps_done.append(f"✅ Cleaned 'Pozo': removed Aux/letters/non-positive ({deleted_rows} rows deleted).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # STEP 5 – Cross-fill and clean Coordinates (X, Y, Z) + remove negatives
            before_rows = len(df)

            if "Banco" not in df.columns:
                df["Banco"] = pd.NA
                steps_done.append("⚠️ 'Banco' missing — Z fallback (Banco+15) may be incomplete.")

            # X
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df["Coordenadas diseño X"] = df["Coordenadas diseño X"].fillna(df["Coordenada real inicioX"])
                df["Coordenada real inicioX"] = df["Coordenada real inicioX"].fillna(df["Coordenadas diseño X"])
                mask_x_empty = df["Coordenadas diseño X"].isna() & df["Coordenada real inicioX"].isna()
                df = df[~mask_x_empty]
                # X must be ≥ 100000
                df = df[
                    (df["Coordenadas diseño X"] >= 100000) &
                    (df["Coordenada real inicioX"] >= 100000)
                ]
            else:
                steps_done.append("⚠️ X coordinate columns missing.")

            # Y
            if "Coordenadas diseño Y" in df.columns and "Coordenada real inicio Y" in df.columns:
                df["Coordenadas diseño Y"] = df["Coordenadas diseño Y"].fillna(df["Coordenada real inicio Y"])
                df["Coordenada real inicio Y"] = df["Coordenada real inicio Y"].fillna(df["Coordenadas diseño Y"])
                mask_y_empty = df["Coordenadas diseño Y"].isna() & df["Coordenada real inicio Y"].isna()
                df = df[~mask_y_empty]
            else:
                steps_done.append("⚠️ Y coordinate columns missing.")

            # Z
            if "Coordenadas diseño Z" in df.columns and "Coordena real inicio Z" in df.columns:
                df["Coordenadas diseño Z"] = df["Coordenadas diseño Z"].fillna(df["Coordena real inicio Z"])
                df["Coordena real inicio Z"] = df["Coordena real inicio Z"].fillna(df["Coordenadas diseño Z"])
                both_empty_mask = df["Coordenadas diseño Z"].isna() & df["Coordena real inicio Z"].isna()
                if both_empty_mask.any():
                    df.loc[both_empty_mask, "Coordenadas diseño Z"] = (
                        pd.to_numeric(df.loc[both_empty_mask, "Banco"], errors="coerce") + 15
                    )
                    df.loc[both_empty_mask, "Coordena real inicio Z"] = df.loc[
                        both_empty_mask, "Coordenadas diseño Z"
                    ]
            else:
                steps_done.append("⚠️ Z coordinate columns missing.")

            # Ensure coordinates are numeric and drop negative X/Y/Z
            coord_cols = [
                "Coordenadas diseño X", "Coordenada real inicioX",
                "Coordenadas diseño Y", "Coordenada real inicio Y",
                "Coordenadas diseño Z", "Coordena real inicio Z"
            ]
            for c in coord_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            before_neg = len(df)
            neg_mask = (
                (df["Coordenadas diseño X"] < 0) |
                (df["Coordenada real inicioX"] < 0) |
                (df["Coordenadas diseño Y"] < 0) |
                (df["Coordenada real inicio Y"] < 0) |
                (df["Coordenadas diseño Z"] < 0) |
                (df["Coordena real inicio Z"] < 0)
            )
            df = df[~neg_mask]
            deleted_neg = before_neg - len(df)

            deleted_rows = before_rows - len(df)
            steps_done.append(
                f"✅ Cleaned coordinates: cross-filled, enforced X≥100000, "
                f"and removed {deleted_neg} rows with negative coordinates "
                f"({deleted_rows} total rows removed in this step)."
            )

            # STEP 6 – Remove empty or zero Largo de pozo real
            if "Largo de pozo real" in df.columns:
                before_len = len(df)
                df["Largo de pozo real"] = pd.to_numeric(df["Largo de pozo real"], errors="coerce")
                df = df[df["Largo de pozo real"].notna()]
                df = df[df["Largo de pozo real"] != 0]
                deleted_len = before_len - len(df)
                steps_done.append(f"✅ Removed {deleted_len} rows with empty/zero 'Largo de pozo real'.")
            else:
                steps_done.append("⚠️ Column 'Largo de pozo real' not found.")

            # STEP 7 – Dureza / Velocidad / RPM / Pulldown rules
            # 7.1 Dureza: empty → 0
            if "Dureza" in df.columns:
                df["Dureza"] = pd.to_numeric(df["Dureza"], errors="coerce").fillna(0)
                steps_done.append("✅ 'Dureza': empty filled with 0.")
            else:
                steps_done.append("⚠️ Column 'Dureza' not found.")

            # 7.2 RPM de perforacion: empty → 0
            if "RPM de perforacion" in df.columns:
                df["RPM de perforacion"] = pd.to_numeric(df["RPM de perforacion"], errors="coerce").fillna(0)
                steps_done.append("✅ 'RPM de perforacion': empty filled with 0.")
            else:
                steps_done.append("⚠️ Column 'RPM de perforacion' not found.")

            # 7.3 Velocidad de penetracion (m/minutos):
            #     if empty OR 0 → delete row
            if "Velocidad de penetracion (m/minutos)" in df.columns:
                before_len = len(df)
                df["Velocidad de penetracion (m/minutos)"] = pd.to_numeric(
                    df["Velocidad de penetracion (m/minutos)"], errors="coerce"
                )
                df = df[
                    df["Velocidad de penetracion (m/minutos)"].notna() &
                    (df["Velocidad de penetracion (m/minutos)"] != 0)
                ]
                deleted_len = before_len - len(df)
                steps_done.append(
                    f"✅ Removed {deleted_len} rows with empty/zero "
                    f"'Velocidad de penetracion (m/minutos)'."
                )
            else:
                steps_done.append("⚠️ Column 'Velocidad de penetracion (m/minutos)' not found.")

            # 7.4 Pulldown KN: if empty OR 0 → delete row
            if "Pulldown KN" in df.columns:
                before_len = len(df)
                df["Pulldown KN"] = pd.to_numeric(df["Pulldown KN"], errors="coerce")
                df = df[df["Pulldown KN"].notna() & (df["Pulldown KN"] != 0)]
                deleted_len = before_len - len(df)
                steps_done.append(
                    f"✅ Removed {deleted_len} rows with empty/zero 'Pulldown KN'."
                )
            else:
                steps_done.append("⚠️ Column 'Pulldown KN' not found.")

            # STEP 8 – Estatus de pozo → keep only 'Drilled'
            if "Estatus de pozo" in df.columns:
                before_len = len(df)
                df["Estatus de pozo"] = df["Estatus de pozo"].astype(str)
                df = df[df["Estatus de pozo"].str.strip().str.lower() == "drilled"]
                deleted_len = before_len - len(df)
                steps_done.append(
                    f"✅ Filtered 'Estatus de pozo' to Drilled only "
                    f"({deleted_len} rows removed)."
                )
            else:
                steps_done.append("⚠️ Column 'Estatus de pozo' not found.")

            # STEP 9 – Categoria de Pozo: map + keep only 1 & 2
            if "Categoria de pozo" in df.columns:
                df["Categoria de pozo"] = df["Categoria de pozo"].replace({
                    "Produccion": 1,
                    "Buffer": 2,
                    "Auxiliar": 3
                })
                before_len = len(df)
                df = df[df["Categoria de pozo"].isin([1, 2])]
                deleted_len = before_len - len(df)
                steps_done.append(
                    f"✅ Mapped 'Categoria de pozo' and kept only 1 (Produccion) "
                    f"and 2 (Buffer): {deleted_len} rows removed."
                )
            else:
                steps_done.append("⚠️ Column 'Categoria de pozo' not found.")

            # ======================================================
            # STEP 10 – Operator Mapping (Option A logic, uploaded file)
            # ======================================================
            if uploaded_ops is not None and "Operador" in df.columns:
                try:
                    ops_df = pd.read_excel(uploaded_ops)
                    if not {"Nombre", "Codigo"}.issubset(ops_df.columns):
                        steps_done.append(
                            "⚠️ Operators file must contain 'Nombre' and 'Codigo' columns. "
                            "Operator mapping skipped."
                        )
                    else:
                        # Normalize operators mapping
                        ops_df = ops_df.copy()
                        ops_df["Nombre"] = ops_df["Nombre"].astype(str).str.strip()
                        ops_df["Codigo"] = pd.to_numeric(ops_df["Codigo"], errors="coerce").astype("Int64")

                        # --- Helper functions for Option A logic ---
                        def _strip_accents(s: str) -> str:
                            return "".join(
                                c for c in unicodedata.normalize("NFD", str(s))
                                if unicodedata.category(c) != "Mn"
                            )

                        def _norm_ws(s: str) -> str:
                            s = _strip_accents(str(s).lower().strip())
                            return " ".join(s.split())

                        def _nospace(s: str) -> str:
                            return re.sub(r"\s+", "", _norm_ws(s))

                        # Build index
                        _ops_index = []
                        _operator_names = {}
                        for _, row in ops_df.iterrows():
                            name = str(row["Nombre"]).strip()
                            code = int(row["Codigo"]) if not pd.isna(row["Codigo"]) else None
                            if code is None:
                                continue
                            norm_ws = _norm_ws(name)
                            nospace = _nospace(name)
                            tokens = set(norm_ws.split())
                            _ops_index.append({
                                "name": name,
                                "code": code,
                                "nospace": nospace,
                                "tokens": tokens,
                                "ntok": len(tokens),
                            })
                            _operator_names[name] = code

                        new_operators = {}

                        def _best_operator_match(raw_value: str):
                            """Return (code, reason) with dynamic sequential assignment for new operators."""
                            # 0️⃣ Empty → 75
                            if pd.isna(raw_value) or str(raw_value).strip() == "":
                                return 75, "empty→75"

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
                                if SequenceMatcher(
                                    None,
                                    norm_name,
                                    _nospace(_norm_ws(known))
                                ).ratio() >= 0.95:
                                    return new_operators[known], "duplicate-new"

                            # Persistent counter for sequential numbering
                            if not hasattr(_best_operator_match, "next_code"):
                                max_code = pd.to_numeric(ops_df["Codigo"], errors="coerce").max()
                                max_code = int(max_code) if pd.notna(max_code) else 0
                                _best_operator_match.next_code = max_code + 1

                            new_code = _best_operator_match.next_code
                            _best_operator_match.next_code += 1

                            new_operators[raw_value] = new_code
                            _operator_names[raw_value] = new_code
                            return new_code, "new-operator"

                        def convert_operador(value):
                            code, _reason = _best_operator_match(value)
                            return code

                        before_unique_ops = df["Operador"].nunique(dropna=False)
                        df["Operador"] = df["Operador"].apply(convert_operador)
                        after_unique_ops = df["Operador"].nunique(dropna=False)

                        # Show new operators, if any
                        if new_operators:
                            new_ops_df = pd.DataFrame(
                                [{"Nombre": k, "Codigo": v} for k, v in new_operators.items()]
                            )
                            updated_ops = pd.concat(
                                [ops_df[["Nombre", "Codigo"]], new_ops_df], ignore_index=True
                            )
                            steps_done.append(
                                f"🆕 New operators detected: {len(new_operators)} "
                                f"(unique Operador count: {before_unique_ops} → {after_unique_ops})."
                            )
                            st.markdown("**🆕 New operators found during processing:**")
                            st.dataframe(new_ops_df, use_container_width=True)
                        else:
                            updated_ops = ops_df[["Nombre", "Codigo"]].copy()
                            steps_done.append("✅ All operators matched existing records — no new operators added.")

                except Exception as e:
                    steps_done.append(f"⚠️ Operator mapping error: {e}")
            else:
                if "Operador" not in df.columns:
                    steps_done.append("⚠️ Column 'Operador' not found — operator mapping skipped.")
                else:
                    steps_done.append("⚠️ No operators mapping file uploaded — 'Operador' left unchanged.")

            # STEP 11 – Modo de perforacion mapping
            if "Modo de perforacion" in df.columns:
                df["Modo de perforacion"] = df["Modo de perforacion"].replace({
                    "Manual": 1,
                    "Autonomous": 2,
                    "Teleremote": 3
                })
                steps_done.append("✅ Mapped 'Modo de perforacion' to standardized codes (Manual=1, Autonomous=2, Teleremote=3).")
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
        st.subheader("💾 Export Cleaned AUTONOMÍA File")

        option = st.radio(
            "Choose download option:",
            ["⬇️ Download All Columns", "🧩 Download Selected Columns"]
        )

        if option == "⬇️ Download All Columns":
            export_df = df
        else:
            selected_columns = st.multiselect(
                "Select columns (drag to reorder):",
                options=list(df.columns),
                default=list(df.columns)
            )
            export_df = df[selected_columns] if selected_columns else df

        # Excel + CSV for main data
        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        csv_buffer = io.StringIO()
        export_df.to_csv(csv_buffer, index=False)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Cleaned Excel",
                excel_buffer,
                file_name="Escondida_Autonomia_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📗 Download Cleaned CSV",
                csv_buffer.getvalue(),
                file_name="Escondida_Autonomia_Cleaned.csv",
                mime="text/csv",
                use_container_width=True
            )

        # ==========================================================
        # DOWNLOAD UPDATED OPERATORS (if available)
        # ==========================================================
        if updated_ops is not None:
            st.markdown("---")
            st.subheader("💾 Export Updated Operators Mapping")

            ops_buffer = io.BytesIO()
            updated_ops.to_excel(ops_buffer, index=False, engine="openpyxl")
            ops_buffer.seek(0)

            today_str = datetime.now().strftime("%d_%m_%Y")
            ops_filename = f"ES_Operators_{today_str}.xlsx"

            st.download_button(
                "📘 Download Updated Operators Excel",
                ops_buffer,
                file_name=ops_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi -")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

else:
    st.info("📂 Please upload the AUTONOMÍA file (and optionally the Operators mapping file) to begin.")
