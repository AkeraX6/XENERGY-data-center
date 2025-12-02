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

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload one or multiple QAQC files (Excel/CSV)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key="QAQC_upload"
)

if not uploaded_files:
    st.info("📂 Please upload at least one Excel or CSV file to begin.")
    st.stop()

# ==================================================
# FILE READER
# ==================================================
def read_any_file(file):
    name = file.name.lower()
    try:
        if name.endswith(".csv"):
            sample = file.read(2048).decode("utf-8", errors="ignore")
            file.seek(0)
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(file, sep=sep)
        else:
            df = pd.read_excel(file)
        return df
    except Exception as e:
        st.error(f"❌ Error reading {file.name}: {e}")
        return None

dfs = [read_any_file(f) for f in uploaded_files]
dfs = [d for d in dfs if d is not None]
if not dfs:
    st.error("❌ No valid files were processed.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)
st.success(f"📌 Merged {len(dfs)} files → Total rows: {len(df)}")
st.dataframe(df.head(10), use_container_width=True)

# ==================================================
# CLEANING STEPS
# ==================================================
with st.expander("⚙️ Processing Steps"):
    steps_done = []
    total_deleted = 0

    # STEP 1 – Clean Density
    if "Density" in df.columns:
        before = len(df)
        df = df[df["Density"].astype(str).str.match(r"^\d+(\.\d+)?$", na=False)]
        df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density"] > 0]
        deleted = before - len(df)
        total_deleted += deleted
        steps_done.append(f"Density cleaned → {deleted} removed")
    else:
        steps_done.append("⚠️ Missing Density column")

    # STEP 2 – Remove negative coordinates
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = pd.to_numeric(df["Local X (Design)"], errors="coerce")
        df["Local Y (Design)"] = pd.to_numeric(df["Local Y (Design)"], errors="coerce")
        df = df.dropna(subset=["Local X (Design)", "Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        total_deleted += deleted
        steps_done.append(f"Negative coordinates removed → {deleted} rows deleted")
    else:
        steps_done.append("⚠️ Missing coordinate columns")

    # STEP 3 – Borehole cleanup
    bore_col = next((c for c in df.columns if "bore" in c.lower() or "pozo" in c.lower()), None)

    if bore_col:
        before = len(df)

        # Remove AUX rows
        df = df[~df[bore_col].astype(str).str.contains(r"\baux\b|\baux\d+|\bp\d+|\ba\d{1,2}\b", flags=re.IGNORECASE, na=False)]

        # Extract final numeric part such as:
        # 01A_402 → 402, 308_4 → 308, 11C_866 → 866, A.15 → 15, a20 → 20, etc.
        df[bore_col] = df[bore_col].astype(str)
        df[bore_col] = df[bore_col].str.extract(r"(\d+)", expand=False)

        df[bore_col] = pd.to_numeric(df[bore_col], errors="coerce")
        df = df.dropna(subset=[bore_col])

        deleted = before - len(df)
        total_deleted += deleted
        steps_done.append(f"Borehole cleaned → {deleted} rows removed/fixed")
    else:
        steps_done.append("⚠️ Borehole column not found")

    # STEP 4 – Expansion / Level extraction
    if "Blast" in df.columns:
        df["Expansion"] = df["Blast"].astype(str).str.extract(r"F[_-]*0*(\d+)", expand=False)

        # Fix extraction for values like "_238_" "238B_" "B238_"
        df["Level"] = (
            df["Blast"]
            .astype(str)
            .str.extract(r"(2\d{3}|3\d{3}|4\d{3})", expand=False)
        )

        # Reorder columns next to Blast
        col_list = list(df.columns)
        b_idx = col_list.index("Blast")
        for c in ["Expansion", "Level"]:
            if c in col_list:
                col_list.remove(c)
        col_list[b_idx + 1:b_idx + 1] = ["Expansion", "Level"]
        df = df[col_list]

        steps_done.append("Expansion + Level extracted and reordered")
    else:
        steps_done.append("⚠️ Missing Blast column")

    # STEP 5 – Cross-fill Hole Length
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        for c in ["Hole Length (Design)", "Hole Length (Actual)"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
        df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
        df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps_done.append(f"Hole Length cross-filled → {deleted} deleted")
    else:
        steps_done.append("⚠️ Hole Length column missing")

    # STEP 6 – Cross-fill Explosive
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        for c in ["Explosive (kg) (Design)", "Explosive (kg) (Actual)"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
        df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
        df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
        deleted = before - len(df)
        total_deleted += deleted
        steps_done.append(f"Explosive cross-filled → {deleted} deleted")
    else:
        steps_done.append("⚠️ Explosive column missing")

    # STEP 7 – Asset cleaning + Fix missing → 266
    asset_col = next((c for c in df.columns if "asset" in c.lower()), None)
    if asset_col:
        df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
        missing = df[asset_col].isna().sum()
        df[asset_col] = df[asset_col].fillna(266)
        if missing > 0:
            steps_done.append(f"Asset fixed → {missing} rows filled with 266")
    else:
        steps_done.append("⚠️ Asset column missing")

    # STEP 8 – Water level fix
    water_col = next((c for c in df.columns if "water" in c.lower() or "agua" in c.lower()), None)
    if water_col:
        df[water_col] = pd.to_numeric(df[water_col], errors="coerce")
        missing = df[water_col].isna().sum()
        df[water_col] = df[water_col].fillna(0)
        if missing > 0:
            steps_done.append(f"Water Level fixed → {missing} rows set to 0")
    else:
        steps_done.append("⚠️ Water Level column missing")

    steps_done.append(f"🧹 TOTAL rows removed during cleaning: {total_deleted}")

    for s in steps_done:
        st.markdown(f"<div style='background:#e8f8f0;border-radius:6px;padding:6px;margin-bottom:4px;'>{s}</div>",
                    unsafe_allow_html=True)

# ==================================================
# SHOW RESULTS
# ==================================================
st.markdown("---")
st.subheader("📌 Final Clean Dataset Preview")
st.dataframe(df.head(20), use_container_width=True)
st.success(f"📊 Clean dataset: {len(df)} rows × {len(df.columns)} columns")

# ==================================================
# DATE RANGE FOR FILE NAME
# ==================================================
date_col = next((c for c in df.columns if "Date" in c or "Fecha" in c), None)
file_suffix = ""
if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = df[date_col].dropna()
    if not valid_dates.empty:
        min_date = valid_dates.min().strftime("%d%m%y")
        max_date = valid_dates.max().strftime("%d%m%y")
        file_suffix = f"_{min_date}_{max_date}"

file_stem = f"DGM_QAQC_Cleaned{file_suffix}"

# ==================================================
# DOWNLOAD SECTION
# ==================================================
st.markdown("---")
st.subheader("💾 Export Cleaned File")

opt = st.radio("Choose download format:", ["Excel", "TXT"], key="QAQC_format")

export_df = df

if opt == "Excel":
    buffer = io.BytesIO()
    export_df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    st.download_button(
        "📘 Download Excel File",
        buffer,
        file_name=f"{file_stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
else:
    txt = export_df.to_csv(index=False, sep=";", encoding="utf-8")
    st.download_button(
        "📄 Download TXT File",
        txt,
        file_name=f"{file_stem}.txt",
        mime="text/plain",
        use_container_width=True
    )

st.caption("Built by Maxam – Omar El Kendi")




