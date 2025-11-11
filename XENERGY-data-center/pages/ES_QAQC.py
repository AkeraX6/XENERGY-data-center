import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — QAQC Data Filter</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and preparation of QAQC drilling data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esqaqc"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    file_name = uploaded_file.name.lower()

    # Smart CSV reader with delimiter detection
    def read_csv_smart(file_obj):
        sample = file_obj.read(8192).decode(errors="replace")
        file_obj.seek(0)
        try:
            return pd.read_csv(file_obj, sep=None, engine="python")
        except Exception:
            if sample.count(";") > sample.count(","):
                file_obj.seek(0)
                return pd.read_csv(file_obj, sep=";")
            elif sample.count("\t") > 0:
                file_obj.seek(0)
                return pd.read_csv(file_obj, sep="\t")
            elif sample.count("|") > 0:
                file_obj.seek(0)
                return pd.read_csv(file_obj, sep="|")
            else:
                file_obj.seek(0)
                return pd.read_csv(file_obj)

    # Read file
    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    steps_done = []

    # ==========================================================
    # CLEANING STEPS
    # ==========================================================
    with st.expander("⚙️ See Processing Steps", expanded=False):

        # STEP 1 – Clean invalid Density values
        if "Density" in df.columns:
            before = len(df)
            df["Density_clean"] = pd.to_numeric(df["Density"], errors="coerce")
            df = df[df["Density_clean"].notna() & (df["Density_clean"] > 0)]
            deleted = before - len(df)
            df.drop(columns=["Density_clean"], inplace=True)
            steps_done.append(f"✅ Cleaned Density: removed {deleted} invalid rows (letters, negatives, symbols, or empty).")
        else:
            steps_done.append("❌ Column 'Density' not found in the file.")

        # STEP 2 – Remove negative coordinates
        if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
            before = len(df)
            df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
            deleted = before - len(df)
            steps_done.append(f"✅ Removed {deleted} rows with negative coordinates.")
        else:
            steps_done.append("❌ Missing columns 'Local X (Design)' or 'Local Y (Design)'.")

        # STEP 3 – Extract Level and Phase from Blast
        if "Blast" in df.columns:
            def extract_level(text):
                """Extract Level (4 digits at start of Blast)"""
                if pd.isna(text):
                    return None
                m = re.match(r"(\d{4})", str(text))
                return m.group(1) if m else None

            def extract_phase(text):
                """Extract phase number from N12, PL1S, L05, S04, etc."""
                if pd.isna(text):
                    return None
                txt = str(text).upper()
                m = re.search(r"(?:N|PL|L|S)(\d{1,2})", txt)
                return m.group(1) if m else None

            df["Level"] = df["Blast"].apply(extract_level)
            df["Phase"] = df["Blast"].apply(extract_phase)
        else:
            steps_done.append("❌ Column 'Blast' not found (Level/Phase skipped).")

        # STEP 4 – Parse Borehole (Grid + Borehole), clean, and apply B/C/D transform
        if "Borehole" in df.columns:
            def parse_borehole_keep_letter(val):
                """
                Accepts:
                  5001_255   -> Grid=5001,  BH='255'
                  6001_B267  -> Grid=6001,  BH='B267'
                  3040-C012  -> Grid=3040,  BH='C012'
                  2995 D004  -> Grid=2995,  BH='D004'
                """
                if pd.isna(val) or str(val).strip() == "":
                    return (None, None)
                s = str(val).strip()

                m = re.match(r"^\s*(\d{3,4})[_\-\s]+([A-Za-z]?\d+)\s*$", s)
                if m:
                    return (m.group(1), m.group(2))

                m2 = re.match(r"^\s*([A-Za-z]?\d+)\s*$", s)
                if m2:
                    return (None, m2.group(1))

                nums = re.findall(r"\d+", s)
                if len(nums) >= 1:
                    return (None, nums[-1])
                return (None, None)

            parsed = df["Borehole"].apply(parse_borehole_keep_letter)
            df["Grid"] = parsed.apply(lambda x: x[0])
            df["Borehole"] = parsed.apply(lambda x: x[1])

            # Drop Boreholes with 'aux' or invalid letters
            before_bh = len(df)
            bh_str = df["Borehole"].astype(str)
            mask_aux = bh_str.str.contains(r"aux", case=False, na=False)
            mask_bad = ~bh_str.str.fullmatch(r"[BCD]?\d+", na=False)
            df = df[~(mask_aux | mask_bad)]
            deleted_bh = before_bh - len(df)

            # Apply B/C/D transformation
            def transform_pozo(token):
                s = str(token).strip().upper()
                if s.startswith("B"):
                    return "100000" + s[1:]
                if s.startswith("C"):
                    return "200000" + s[1:]
                if s.startswith("D"):
                    return s[1:]
                return s

            df["Borehole"] = df["Borehole"].apply(transform_pozo)
            df["Borehole"] = pd.to_numeric(df["Borehole"], errors="coerce")
            df = df[df["Borehole"].notna()]
            df["Borehole"] = df["Borehole"].astype(int)

            # Fill missing Boreholes within each Blast
            if "Blast" in df.columns:
                def fill_bh(group):
                    counter = 10000
                    out = []
                    for v in group["Borehole"]:
                        if pd.isna(v):
                            out.append(counter)
                            counter += 1
                        else:
                            out.append(v)
                    group["Borehole"] = out
                    return group
                df = df.groupby("Blast", group_keys=False).apply(fill_bh)

            # Reorder columns
            cols = list(df.columns)
            desired = [c for c in ["Blast", "Level", "Phase", "Grid", "Borehole"] if c in cols]
            others = [c for c in cols if c not in desired]
            df = df[desired + others]

            steps_done.append(f"✅ Borehole parsed & transformed (B/C/D logic). Removed {deleted_bh} invalid AUX/letter rows.")
        else:
            steps_done.append("❌ Column 'Borehole' not found.")

        # STEP 5 – Hole Length cross-fill
        if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
            before = len(df)
            df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
            df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all", inplace=True)
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Hole Length data (removed {deleted} rows).")
        else:
            steps_done.append("⚠️ Hole Length columns not found.")

        # STEP 6 – Explosive cross-fill
        if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
            before = len(df)
            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
            df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all", inplace=True)
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Explosive data (removed {deleted} rows).")
        else:
            steps_done.append("⚠️ Explosive columns not found.")

        # STEP 7 – Clean Asset column
        asset_col = next((c for c in df.columns if "Asset" in c), None)
        if asset_col:
            before_non_numeric = df[asset_col].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            steps_done.append(f"✅ Cleaned '{asset_col}' column (removed {before_non_numeric} non-numeric entries).")
        else:
            steps_done.append("⚠️ 'Asset' column not found.")

        # --- Display Steps ---
        for s in steps_done:
            st.markdown(
                f"<div style='background:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{s}</span></div>",
                unsafe_allow_html=True
            )

    # ==========================================================
    # AFTER CLEANING
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    opt = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])
    if opt == "⬇️ Download All Columns":
        export_df = df
    else:
        sel_cols = st.multiselect("Select columns:", list(df.columns), default=list(df.columns))
        export_df = df[sel_cols] if sel_cols else df

    # Prepare download buffers
    excel_buf = io.BytesIO()
    export_df.to_excel(excel_buf, index=False, engine="openpyxl")
    excel_buf.seek(0)

    csv_buf = io.StringIO()
    export_df.to_csv(csv_buf, index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📘 Download Excel File", excel_buf, "Escondida_QAQC_Cleaned.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with col2:
        st.download_button("📗 Download CSV File", csv_buf.getvalue(), "Escondida_QAQC_Cleaned.csv",
                           mime="text/csv", use_container_width=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")









