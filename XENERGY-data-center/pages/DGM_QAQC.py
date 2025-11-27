import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# HEADER
# ==========================================================
st.markdown("""
<h2 style='text-align:center;'>DGM — QAQC Data Filter</h2>
<p style='text-align:center;color:gray;'>Automatic cleaning, merging & validation of QAQC drilling data</p>
<hr>
""", unsafe_allow_html=True)

if st.button("⬅️ Back to Menu"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or multiple QAQC files",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("📂 Please upload at least one file.")
    st.stop()


# Read files function
def read_any_file(file):
    name = file.name.lower()
    try:
        if name.endswith(".csv"):
            sample = file.read(2048).decode("utf-8", errors="ignore")
            file.seek(0)
            sep = ";" if sample.count(";") > sample.count(",") else ","
            return pd.read_csv(file, sep=sep)
        return pd.read_excel(file)
    except:
        return None


dfs = [read_any_file(f) for f in uploaded_files if read_any_file(f) is not None]
if not dfs:
    st.error("❌ No valid files could be read.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)

st.success(f"📌 Merged {len(dfs)} files — {len(df)} rows.")
st.dataframe(df.head(10))


# ==========================================================
# PROCESSING STEPS
# ==========================================================
with st.expander("⚙️ Processing Summary", expanded=True):
    steps = []
    total_deleted = 0

    # STEP 1 - Clean Density
    if "Density" in df.columns:
        before = len(df)
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        df = df.dropna(subset=["Density"])
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"Density cleaned → {deleted} removed")
    else:
        steps.append("⚠️ Density column not found")

    # STEP 2 - Remove invalid coordinates
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"Negative/Invalid coord removed → {deleted} rows")
    else:
        steps.append("⚠️ Missing Local X/Y columns")

    # STEP 3 - Clean Borehole
    borehole_col = "Borehole" if "Borehole" in df.columns else None

    if borehole_col:
        before = len(df)

        # 3.1 Remove AUX & PXX rows
        df = df[~df[borehole_col].astype(str).str.contains(r"\baux\b|^aux|P\d+", flags=re.IGNORECASE, na=False)]

        # 3.2 Extract numeric reference
        def clean_borehole(v):
            v = str(v).lower()
            m = re.search(r"(\d{2,4})", v)  # catch first number group
            return m.group(1) if m else None

        df[borehole_col] = df[borehole_col].apply(clean_borehole)
        df = df.dropna(subset=[borehole_col])

        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"Borehole cleaned → {deleted} removed")
    else:
        steps.append("⚠️ Borehole column not found")

    # STEP 4 - Extract Expansion + Level from Blast
    if "Blast" in df.columns:
        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F0*(\d+)", expand=False)
        df["Level"] = df["Blast"].astype(str).str.extract(r"(\d{3,4})", expand=False)

        # Move near Blast
        cols = list(df.columns)
        idx = cols.index("Blast")
        for c in ["Expansion", "Level"]:
            cols.remove(c)
        cols[idx+1:idx+1] = ["Expansion", "Level"]
        df = df[cols]

        steps.append("Expansion + Level extracted")
    else:
        steps.append("⚠️ Blast column missing")

    # STEP 5 - Cross-fill Hole Length
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df["Hole Length (Design)"] = pd.to_numeric(df["Hole Length (Design)"], errors="coerce")
        df["Hole Length (Actual)"] = pd.to_numeric(df["Hole Length (Actual)"], errors="coerce")

        df["Hole Length (Design)"] = df["Hole Length (Design)"].replace(0, pd.NA).fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].replace(0, pd.NA).fillna(df["Hole Length (Design)"])

        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"Hole Length cross-filled → {deleted} removed")

    # STEP 6 - Cross-fill Explosive
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df["Explosive (kg) (Design)"] = pd.to_numeric(df["Explosive (kg) (Design)"], errors="coerce")
        df["Explosive (kg) (Actual)"] = pd.to_numeric(df["Explosive (kg) (Actual)"], errors="coerce")

        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])

        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps.append(f"Explosive cross-filled → {deleted} removed")

    # Final deleted rows counter
    steps.append(f"🗑 TOTAL deleted rows: {total_deleted}")

    for x in steps:
        st.markdown(f"<div style='padding:6px;background:#ecfff1;border-radius:6px;margin-bottom:6px;'>{x}</div>", unsafe_allow_html=True)


# ==========================================================
# OUTPUT
# ==========================================================
valid_date_col = next((c for c in df.columns if "Date" in c or "Fecha" in c), None)

suffix = ""
if valid_date_col:
    df[valid_date_col] = pd.to_datetime(df[valid_date_col], errors="coerce")
    v = df[valid_date_col].dropna()
    if not v.empty:
        suffix = f"_{v.min().strftime('%d%m%y')}_{v.max().strftime('%d%m%y')}"

export_file = f"DGM_QAQC_Cleaned{suffix}"

st.subheader("📌 Final Clean Data Preview")
st.dataframe(df.head(20), use_container_width=True)

excel = io.BytesIO()
df.to_excel(excel, index=False, engine="openpyxl")
excel.seek(0)

csv = io.StringIO()
df.to_csv(csv, index=False, sep=";")

col1, col2 = st.columns(2)
with col1:
    st.download_button("📘 Download Excel", excel, f"{export_file}.xlsx")
with col2:
    st.download_button("📗 Download CSV", csv.getvalue(), f"{export_file}.csv")

st.caption("Built by Maxam — Omar El Kendi")
