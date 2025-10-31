import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import get_close_matches
import os

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
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        steps_done = []

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
            df["Perforadora"] = df["Perforadora"].astype(str).str[-2:]
            df["turno (dia o noche)"] = df["turno (dia o noche)"].replace({"Dia": 1, "Noche": 2})
            df["Coordinacion"] = df["Coordinacion"].replace({"A": 1, "B": 2, "C": 3, "D": 4})
            steps_done.append("✅ Normalized Perforadora, Turno, and Coordinacion values.")

            # STEP 3 – Split and Extract Banco / Expansion / MallaID
            if "Malla" in df.columns:
                malla_split = df["Malla"].astype(str).str.split("-", expand=True)
                banco = malla_split[0].str[:4]
                expansion = malla_split[1].str.extract(r'(\d+)')
                mallaid = malla_split[2].str[-4:]

                df["Malla"] = mallaid
                df = df.rename(columns={"Malla": "MallaID"})
                col_index = df.columns.get_loc("MallaID")
                df.insert(col_index, "Banco", banco)
                df.insert(col_index + 1, "Expansion", expansion)
                steps_done.append("✅ Extracted Banco, Expansion, and MallaID from Malla column.")
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
                df = df[~df["Pozo"].astype(str).str.contains("Aux", case=False, na=False)]
                df = df[~df["Pozo"].astype(str).str.fullmatch(r'[A-Za-z]+', na=False)]
                df["Pozo_num"] = pd.to_numeric(df["Pozo"], errors="coerce")
                df = df[df["Pozo_num"].notna()]
                df = df[df["Pozo_num"] > 0]
                df["Pozo"] = df["Pozo_num"].astype(int)
                df = df.drop(columns=["Pozo_num"])
                deleted_rows = before_rows - len(df)
                steps_done.append(f"✅ Cleaned Pozo ({deleted_rows} invalid rows deleted).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # STEP 5 – Cross-fill and clean Coordinates (X, Y, Z)
            before_rows = len(df)
            if "Banco" not in df.columns:
                st.warning("⚠️ Banco column missing — Z fallback (Banco+15) will be skipped.")
                df["Banco"] = pd.NA

            # X
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df["Coordenadas diseño X"] = df["Coordenadas diseño X"].fillna(df["Coordenada real inicioX"])
                df["Coordenada real inicioX"] = df["Coordenada real inicioX"].fillna(df["Coordenadas diseño X"])
                mask_x_empty = df["Coordenadas diseño X"].isna() & df["Coordenada real inicioX"].isna()
                df = df[~mask_x_empty]
                df = df[(df["Coordenadas diseño X"] >= 100000) & (df["Coordenada real inicioX"] >= 100000)]

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
                    df.loc[both_empty_mask, "Coordenadas diseño Z"] = pd.to_numeric(df.loc[both_empty_mask, "Banco"], errors="coerce") + 15
                    df.loc[both_empty_mask, "Coordena real inicio Z"] = df.loc[both_empty_mask, "Coordenadas diseño Z"]
            deleted_rows = before_rows - len(df)
            steps_done.append(f"✅ Cleaned Coordinates: filled and removed {deleted_rows} invalid rows.")

            # STEP 6 – Remove empty or zero Largo de pozo real
            if "Largo de pozo real" in df.columns:
                before_len = len(df)
                df = df[df["Largo de pozo real"].notna()]
                df = df[df["Largo de pozo real"] != 0]
                deleted_len = before_len - len(df)
                steps_done.append(f"✅ Removed {deleted_len} empty/zero 'Largo de pozo real' rows.")
            else:
                steps_done.append("⚠️ Column 'Largo de pozo real' not found.")

            # STEP 7 – Categoria de Pozo
            df["Categoria de pozo"] = df["Categoria de pozo"].replace({"Produccion": 1, "Buffer": 2, "Auxiliar": 3})
            steps_done.append("✅ Mapped Categoria de Pozo to numeric codes.")

            # ==========================================================
            # STEP 8 – Operator Mapping (Excel-based fuzzy match)
            # ==========================================================
            operators_path = r"C:\Users\oelkendi\OneDrive - MAXAM\Escritorio\Data_Process\Main Dashboard\Escondida Database\Operators.xlsx"

            def normalize_name(name):
                s = str(name).strip().lower()
                s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
                return re.sub(r'\s+', '', s)

            if os.path.exists(operators_path):
                try:
                    ops = pd.read_excel(operators_path)
                    ops["Nombre"] = ops["Nombre"].astype(str).str.strip()
                    ops["Normalized"] = ops["Nombre"].apply(normalize_name)
                    name_to_code = dict(zip(ops["Normalized"], ops["Codigo"]))
                    next_code_box = [int(pd.to_numeric(ops["Codigo"], errors="coerce").max() or 0) + 1]
                    new_ops = []

                    def get_code(name):
                        if pd.isna(name) or str(name).strip() == "":
                            return 110
                        norm = normalize_name(name)
                        if norm in name_to_code:
                            return name_to_code[norm]
                        match = get_close_matches(norm, list(name_to_code.keys()), n=1, cutoff=0.8)
                        if match:
                            return name_to_code[match[0]]
                        code = next_code_box[0]
                        name_to_code[norm] = code
                        new_ops.append((str(name).strip(), code))
                        next_code_box[0] += 1
                        return code

                    if "Operador" in df.columns:
                        df["Operador"] = df["Operador"].apply(get_code)
                        if new_ops:
                            added_df = pd.DataFrame(new_ops, columns=["Nombre", "Codigo"])
                            st.info(f"🆕 New operators detected: {len(new_ops)}")
                            st.dataframe(added_df, use_container_width=True)
                        else:
                            steps_done.append("✅ All operators matched existing records.")
                    else:
                        steps_done.append("⚠️ Column 'Operador' not found.")
                except Exception as e:
                    steps_done.append(f"⚠️ Operator mapping error: {e}")
            else:
                steps_done.append(f"⚠️ Operators.xlsx not found at {operators_path}")

            # STEP 9 – Modo de perforacion mapping
            df["Modo de perforacion"] = df["Modo de perforacion"].replace({"Manual": 1, "Autonomous": 2, "Teleremote": 3})
            steps_done.append("✅ Mapped Modo de perforacion to standardized codes.")

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
    st.info("📂 Please upload an Excel file to begin.")



