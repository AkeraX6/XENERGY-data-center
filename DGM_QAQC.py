import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning and validation of QAQC drilling data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Dashboard
if st.button("⬅️ Back to Menu", key="back_dgmqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_file = st.file_uploader("📤 Upload your Excel file", type=["xlsx", "xls"])

if uploaded_file is not None:
    # --- READ FILE ---
    df = pd.read_excel(uploaded_file)

    # --- DISPLAY BEFORE DATA ---
    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    # ==================================================
    # CLEANING STEPS — SINGLE EXPANDER
    # ==================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):
        steps_done = []

        # STEP 1 – Extract Expansion and Level from Blast
        if "Blast" in df.columns:
            df["Expansion"] = df["Blast"].astype(str).str.extract(r"F0*(\d+)", expand=False)
            df["Level"] = df["Blast"].astype(str).str.extract(r"B(\d{3,4})", expand=False)

            # Place next to Blast
            cols = list(df.columns)
            if all(c in cols for c in ["Blast", "Expansion", "Level"]):
                blast_idx = cols.index("Blast")
                cols.remove("Expansion")
                cols.remove("Level")
                cols[blast_idx + 1:blast_idx + 1] = ["Expansion", "Level"]
                df = df[cols]

            steps_done.append("✅ Extracted 'Expansion' and 'Level' columns from Blast.")
        else:
            steps_done.append("❌ Column 'Blast' not found.")

        # STEP 2 – Remove invalid Density
        if "Density" in df.columns:
            before = len(df)
            df = df[~df["Density"].isin([None, "-", 0])]
            df = df[df["Density"].notna()]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with invalid or zero Density.")
        else:
            steps_done.append("❌ Column 'Density' not found.")

        # STEP 3 – Remove negative coordinates
        if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
            before = len(df)
          # Convert safely to numeric (non-numeric → NaN)
            df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
            df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")

            df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"], how="any")
            df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]    
            
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with negative or invalid coordinates.")
        else:
            steps_done.append("❌ Missing coordinate columns (Local X/Y).")

        # STEP 4 – Cross-fill Hole Length (Design/Actual)
        if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
            before = len(df)
            df["Hole Length (Design)"] = df["Hole Length (Design)"].replace(0, pd.NA)
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].replace(0, pd.NA)

            df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])

            df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Hole Length values (removed {deleted} empty rows).")
        else:
            steps_done.append("⚠️ Hole Length columns not found.")

        # STEP 5 – Cross-fill Explosive (Design/Actual)
        if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
            before = len(df)
            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].replace(0, pd.NA)
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].replace(0, pd.NA)

            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

            df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Explosive values (removed {deleted} empty rows).")
        else:
            steps_done.append("⚠️ Explosive columns not found.")

        # STEP 6 – Clean Asset column (keep only numbers)
        asset_col = None
        for col in df.columns:
            if "Asset" in col:
                asset_col = col
                break
        if asset_col:
            before = df[asset_col].isna().sum()
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
            after = df[asset_col].isna().sum()
            steps_done.append(f"✅ Cleaned 'Asset' column — converted to numeric ({before - after} values fixed).")
        else:
            steps_done.append("⚠️ 'Asset' column not found.")

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

    # Prepare Excel + CSV
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
            file_name="DGM_QAQC_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="DGM_QAQC_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam -Omar El Kendi-")

else:
    st.info("📂 Please upload an Excel file to begin.")
