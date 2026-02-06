import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Block Models Converter</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Convert block model files with automatic column extraction and expansion detection.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esmob"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        # Get filename for expansion extraction
        filename = uploaded_file.name
        
        # ==========================================================
        # FUNCTION: EXTRACT EXPANSION FROM FILENAME
        # ==========================================================
        def extract_expansion(filename):
            """
            Extract expansion number from filename:
            - n17a_feb26 = 17
            - n17b_feb26 = 170
            - pl1_feb26 = 1
            - pl1s_feb26 = 101
            - S04_feb26 = 4
            """
            filename_lower = filename.lower()
            
            # Pattern for n17a or n17b
            match = re.search(r'n(\d+)([ab])', filename_lower)
            if match:
                num = int(match.group(1))
                letter = match.group(2)
                if letter == 'a':
                    return num
                elif letter == 'b':
                    return num * 10  # 17b becomes 170
            
            # Pattern for pl1s or pl1
            match = re.search(r'pl(\d+)(s?)', filename_lower)
            if match:
                num = int(match.group(1))
                has_s = match.group(2)
                if has_s == 's':
                    return 100 + num  # pl1s becomes 101
                else:
                    return num  # pl1 becomes 1
            
            # Pattern for S04, s04, etc (any letter followed by numbers)
            match = re.search(r'[a-z](\d+)', filename_lower)
            if match:
                return int(match.group(1))
            
            # Default if no pattern matches
            return None
        
        expansion_number = extract_expansion(filename)
        
        # ==========================================================
        # READ FILE
        # ==========================================================
        if filename.endswith('.csv'):
            # Read CSV - headers are in row 1 (index 0)
            df_full = pd.read_csv(uploaded_file, header=0)
        else:
            # Read Excel - headers are in row 1 (index 0)
            df_full = pd.read_excel(uploaded_file, header=0)
        
        st.subheader("📄 Original Data (Before Processing)")
        st.dataframe(df_full.head(10), use_container_width=True)
        st.info(f"📏 Total rows: {len(df_full)}")
        
        steps_done = []
        
        # ==========================================================
        # PROCESSING STEPS
        # ==========================================================
        with st.expander("⚙️ See Processing Steps", expanded=True):
            
            # STEP 1 – Extract Date from Row 2 (Variable descriptions row)
            date_found = None
            month_num = None
            year_num = None
            
            # Row 2 in the file is index 0 in the data (first row after header)
            if len(df_full) > 0:
                row2 = df_full.iloc[0]  # First data row (Variable descriptions)
                for cell in row2:
                    if pd.notna(cell):
                        cell_str = str(cell)
                        # Try to find date pattern like "28-Oct-2025" or similar
                        date_patterns = [
                            r'(\d{1,2})[/-]([A-Za-z]{3})[/-](\d{4})',  # 28-Oct-2025
                            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',      # 28/10/2025 or 28-10-2025
                            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',      # 2025-10-28
                        ]
                        
                        for pattern in date_patterns:
                            match = re.search(pattern, cell_str)
                            if match:
                                try:
                                    # First pattern: day-month_name-year
                                    if len(match.groups()) == 3 and match.group(2).isalpha():
                                        day = match.group(1)
                                        month_str = match.group(2)
                                        year = match.group(3)
                                        
                                        # Convert month name to number
                                        month_map = {
                                            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                                            'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                                            'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                                        }
                                        month_num = month_map.get(month_str.lower()[:3])
                                        year_num = int(year)
                                        date_found = f"{day}-{month_str}-{year}"
                                        break
                                    
                                    # Second pattern: day/month/year or day-month-year
                                    elif len(match.groups()) == 3 and match.group(1).isdigit() and match.group(2).isdigit():
                                        if len(match.group(1)) == 4:  # Year first (2025-10-28)
                                            year_num = int(match.group(1))
                                            month_num = int(match.group(2))
                                            day = match.group(3)
                                        else:  # Day first (28/10/2025)
                                            day = match.group(1)
                                            month_num = int(match.group(2))
                                            year_num = int(match.group(3))
                                        date_found = f"{day}/{month_num}/{year_num}"
                                        break
                                except:
                                    continue
                        
                        if date_found:
                            break
            
            if date_found:
                steps_done.append(f"✅ Date found in row 2: {date_found} (Month: {month_num}, Year: {year_num})")
            else:
                steps_done.append("⚠️ No date found in row 2. Month and Year columns will be empty.")
            
            # STEP 2 – Data starts from row 5 (index 3 after header)
            # Rows 1-3 after header are: Variable descriptions, Variable types, Variable defaults
            if len(df_full) > 3:
                # Get the original headers (already read)
                headers = [str(col).strip().lower() for col in df_full.columns]
                
                # Data starts from row 4 (index 3) - skip description, types, defaults rows
                df_data = df_full.iloc[3:].copy()
                df_data.columns = headers
                df_data = df_data.reset_index(drop=True)
                steps_done.append(f"✅ Headers extracted. Data starts from row 5 ({len(df_data)} data rows).")
            else:
                st.error("⚠️ File has insufficient rows. Cannot extract data.")
                st.stop()
            
            # STEP 3 – Select required columns
            required_columns = [
                'centroid_x', 'centroid_y', 'centroid_z', 'litologia', 'alteracion',
                'ucs', 'spi', 'bwi', 'gsi', 'ff', 'rqd', 'cut', 'mtype_op'
            ]
            
            # Find matching columns (case-insensitive)
            found_columns = []
            column_mapping = {}
            
            # Create a lookup dictionary for available columns
            available_cols_lower = {col.lower(): col for col in df_data.columns}
            
            for req_col in required_columns:
                req_col_lower = req_col.lower()
                
                # Try exact match first
                if req_col_lower in available_cols_lower:
                    found_columns.append(req_col)
                    column_mapping[req_col] = available_cols_lower[req_col_lower]
                else:
                    # Try partial match (columns might have variations like ed_cut for cut)
                    for avail_col_lower, avail_col_orig in available_cols_lower.items():
                        # Check if the required column is contained in the available column
                        if req_col_lower in avail_col_lower or avail_col_lower in req_col_lower:
                            found_columns.append(req_col)
                            column_mapping[req_col] = avail_col_orig
                            break
                        # Check without underscores
                        if req_col_lower.replace('_', '') in avail_col_lower.replace('_', ''):
                            found_columns.append(req_col)
                            column_mapping[req_col] = avail_col_orig
                            break
            
            # Show available columns for debugging
            st.info(f"📋 Available columns in file: {', '.join(df_data.columns.tolist())}")
            
            if len(found_columns) == 0:
                st.error("⚠️ None of the required columns were found in the file.")
                st.stop()
            
            # Extract only the found columns
            output_df = pd.DataFrame()
            for req_col in required_columns:
                if req_col in column_mapping:
                    actual_col = column_mapping[req_col]
                    output_df[req_col] = df_data[actual_col].values
                else:
                    output_df[req_col] = pd.NA
            
            steps_done.append(f"✅ Extracted {len(found_columns)} out of {len(required_columns)} required columns.")
            if len(found_columns) < len(required_columns):
                missing = [col for col in required_columns if col not in column_mapping]
                steps_done.append(f"⚠️ Missing columns (filled with NA): {', '.join(missing)}")
            
            # STEP 4 – Add Expansion column
            if expansion_number is not None:
                output_df['Expansion'] = expansion_number
                steps_done.append(f"✅ Expansion number extracted from filename: {expansion_number}")
            else:
                output_df['Expansion'] = pd.NA
                steps_done.append(f"⚠️ Could not extract expansion number from filename: {filename}")
            
            # STEP 5 – Add Month and Year columns
            output_df['Month'] = month_num if month_num else pd.NA
            output_df['Year'] = year_num if year_num else pd.NA
            steps_done.append(f"✅ Added Month and Year columns to output.")
            
            # Display all steps
            for step in steps_done:
                st.markdown(
                    f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )
        
        # ==========================================================
        # AFTER PROCESSING
        # ==========================================================
        st.markdown("---")
        st.subheader("✅ Processed Data Preview")
        st.dataframe(output_df.head(20), use_container_width=True)
        st.success(f"✅ Final dataset: {len(output_df)} rows × {len(output_df.columns)} columns.")
        
        # ==========================================================
        # DOWNLOAD SECTION
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Processed File")
        
        # Prepare Excel download
        excel_buffer = io.BytesIO()
        output_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)
        
        # Prepare CSV download
        csv_buffer = io.StringIO()
        output_df.to_csv(csv_buffer, index=False)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel File",
                excel_buffer,
                file_name="Escondida_BlockModel_Processed.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📗 Download CSV File",
                csv_buffer.getvalue(),
                file_name="Escondida_BlockModel_Processed.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi")
        
    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")
