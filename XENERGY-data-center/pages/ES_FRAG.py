import streamlit as st
import pandas as pd
import re
from io import StringIO, BytesIO

# ==========================================================
# HEADER
# ==========================================================
st.markdown(
    """
    <h2 style='text-align:center;'> Fragmentation Data Formatter </h2>
    <p style='text-align:center;color:gray;'>Works with both Shovel-path logs and classic CSV formats</p>
    <hr>
    """,
    unsafe_allow_html=True
)

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_files = st.file_uploader("📂 Upload one or multiple CSV/TXT files", type=["csv", "txt"], accept_multiple_files=True)

if uploaded_files:
    all_data = []

    for uploaded_file in uploaded_files:
        lines = uploaded_file.read().decode("utf-8", errors="ignore").strip().splitlines()

        for line in lines:
            line = line.strip()
            if not line or line.lower().startswith("data source"):
                continue  # Skip empty or header lines

            # ✅ Normalize separator to comma
            line = line.replace(";", ",").replace("|", ",")
            parts = [p.strip() for p in line.split(",") if p.strip()]

            # Different formats have 3 or 4 parts
            if len(parts) < 3:
                continue

            # Case 1: With full path
            if "Shovel" in parts[0]:
                raw_id = parts[0]
                code = parts[1]
                timestamp = parts[2]
                value = parts[-1]
            # Case 2: Simple format like 65,P80,24/07/2025 0:01,5.64
            else:
                raw_id = parts[0]
                code = parts[1]
                timestamp = parts[2]
                value = parts[-1]

            # ✅ Extract shovel number (works for both types)
            match = re.search(r"Shovel(\d+)", raw_id, re.IGNORECASE)
            if match:
                number = int(match.group(1))
            else:
                num_match = re.search(r"\b(\d+)\b", raw_id)
                number = int(num_match.group(1)) if num_match else None

            # ✅ Parse timestamp
            try:
                dt = pd.to_datetime(timestamp, dayfirst=True, errors="coerce")
                if pd.isna(dt):
                    continue
                day, month, year = dt.day, dt.month, dt.year
                hour, minute = dt.hour, dt.minute
            except Exception:
                continue

            # ✅ Convert value
            try:
                value = float(str(value).replace(",", "."))
            except:
                value = None

            all_data.append({
                "Number": number,
                "Day": day,
                "Month": month,
                "Year": year,
                "Hour": hour,
                "Minute": minute,
                "Code": code,
                "Value": value
            })

    # ==========================================================
    # CREATE FINAL TABLE
    # ==========================================================
    df = pd.DataFrame(all_data)

    if df.empty:
        st.error("⚠️ No valid data found in uploaded files. Check separators (comma or semicolon).")
        st.stop()

    df_pivot = df.pivot_table(
        index=["Number", "Day", "Month", "Year", "Hour", "Minute"],
        columns="Code",
        values="Value",
        aggfunc="first"
    ).reset_index()

    expected_cols = ["P80", "P50", "P20", "Grueso", "Intermedio", "Fino"]
    for col in expected_cols:
        if col not in df_pivot.columns:
            df_pivot[col] = None

    df_pivot = df_pivot[["Number", "Day", "Month", "Year", "Hour", "Minute"] + expected_cols]

    # ==========================================================
    # SHOW RESULTS
    # ==========================================================
    st.success(f"✅ Processed successfully! Total rows: {len(df_pivot)}")
    st.dataframe(df_pivot.head(20), use_container_width=True)

    # ==========================================================
    # DOWNLOAD
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Download Processed Data")

    excel_buffer = BytesIO()
    df_pivot.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    txt_buffer = StringIO()
    df_pivot.to_csv(txt_buffer, sep="\t", index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name="ES_Fragmentation_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download TXT File",
            txt_buffer.getvalue(),
            file_name="ES_Fragmentation_Cleaned.txt",
            mime="text/plain",
            use_container_width=True
        )

else:
    st.info("📄 Please upload one or more CSV/TXT files to begin.")
