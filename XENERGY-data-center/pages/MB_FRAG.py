import streamlit as st
import pandas as pd
import re
import io
import numpy as np

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>Mantos Blancos — Fragmentation Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning and structuring of MB fragmentation measurement data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_mbfrag"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# HELPER FUNCTIONS
# ==================================================

def read_any_file(uploaded_file):
    """Read CSV or Excel file with proper handling"""
    try:
        if uploaded_file.name.endswith(".csv"):
            # Try reading with different delimiters
            content = uploaded_file.read()
            if b";" in content[:1000]:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, delimiter=";")
            else:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file)
        else:
            return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file {uploaded_file.name}: {e}")
        return None

def normalize_columns(df):
    """Normalize column names by stripping whitespace"""
    df.columns = [str(c).strip() for c in df.columns]
    return df

def to_numeric_safely(series):
    """Convert series to numeric, replacing errors with NaN"""
    return pd.to_numeric(series, errors='coerce')

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload your files (Excel or CSV)", 
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    # --- READ AND MERGE FILES ---
    all_dfs = []
    
    for uploaded_file in uploaded_files:
        temp_df = read_any_file(uploaded_file)
        if temp_df is not None:
            all_dfs.append(temp_df)
    
    if all_dfs:
        # Merge all dataframes
        df = pd.concat(all_dfs, ignore_index=True)
        df = normalize_columns(df)
        
        # --- DISPLAY MERGED BEFORE DATA ---
        st.subheader("📄 Merged Data (Before Cleaning)")
        st.dataframe(df.head(15), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)} (from {len(uploaded_files)} file(s))")

        # ==================================================
        # CLEANING STEPS — SINGLE EXPANDER
        # ==================================================
        with st.expander("⚙️ See Processing Steps", expanded=False):
            steps_done = []
            initial_count = len(df)

            # STEP 1 – Remove rows with empty Ref. X, Ref. Y, or Ref. Z
            coord_cols = ["Ref. X", "Ref. Y", "Ref. Z"]
            existing_coord_cols = [col for col in coord_cols if col in df.columns]
            
            if existing_coord_cols:
                before_count = len(df)
                df = df.dropna(subset=existing_coord_cols, how='any')
                removed_count = before_count - len(df)
                steps_done.append(f"✅ Removed {removed_count} rows with empty coordinates (Ref. X/Y/Z)")
            else:
                steps_done.append("⚠️ Coordinate columns (Ref. X/Y/Z) not found")

            # STEP 2 – Clean Fase column (F17 → 17)
            if "Fase" in df.columns:
                before_sample = df["Fase"].head(3).tolist()
                df["Fase"] = df["Fase"].astype(str).str.replace("F", "", regex=False).str.strip()
                df["Fase"] = to_numeric_safely(df["Fase"])
                steps_done.append(f"✅ Cleaned 'Fase' column: removed 'F' prefix (e.g., {before_sample[0] if before_sample else 'F17'} → {df['Fase'].iloc[0] if len(df) > 0 else '17'})")
            else:
                steps_done.append("⚠️ Column 'Fase' not found")

            # STEP 3 – Clean Equipo column (keep only numbers)
            if "Equipo" in df.columns:
                before_sample = df["Equipo"].head(3).tolist()
                df["Equipo"] = df["Equipo"].astype(str).str.extract(r"(\d+)", expand=False)
                df["Equipo"] = to_numeric_safely(df["Equipo"])
                steps_done.append(f"✅ Cleaned 'Equipo' column: kept only numbers (e.g., {before_sample[0] if before_sample else 'EQ123'} → {df['Equipo'].iloc[0] if len(df) > 0 else '123'})")
            else:
                steps_done.append("⚠️ Column 'Equipo' not found")

            # STEP 4 – Transform MINERALIZACION (Mineral=1, Lastre=2, Marginal=3)
            if "MINERALIZACION" in df.columns:
                df["MINERALIZACION"] = df["MINERALIZACION"].astype(str).str.strip().str.lower()
                mineralizacion_map = {
                    "mineral": 1,
                    "lastre": 2,
                    "marginal": 3
                }
                df["MINERALIZACION"] = df["MINERALIZACION"].map(mineralizacion_map)
                steps_done.append("✅ Transformed 'MINERALIZACION': Mineral→1, Lastre→2, Marginal→3")
            else:
                steps_done.append("⚠️ Column 'MINERALIZACION' not found")

            # STEP 5 – Transform LITOLOGIA with comprehensive mapping
            if "LITOLOGIA" in df.columns:
                df["LITOLOGIA"] = df["LITOLOGIA"].astype(str).str.strip().str.upper()
                
                # Create mapping function with fuzzy matching
                def map_litologia(value):
                    if pd.isna(value) or value == "NAN":
                        return np.nan
                    
                    value = value.upper().strip()
                    
                    # Exact and partial matches
                    if "ANDESITA BASAL" in value or value == "ANDESITA BASAL":
                        return 1
                    elif value == "DACITA" or "DACITA" == value:
                        return 2
                    elif "ANDESITA SUPERIOR" in value or "ANDESITAS SUPERIORES" in value:
                        return 3
                    elif "ANDESITA INTRUSIVA" in value or (value == "ANDESITA" or value == "ANDESITAS"):
                        return 4
                    elif "GRANITO" in value:
                        return 5
                    elif "DIORITA" in value:
                        return 6
                    elif "DIQUE" in value:
                        return 7
                    elif "GRAVA" in value:
                        return 8
                    elif "BRECHA" in value:
                        return 9
                    else:
                        return np.nan
                
                df["LITOLOGIA"] = df["LITOLOGIA"].apply(map_litologia)
                steps_done.append("✅ Transformed 'LITOLOGIA': mapped lithology types to codes (1-9)")
            else:
                steps_done.append("⚠️ Column 'LITOLOGIA' not found")

            # STEP 6 – Fill D20 from D50/2 when empty or "-"
            if "D20" in df.columns and "D50" in df.columns:
                # Convert to numeric
                df["D20"] = to_numeric_safely(df["D20"].replace("-", np.nan))
                df["D50"] = to_numeric_safely(df["D50"])
                
                # Count how many will be filled
                empty_d20_count = df["D20"].isna().sum()
                
                # Fill D20 with D50/2 where D20 is empty
                df.loc[df["D20"].isna(), "D20"] = df.loc[df["D20"].isna(), "D50"] / 2
                
                steps_done.append(f"✅ Filled {empty_d20_count} empty 'D20' values with D50/2")
            else:
                steps_done.append("⚠️ Columns 'D20' or 'D50' not found for filling")

            # STEP 7 – Rename columns for output
            column_mapping = {
                "Ref. Pozo": "Pozo",
                "Ref. X": "X",
                "Ref. Y": "Y",
                "Ref. Z": "Z"
            }
            df = df.rename(columns=column_mapping)
            steps_done.append("✅ Renamed columns: Ref. Pozo→Pozo, Ref. X→X, Ref. Y→Y, Ref. Z→Z")

            # STEP 8 – Select and reorder columns for output
            output_columns = [
                "Fecha fotografias", "Fase", "Banco", "Equipo", "MINERALIZACION", "LITOLOGIA",
                "Pozo", "X", "Y", "Z", "D20", "D25", "D50", "D75", "D80", "D90", "D95", "D99", "n", "Xmax"
            ]
            
            # Select only existing columns
            available_columns = [col for col in output_columns if col in df.columns]
            df = df[available_columns]
            
            steps_done.append(f"✅ Selected output columns ({len(available_columns)} columns)")
            steps_done.append(f"✅ Final dataset: {len(df)} rows (removed {initial_count - len(df)} total)")

            # --- Display all steps in green cards ---
            for step in steps_done:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )

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

        # Prepare Excel + CSV
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel File",
                excel_buffer,
                file_name="MB_FRAG_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📗 Download CSV File",
                csv_buffer.getvalue(),
                file_name="MB_FRAG_Cleaned.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam -Omar El Kendi-")

else:
    st.info("📂 Please upload one or more Excel/CSV files to begin.")
