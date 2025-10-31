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
st.markdown("<p style='text-align:center; color:gray;'>Automated cleaning and preparation of QAQC drilling data.</p>", unsafe_allow_html=True)
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
    # --- READ FILE (Excel or CSV) with smart delimiter detection ---
    file_name = uploaded_file.name.lower()

    def read_csv_smart(file_obj):
        """Detect delimiter automatically for CSVs"""
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

        # STEP 1 – Clean invalid Density values (empty, letters, symbols, negatives, zero)
        if "Density" in df.columns:
            before = len(df)

            # Convert safely to numeric, invalid to NaN
            df["Density_clean"] = pd.to_numeric(df["Density"], errors="coerce")

            # Keep only positive valid numeric values
            df = df[df["Density_clean"].notna()]
            df = df[df["Density_clean"] > 0]

            deleted = before - len(df)
            df = df.drop(columns=["Density_clean"])

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

        # STEP 3 – Extract Expansion and Nivel from Blast
        if "Blast" in df.columns:
            def extract_nivel(text):
                if pd.isna(text):
                    return None
                m = re.search(r"(\d{4})", str(text))
                return m.group(1) if m else None

            def extract_expansion(text):
                if pd.isna(text):
                    return None
                txt = str(text).upper()
                m = re.search(r"[A-Z]{1,3}(\d{1,2})", txt)
                return m.group(1) if m else None

            df["Expansion"] = df["Blast"].apply(extract_expansion)
            df["Nivel"] = df["Blast"].apply(extract_nivel)

            # Move Expansion + Nivel next to Blast
            cols = list(df.columns)
            for c in ["Expansion", "Nivel"]:
                if c in cols:
                    cols.remove(c)
            if "Blast" in cols:
                idx = cols.index("Blast")
                cols[idx + 1:idx + 1] = ["Expansion", "Nivel"]
                df = df[cols]

            steps_done.append("✅ Extracted Expansion and Nivel columns next to Blast.")
        else:
            steps_done.append("❌ Column 'Blast' not found in file.")

        # STEP 4 – Clean and fill Borehole names + apply Pozo transformation
        if "Borehole" in df.columns and "Blast" in df.columns:
            before_empty = df["Borehole"].isna().sum()

            def clean_borehole(val):
                if pd.isna(val) or str(val).strip() == "":
                    return None
                val = str(val).strip()
                if "_" in val:
                    return val.split("_")[-1]
                digits = re.findall(r"\d+", val)
                return digits[-1] if digits else val

            df["Borehole"] = df["Borehole"].apply(clean_borehole)

            def fill_boreholes(group):
                counter = 10000
                new_bh = []
                for val in group["Borehole"]:
                    if pd.isna(val) or val == "":
                        new_bh.append(str(counter))
                        counter += 1
                    else:
                        new_bh.append(val)
                group["Borehole"] = new_bh
                return group

            df = df.groupby("Blast", group_keys=False).apply(fill_boreholes)
            after_empty = df["Borehole"].isna().sum()
            filled = before_empty - after_empty
            steps_done.append(f"✅ Cleaned and filled {filled} missing Borehole values.")

            # --- Apply Pozo-style transformation to Borehole ---
            def transform_pozo(val):
                val = str(val).strip()
                if val.startswith("B"):
                    return "100000" + val[1:]
                elif val.startswith("C"):
                    return "200000" + val[1:]
                elif val.startswith("D"):
                    return val[1:]
                else:
                    return val

            before_transform = df["Borehole"].copy()
            df["Borehole"] = df["Borehole"].apply(transform_pozo)
            changed = (before_transform != df["Borehole"]).sum()
            steps_done.append(f"✅ Transformed {changed} Borehole values (B/C/D logic applied).")

            # --- Remove Boreholes containing 'aux' (in any case/format) ---
            before_aux = len(df)
            df = df[~df["Borehole"].astype(str).str.contains(r"aux", case=False, na=False)]
            deleted_aux = before_aux - len(df)
            steps_done.append(f"🗑️ Removed {deleted_aux} Boreholes containing 'aux'.")

        else:
            steps_done.append("⚠️ 'Borehole' or 'Blast' column missing.")

        # STEP 5 – Hole Length cross-fill
        if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
            before = len(df)
            df["Hole Length (Design)"] = df["Hole Length (Design)"].fillna(df["Hole Length (Actual)"])
            df["Hole Length (Actual)"] = df["Hole Length (Actual)"].fillna(df["Hole Length (Design)"])
            df = df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Hole Length data (removed {deleted} rows).")
        else:
            steps_done.append("⚠️ Hole Length columns not found.")

        # STEP 6 – Explosive cross-fill
        if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
            before = len(df)
            df["Explosive (kg) (Design)"] = df["Explosive (kg) (Design)"].fillna(df["Explosive (kg) (Actual)"])
            df["Explosive (kg) (Actual)"] = df["Explosive (kg) (Actual)"].fillna(df["Explosive (kg) (Design)"])
            df = df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all")
            deleted = before - len(df)
            steps_done.append(f"✅ Cross-filled Explosive data (removed {deleted} rows).")
        else:
            steps_done.append("⚠️ Explosive columns not found.")

        # STEP 7 – Clean Asset column
        asset_col = None
        for col in df.columns:
            if "Asset" in col:
                asset_col = col
                break
        if asset_col:
            before_non_numeric = df[asset_col].astype(str).apply(lambda x: bool(re.search(r"[A-Za-z]", x))).sum()
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            steps_done.append(f"✅ Cleaned '{asset_col}' column (removed {before_non_numeric} non-numeric entries).")
        else:
            steps_done.append("⚠️ 'Asset' column not found.")

        # --- Display Steps ---
        for step in steps_done:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{step}</span></div>",
                unsafe_allow_html=True
            )

    # ==========================================================
    # AFTER CLEANING — RESULTS
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

    option = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])
    if option == "⬇️ Download All Columns":
        export_df = df
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(df.columns),
            default=list(df.columns)
        )
        export_df = df[selected_columns] if selected_columns else df

    # Prepare Excel + CSV
    excel_buffer = io.BytesIO()
    export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    csv_buffer = io.StringIO()
    export_df.to_csv(csv_buffer, index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name="Escondida_QAQC_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col2:
        st.download_button(
            "📗 Download CSV File",
            csv_buffer.getvalue(),
            file_name="Escondida_QAQC_Cleaned.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file to begin.")

