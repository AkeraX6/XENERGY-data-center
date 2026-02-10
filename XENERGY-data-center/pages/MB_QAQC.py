import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# HELPERS
# ==================================================
def read_any_file(uploaded_file) -> pd.DataFrame:
    """
    Reads Excel or CSV files robustly.
    - Supports CSV with semicolon (;) or comma (,)
    - If a CSV is read as a single column, it tries to split by ;
    """
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        # Try semicolon first (common in Spanish/European exports)
        try:
            df = pd.read_csv(uploaded_file, sep=";", engine="python")
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, engine="python")

        # If still 1 column, try manual split
        if df.shape[1] == 1:
            col0 = str(df.columns[0])
            if ";" in col0:
                uploaded_file.seek(0)
                raw = pd.read_csv(uploaded_file, header=None, engine="python")
                split = raw[0].astype(str).str.split(";", expand=True)

                # First row contains header
                split.columns = split.iloc[0].tolist()
                df = split.iloc[1:].reset_index(drop=True)

        return df

    # Excel
    return pd.read_excel(uploaded_file)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip spaces and normalize column names (keep original names but trimmed)."""
    df.columns = [str(c).strip() for c in df.columns]
    return df


def to_numeric_safely(df: pd.DataFrame, cols: list[str]) -> None:
    """Convert columns to numeric if they exist (handles strings from CSV split)."""
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>📊 Mantos Blancos — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and validation of QAQC drilling data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Dashboard
if st.button("⬅️ Back to Menu", key="back_mbqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload your files (Excel or CSV)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []
    file_info = []

    for uploaded_file in uploaded_files:
        try:
            temp_df = read_any_file(uploaded_file)
            temp_df = normalize_columns(temp_df)

            all_dfs.append(temp_df)
            file_info.append(
                {"name": uploaded_file.name, "rows": len(temp_df), "cols": len(temp_df.columns)}
            )
        except Exception as e:
            st.error(f"⚠️ Error reading {uploaded_file.name}: {e}")

    if not all_dfs:
        st.stop()

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

        # Ensure numeric conversion for key numeric columns (CSV often reads them as strings)
        to_numeric_safely(df, [
            "Density",
            "Local X (Design)",
            "Local Y (Design)",
            "Hole Length (Design)",
            "Hole Length (Actual)",
            "Explosive (kg) (Design)",
            "Explosive (kg) (Actual)",
        ])

        # STEP 1 – Remove rows with empty or zero Density
        if "Density" in df.columns:
            before = len(df)
            df = df[df["Density"].notna()]
            df = df[df["Density"] != 0]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with empty or zero Density")
        else:
            steps_done.append("❌ Column 'Density' not found")

        # STEP 2 – Remove negative coordinates
        if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
            before = len(df)
            df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with negative coordinates")
        else:
            steps_done.append("❌ Missing coordinate columns")

        # STEP 3 – Fill empty Boreholes per Blast
        if "Borehole" in df.columns and "Blast" in df.columns:
            before_missing = df["Borehole"].isna().sum() + (df["Borehole"].astype(str).str.strip() == "").sum()

            def fill_boreholes(group):
                counter = 10000
                new_bh = []
                for val in group["Borehole"]:
                    if pd.isna(val) or str(val).strip() == "":
                        new_bh.append(str(counter))
                        counter += 1
                    else:
                        new_bh.append(val)
                group["Borehole"] = new_bh
                return group

            df = df.groupby("Blast", group_keys=False).apply(fill_boreholes)
            after_missing = df["Borehole"].isna().sum() + (df["Borehole"].astype(str).str.strip() == "").sum()
            filled = before_missing - after_missing
            steps_done.append(f"✅ Filled {filled} missing Borehole values")
        else:
            steps_done.append("❌ Missing 'Borehole' or 'Blast' columns")

        # STEP 4 – Extract Fase and Block (and place after Blast)
        if "Blast" in df.columns:
            df["Fase"] = df["Blast"].astype(str).str.extract(r"F(\d{2})", expand=False)
            df["Block"] = df["Blast"].astype(str).str.extract(r"(?:-|_)(\d{3,4})(?:-|_)", expand=False)

            # Reorder columns to keep Fase and Block next to Blast
            cols = list(df.columns)
            if all(c in cols for c in ["Blast", "Fase", "Block"]):
                blast_index = cols.index("Blast")
                cols.remove("Fase")
                cols.remove("Block")
                cols[blast_index + 1:blast_index + 1] = ["Fase", "Block"]
                df = df[cols]

            steps_done.append("✅ Extracted 'Fase' and 'Block' and positioned them after 'Blast'")
        else:
            steps_done.append("❌ Column 'Blast' not found")

        # STEP 5 – Cross-fill Hole Length
        if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
            before = len(df)
            df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
            df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Hole Length (removed {deleted} empty rows)")
        else:
            steps_done.append("⚠️ Hole Length columns not found")

        # STEP 6 – Cross-fill Explosive
        if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
            before = len(df)
            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
            df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Explosive values (removed {deleted} empty rows)")
        else:
            steps_done.append("⚠️ Explosive columns not found")

        # STEP 6.5 – Cross-fill Stemming (bidirectional)
        if "Stemming (Design)" in df.columns and "Stemming (Actual)" in df.columns:
            # Replace "-", "None", and empty strings with NaN for proper handling
            df["Stemming (Design)"] = df["Stemming (Design)"].replace(["-", "None", ""], pd.NA)
            df["Stemming (Actual)"] = df["Stemming (Actual)"].replace(["-", "None", ""], pd.NA)
            
            # Convert to numeric if needed
            df["Stemming (Design)"] = pd.to_numeric(df["Stemming (Design)"], errors="coerce")
            df["Stemming (Actual)"] = pd.to_numeric(df["Stemming (Actual)"], errors="coerce")
            
            # Count how many will be filled in each direction
            design_empty_before = df["Stemming (Design)"].isna().sum()
            actual_empty_before = df["Stemming (Actual)"].isna().sum()
            
            # Cross-fill: bidirectional
            df["Stemming (Design)"] = df["Stemming (Design)"].fillna(df["Stemming (Actual)"])
            df["Stemming (Actual)"] = df["Stemming (Actual)"].fillna(df["Stemming (Design)"])
            
            design_filled = design_empty_before - df["Stemming (Design)"].isna().sum()
            actual_filled = actual_empty_before - df["Stemming (Actual)"].isna().sum()
            steps_done.append(f"✅ Cross-filled Stemming: Design←Actual ({design_filled} values), Actual←Design ({actual_filled} values)")
        else:
            steps_done.append("⚠️ Stemming columns not found")

        # STEP 7 – Clean column 'Asset' (keep only numbers and fill empty with most repeated)
        # Supports "Asset" or "Asset." or "Asset (R)" etc.
        asset_col = None
        for c in df.columns:
            if str(c).strip().lower().startswith("asset"):
                asset_col = c
                break

        if asset_col:
            # Replace "-" with NaN
            df[asset_col] = df[asset_col].replace("-", pd.NA)
            
            before_non_numeric = df[asset_col].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
            after_cleaned = df[asset_col].notna().sum()
            steps_done.append(
                f"✅ Cleaned column '{asset_col}' — removed {before_non_numeric} non-numeric entries, kept {after_cleaned} numeric values"
            )
            
            # Fill empty/NaN Asset values with most repeated asset
            empty_count = df[asset_col].isna().sum()
            if empty_count > 0:
                most_common_asset = df[asset_col].mode()
                if len(most_common_asset) > 0:
                    most_common_value = most_common_asset.iloc[0]
                    df[asset_col] = df[asset_col].fillna(most_common_value)
                    steps_done.append(
                        f"✅ Filled {empty_count} empty Asset values with most repeated asset: {most_common_value}"
                    )
        else:
            steps_done.append("⚠️ Column 'Asset' not found")

        # STEP 8 – Convert "-" to 0 in Water Level column
        if "Water level" in df.columns:
            before_count = (df["Water level"].astype(str) == "-").sum()
            df["Water level"] = df["Water level"].replace("-", 0)
            df["Water level"] = pd.to_numeric(df["Water level"], errors="coerce")
            steps_done.append(f"✅ Converted {before_count} '-' values to 0 in Water level column")
        else:
            steps_done.append("⚠️ Column 'Water level' not found")

        # STEP 9 – Add Matrix column before Blast Date and move Blast Date to end
        if "Blast Date" in df.columns:
            # Create Matrix column filled with 0
            df["Matrix"] = 0
            
            # Reorder: move Blast Date to the end and Matrix before it
            cols = list(df.columns)
            cols.remove("Blast Date")
            cols.remove("Matrix")
            cols.extend(["Matrix", "Blast Date"])
            df = df[cols]
            
            steps_done.append("✅ Added 'Matrix' column (filled with 0) and moved 'Blast Date' to end")
        else:
            steps_done.append("⚠️ Column 'Blast Date' not found")

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

    # Prepare Excel + CSV in-memory (no filesystem writes)
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
            file_name="MB_QAQC_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="MB_QAQC_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam -Omar El Kendi-")

else:
    st.info("📂 Please upload one or more Excel/CSV files to begin.")



