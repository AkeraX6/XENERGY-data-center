import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>📊 Mantos Blancos — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning and validation of QAQC drilling data.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Dashboard
if st.button("⬅️ Back to Menu", key="back_mbqaqc"):
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
            before = df["Borehole"].isna().sum()

            def fill_boreholes(group):
                counter = 10000
                new_bh = []
                for val in group["Borehole"]:
                    if pd.isna(val) or val == "":
                        new_bh.append(str(counter))
                        counter += 1
                    else:
                        new_bh.append(val)
                group["Borehole"] = new_bh
                return group

            df = df.groupby("Blast", group_keys=False).apply(fill_boreholes)
            after = df["Borehole"].isna().sum()
            filled = before - after
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

        # STEP 7 – Clean column 'Asset' (keep only numbers)
        if "Asset" in df.columns:
            before_non_numeric = df["Asset"].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
            df["Asset"] = df["Asset"].astype(str).str.extract(r"(\d+)", expand=False)
            df["Asset"] = pd.to_numeric(df["Asset"], errors="coerce")
            after_cleaned = df["Asset"].notna().sum()
            steps_done.append(f"✅ Cleaned column 'Asset' — removed {before_non_numeric} non-numeric entries, kept {after_cleaned} numeric values")
        else:
            steps_done.append("⚠️ Column 'Asset' not found")

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
    st.info("📂 Please upload an Excel file to begin.")




