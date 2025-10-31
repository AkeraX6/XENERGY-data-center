import streamlit as st
import pandas as pd
import io

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

    # Step 3 — Keep only needed columns
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

    csv_buffer = io.StringIO()
    df_final.to_csv(csv_buffer, index=False)

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
            "📗 Download CSV",
            csv_buffer.getvalue(),
            file_name="DGM_POSP_Result.csv",
            mime="text/csv",
            use_container_width=True
        )

else:
    st.info("📂 Please upload one or more Excel files to start.")

