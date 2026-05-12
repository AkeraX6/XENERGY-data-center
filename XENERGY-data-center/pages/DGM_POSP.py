import streamlit as st
import pandas as pd
import io
import re

# ============================================================================
# PAGE HEADER
# ============================================================================
st.markdown(
    "<h2 style='text-align:center;'>📍 DGM — Shovle Position Data Processor</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>EquipmentId, Day, Month, Year, Hour, X, Y, Z.</p>", unsafe_allow_html=True)
st.markdown("---")

# ============================================================================
# FILE UPLOAD
# ============================================================================
uploaded_files = st.file_uploader(
    "📤 Upload Excel files (headers start in row 2)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        try:
            # Read with header in second row
            df = pd.read_excel(uploaded_file, header=1)
            all_dfs.append(df)
        except Exception as e:
            st.error(f"❌ Error reading file {uploaded_file.name}: {e}")

    # Merge all files vertically
    df = pd.concat(all_dfs, ignore_index=True)
    st.info(f"📂 Loaded {len(uploaded_files)} files — Total rows: {len(df)}")

    st.subheader("📄 Original Data Preview")
    st.dataframe(df.head(10), use_container_width=True)

    # ============================================================================
    # PROCESSING
    # ============================================================================
    st.markdown("---")
    st.subheader("⚙️ Processing Steps")

    steps_done = []

    # Step 1 — Convert EquipmentId
    if "EquipmentId" in df.columns:
        df["EquipmentId"] = df["EquipmentId"].replace({"PA_01": 1, "PA_02": 2})
        steps_done.append("✅ Converted EquipmentId (PA_01 → 1, PA_02 → 2)")
    else:
        steps_done.append("⚠️ Column 'EquipmentId' not found")

    # Step 2 — Convert Timestamp into Day/Month/Year/Hour
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df["Day"] = df["Timestamp"].dt.day
        df["Month"] = df["Timestamp"].dt.month
        df["Year"] = df["Timestamp"].dt.year
        df["Hour"] = df["Timestamp"].dt.hour
        steps_done.append("✅ Extracted Day, Month, Year, Hour from Timestamp")
    else:
        steps_done.append("⚠️ Column 'Timestamp' not found")

    # Step 3 — Handle empty or -1 values in Z column
    if "Z" in df.columns and "PositionZ" in df.columns:
        df.loc[(df["Z"].isna()) | (df["Z"] == -1), "Z"] = df.loc[(df["Z"].isna()) | (df["Z"] == -1), "PositionZ"]
        steps_done.append("✅ Replaced empty/−1 values in Z with PositionZ data")
    elif "Z" in df.columns:
        steps_done.append("⚠️ Column 'PositionZ' not found for Z replacement")

    # Step 4 — Keep only needed columns
    keep_cols = ["EquipmentId", "Day", "Month", "Year", "Hour", "X", "Y", "Z"]
    existing_cols = [c for c in keep_cols if c in df.columns]
    df_final = df[existing_cols]

    steps_done.append(f"✅ Kept only columns: {', '.join(existing_cols)}")

    # Display steps
    for step in steps_done:
        st.markdown(
            f"<div style='background-color:#e8f8f0;padding:8px;border-radius:6px;margin-bottom:6px;'>{step}</div>",
            unsafe_allow_html=True
        )

    # ============================================================================
    # RESULT PREVIEW
    # ============================================================================
    st.markdown("---")
    st.subheader("✅ Final Processed Data (Preview)")
    st.dataframe(df_final.head(20), use_container_width=True)
    st.success(f"Final dataset: {len(df_final)} rows × {len(df_final.columns)} columns")

    # ============================================================================
    # DOWNLOAD SECTION
    # ============================================================================
    excel_buffer = io.BytesIO()
    df_final.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    txt_buffer = io.StringIO()
    df_final.to_csv(txt_buffer, index=False, header=False, sep="\t")

    st.markdown("---")
    st.subheader("💾 Download Processed File")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel",
            excel_buffer,
            file_name="DGM_POSP_Result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📄 Download TXT",
            txt_buffer.getvalue(),
            file_name="DGM_POSP_Result.txt",
            mime="text/plain",
            use_container_width=True
        )

    # ============================================================================
    # DATA QUALITY CHECK
    # ============================================================================
    st.markdown("---")
    st.subheader("🔍 Data Quality Check")

    if st.button("▶️ Run Quality Check", use_container_width=True, key="dgm_posp_qc"):
        total_rows = len(df_final)

        if total_rows == 0:
            st.error("❌ No data to check — the dataset is empty after cleaning.")
        else:
            issues_found = False
            report_lines = []

            for col in df_final.columns:
                col_issues = []

                empty_count = int(df_final[col].isna().sum() + (df_final[col].astype(str).str.strip() == "").sum())
                if empty_count > 0:
                    col_issues.append(f"**{empty_count}** empty value(s)")

                non_empty = df_final[col].dropna().astype(str).str.strip()
                non_empty = non_empty[non_empty != ""]

                if len(non_empty) > 0:
                    text_mask = non_empty.apply(lambda x: bool(re.search(r"[A-Za-z]", str(x))))
                    text_count = int(text_mask.sum())
                else:
                    text_count = 0
                if text_count > 0:
                    col_issues.append(f"**{text_count}** cell(s) contain text/letters")

                if len(non_empty) > 0:
                    special_mask = non_empty.apply(lambda x: bool(re.search(r"[^0-9eE.\-+\s]", str(x))))
                    special_count = int(special_mask.sum())
                else:
                    special_count = 0
                if special_count > 0:
                    examples = non_empty[special_mask].head(3).tolist()
                    col_issues.append(f"**{special_count}** cell(s) with special characters (e.g. {examples})")

                if col_issues:
                    issues_found = True
                    report_lines.append(f"⚠️ **{col}**: " + " | ".join(col_issues))
                else:
                    report_lines.append(f"✅ **{col}**: OK ({total_rows} values, all numeric)")

            if not issues_found:
                st.success("✅ All columns are clean — no empty values, no text, no special characters. Ready to download!")
            else:
                st.warning("⚠️ Some columns have issues. Review the report below:")

            for line in report_lines:
                st.markdown(line)

else:
    st.info("📂 Please upload one or more Excel files to start.")

