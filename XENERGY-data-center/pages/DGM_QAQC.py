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
st.markdown("<p style='text-align:center; color:gray;'>Upload multiple QAQC files (Excel or CSV). All will be merged, cleaned, and exported as one consolidated dataset.</p>", unsafe_allow_html=True)
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
# FILE READING FUNCTION
# ==========================================================
def read_any_file(file):
    """Reads CSV or Excel automatically, detecting delimiter if CSV."""
    name = file.name.lower()
    try:
        if name.endswith(".csv"):
            # Try auto-detect separator
            sample = file.read(2048).decode("utf-8", errors="ignore")
            file.seek(0)  # reset file pointer
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(file, sep=sep)
        else:
            df = pd.read_excel(file)
        df["__SourceFile__"] = file.name
        return df
    except Exception as e:
        st.error(f"❌ Error reading {file.name}: {e}")
        return None

# ==========================================================
# LOAD & MERGE FILES
# ==========================================================
all_dfs = [read_any_file(f) for f in uploaded_files if f is not None]
all_dfs = [df for df in all_dfs if df is not None]

if not all_dfs:
    st.error("❌ No valid files could be read. Please check your uploads.")
    st.stop()

merged_df = pd.concat(all_dfs, ignore_index=True)
st.success(f"✅ Successfully merged {len(uploaded_files)} files into one dataset.")
st.dataframe(merged_df.head(10), use_container_width=True)

# ==========================================================
# CLEANING FUNCTION
# ==========================================================
def clean_dataframe(df):
    """Cleans QAQC dataset with consistent logic."""
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace('"', "", regex=False)
        .str.replace("’", "'", regex=False)
    )

    # Delete rows with auxiliary boreholes (e.g. AUX01)
    borehole_col = next((c for c in df.columns if c.lower() in ["borehole", "pozo", "id pozo"]), None)
    if borehole_col:
        df = df[~df[borehole_col].astype(str).str.contains(r"aux", flags=re.IGNORECASE, na=False)]

    # Remove invalid or missing density values
    density_col = next((c for c in df.columns if "densidad" in c.lower() or "density" in c.lower()), None)
    if density_col:
        df = df[~df[density_col].astype(str).str.contains(r"[a-zA-Z\-]", na=False)]
        df[density_col] = pd.to_numeric(df[density_col], errors="coerce")
        df = df[df[density_col] > 0]

    return df

# Clean merged dataset
cleaned_df = clean_dataframe(merged_df.copy())

# ==========================================================
# PREVIEW
# ==========================================================
st.markdown("---")
st.subheader("✅ Cleaned & Consolidated Data Preview")
st.dataframe(cleaned_df.head(15), use_container_width=True)
st.success(f"✅ Final dataset: {len(cleaned_df)} rows × {len(cleaned_df.columns)} columns")

# ==========================================================
# EXPORT OPTIONS
# ==========================================================
st.markdown("---")
st.subheader("💾 Export Consolidated File")

# Prepare export buffers
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

