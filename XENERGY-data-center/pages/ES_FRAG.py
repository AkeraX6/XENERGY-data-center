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

    # --- Round numeric columns to max 3 decimals, tiny values → 0 ---
    for col in expected_cols:
        df_pivot[col] = pd.to_numeric(df_pivot[col], errors="coerce")
        df_pivot[col] = df_pivot[col].apply(lambda x: 0 if (pd.notna(x) and abs(x) < 0.001) else x)
        df_pivot[col] = df_pivot[col].round(3)

    # ==========================================================
    # SHOW RESULTS
    # ==========================================================
    st.success(f"✅ Processed successfully! Total rows: {len(df_pivot)}")
    st.dataframe(df_pivot.head(20), use_container_width=True)

    # ==========================================================
    # DATA QUALITY CHECK
    # ==========================================================
    st.markdown("---")
    st.subheader("🔍 Data Quality Check")

    if st.button("▶️ Run Quality Check", use_container_width=True, key="frag_qc"):
        total_rows = len(df_pivot)

        if total_rows == 0:
            st.error("❌ No data to check — the dataset is empty.")
        else:
            issues_found = False
            report_lines = []

            for col in df_pivot.columns:
                col_issues = []

                empty_count = int(df_pivot[col].isna().sum() + (df_pivot[col].astype(str).str.strip() == "").sum())
                if empty_count > 0:
                    col_issues.append(f"**{empty_count}** empty value(s)")

                non_empty = df_pivot[col].dropna().astype(str).str.strip()
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

    # ==========================================================
    # DOWNLOAD
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Download Processed Data")

    excel_buffer = BytesIO()
    df_pivot.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    txt_buffer = StringIO()
    df_pivot.to_csv(txt_buffer, sep="\t", index=False, header=False)

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

