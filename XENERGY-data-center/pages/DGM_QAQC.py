import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — QAQC Data Filter (Multi-file)</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center; color:gray;'>Automatic cleaning, merging, and validation of QAQC drilling data (Excel & CSV supported).</p>", unsafe_allow_html=True)
st.markdown("---")

# Back button
if st.button("⬅️ Back to Menu"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or more QAQC files",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("📂 Upload files to begin.")
    st.stop()

# ==================================================
# SAFE FILE READER
# ==================================================
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

dfs = [read_any_file(f) for f in uploaded_files]
dfs = [x for x in dfs if x is not None]

if len(dfs) == 0:
    st.error("❌ No valid files.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)
st.success(f"✔ Merged {len(dfs)} files — Total rows: {len(df)}")
st.dataframe(df.head(10), use_container_width=True)

# ==================================================
# PROCESSING STEPS
# ==================================================
steps = []
total_removed = 0

# STEP 1 — Clean Density
if "Density" in df.columns:
    before = len(df)
    df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
    df = df[df["Density"] > 0]
    deleted = before - len(df)
    total_removed += deleted
    steps.append(f"Density cleaned → removed {deleted} rows.")

# STEP 2 — Negative / Invalid Coordinates
if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
    before = len(df)
    df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
    df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
    df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
    df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
    deleted = before - len(df)
    total_removed += deleted
    steps.append(f"Removed {deleted} invalid coordinate rows.")

# STEP 3 — Clean Borehole column
bh_col = next((c for c in df.columns if "borehole" in c.lower() or "pozo" in c.lower() or "hole" in c.lower()), None)
if bh_col:
    before = len(df)
    df = df[~df[bh_col].astype(str).str.contains(r"\baux\b|\baux\d+|\ba\d+\b", flags=re.IGNORECASE, na=False)]
    df[bh_col] = df[bh_col].astype(str).str.replace(r"(\d+)_\d+", r"\1", regex=True)
    deleted = before - len(df)
    total_removed += deleted
    steps.append(f"Cleaned Borehole '{bh_col}' → {deleted} AUX rows removed.")

# STEP 4 — Extract Expansion + Level from Blast
if "Blast" in df.columns:
    df["Expansion"] = df["Blast"].astype(str).str.extract(r"F[_\-]?0*(\d+)", expand=False)
    df["Level"] = df["Blast"].astype(str).str.extract(r"(\d{4})", expand=False)

    df["Expansion"] = pd.to_numeric(df["Expansion"], errors="coerce")
    df["Level"] = pd.to_numeric(df["Level"], errors="coerce")

    cols = list(df.columns)
    bi = cols.index("Blast")
    for c in ["Expansion", "Level"]:
        if c in cols: cols.remove(c)
    cols[bi+1:bi+1] = ["Expansion", "Level"]
    df = df[cols]

    steps.append("Extracted & placed Expansion + Level next to Blast.")
else:
    steps.append("⚠ 'Blast' not found.")

# STEP 5 — Cross-fill Hole Length
if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
    before = len(df)
    for c in ["Hole Length (Design)", "Hole Length (Actual)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
    df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
    df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
    deleted = before - len(df)
    total_removed += deleted
    steps.append(f"Cross-filled Hole Length → removed {deleted} empty rows.")

# STEP 6 — Cross-fill Explosive
if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
    before = len(df)
    for c in ["Explosive (kg) (Design)", "Explosive (kg) (Actual)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
    df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
    df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
    deleted = before - len(df)
    total_removed += deleted
    steps.append(f"Cross-filled Explosive → removed {deleted} empty rows.")

# STEP 7 — Clean Asset
asset_col = next((c for c in df.columns if "asset" in c.lower()), None)
if asset_col:
    df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
    df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
    steps.append("Cleaned Asset → extracted only numeric codes.")

# Final step summary
steps.append(f"TOTAL rows removed: {total_removed}")

# ==================================================
# SHOW PROCESSING SUMMARY
# ==================================================
st.markdown("---")
st.subheader("⚙️ Processing Summary")
for s in steps:
    st.success("• " + s)

# ==================================================
# PREVIEW CLEANED DATA
# ==================================================
st.markdown("---")
st.subheader("📊 Cleaned Data Preview")
st.dataframe(df.head(20), use_container_width=True)
st.info(f"Final ➜ {len(df)} rows × {len(df.columns)} columns")

# ==================================================
# DOWNLOAD OPTIONS
# ==================================================
st.markdown("---")
st.subheader("💾 Export Cleaned File")

option = st.radio(
    "Choose:",
    ["⬇️ Download All Columns", "🧩 Download Selected Columns"]
)

if option == "🧩 Download Selected Columns":
    cols = st.multiselect("Select columns:", df.columns, df.columns)
    df_export = df[cols]
else:
    df_export = df

excel = io.BytesIO()
df_export.to_excel(excel, index=False, engine="openpyxl")
excel.seek(0)

txt = io.StringIO()
df_export.to_csv(txt, index=False, sep="\t")

st.download_button(
    "📘 Excel",
    excel,
    file_name="DGM_QAQC_Cleaned.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.download_button(
    "📄 TXT",
    txt.getvalue(),
    file_name="DGM_QAQC_Cleaned.txt",
    mime="text/plain"
)
