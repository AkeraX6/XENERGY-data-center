import streamlit as st
import pandas as pd
import io
import re

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Upload multiple QAQC files (Excel or CSV). They will be merged, cleaned, and exported as one consolidated file.</p>", unsafe_allow_html=True)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_dgmqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or more QAQC files",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("📂 Please upload at least one Excel or CSV file to begin.")
    st.stop()

# ==========================================================
# LOAD AND MERGE FILES
# ==========================================================
all_dfs = []
for file in uploaded_files:
    try:
        if file.name.lower().endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df["__SourceFile__"] = file.name  # keep track of origin
        all_dfs.append(df)
    except Exception as e:
        st.error(f"❌ Error reading {file.name}: {e}")

if not all_dfs:
    st.error("❌ No valid files could be read. Please check your uploads.")
    st.stop()

# Combine all into one
merged_df = pd.concat(all_dfs, ignore_index=True)
st.success(f"✅ Successfully merged {len(uploaded_files)} files into one dataset.")
st.dataframe(merged_df.head(10), use_container_width=True)

# ==========================================================
# CLEANING STEPS
# ==========================================================
def clean_dataframe(df):
    """Basic cleaning logic specific to QAQC."""
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace('"', "", regex=False)
        .str.replace("’", "'", regex=False)
    )

    # Delete rows with auxiliary boreholes (e.g. AUX01)
    if "Borehole" in df.columns or "Pozo" in df.columns:
        borehole_col = "Borehole" if "Borehole" in df.columns else "Pozo"
        df = df[~df[borehole_col].astype(str).str.contains(r"aux", flags=re.IGNORECASE, na=False)]

    # Remove invalid or missing density values
    for col in df.columns:
        if "densidad" in col.lower() or "density" in col.lower():
            df = df[~df[col].astype(str).str.contains(r"[a-zA-Z\-]", na=False)]
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[df[col] > 0]
            break

    return df

cleaned_df = clean_dataframe(merged_df.copy())

st.markdown("---")
st.subheader("✅ Cleaned & Consolidated Data Preview")
st.dataframe(cleaned_df.head(15), use_container_width=True)
st.success(f"✅ Final dataset: {len(cleaned_df)} rows × {len(cleaned_df.columns)} columns")

# ==========================================================
# EXPORT OPTIONS
# ==========================================================
st.markdown("---")
st.subheader("💾 Export Consolidated File")

# Export buffers
excel_buffer = io.BytesIO()
cleaned_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

csv_buffer = io.StringIO()
cleaned_df.to_csv(csv_buffer, index=False, sep=";")

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel (.xlsx)",
        excel_buffer,
        file_name="DGM_QAQC_Merged_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
with col2:
    st.download_button(
        "📗 Download CSV (.csv)",
        csv_buffer.getvalue(),
        file_name="DGM_QAQC_Merged_Cleaned.csv",
        mime="text/csv",
        use_container_width=True
    )

st.caption("Built by Maxam - Omar El Kendi -")
