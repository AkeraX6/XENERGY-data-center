import streamlit as st
import pandas as pd
import re
import io

# ==================================================
# HELPERS
# ==================================================

def read_any_file(uploaded_file) -> pd.DataFrame:
    """Reads Excel or CSV files robustly."""
    name = uploaded_file.name.lower()

    if name.endswith(".csv") or name.endswith(".txt"):
        content = uploaded_file.read()
        if b";" in content[:2000]:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep=";", engine="python")
        elif b"\t" in content[:2000]:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, sep="\t", engine="python")
        else:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, engine="python")

    return pd.read_excel(uploaded_file)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>📊 Mantos Verde — QAQC Data Processor</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and validation of MV QAQC drilling data.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload your files (Excel or CSV)",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True,
)

if uploaded_files:
    all_dfs = []

    for uploaded_file in uploaded_files:
        try:
            temp_df = read_any_file(uploaded_file)
            temp_df = normalize_columns(temp_df)
            all_dfs.append(temp_df)
        except Exception as e:
            st.error(f"⚠️ Error reading {uploaded_file.name}: {e}")

    if not all_dfs:
        st.stop()

    df = pd.concat(all_dfs, ignore_index=True)
    df = normalize_columns(df)

    # --- DISPLAY BEFORE DATA (collapsed) ---
    with st.expander("📄 Original Data (Before Cleaning)", expanded=False):
        st.dataframe(df.head(15), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)} (from {len(uploaded_files)} file(s))")

    # ==================================================
    # CLEANING STEPS
    # ==================================================
    with st.expander("⚙️ See Processing Steps", expanded=True):
        steps = []
        initial_count = len(df)

        # ──────────────────────────────────────────────
        # STEP 1 – Replace standalone "-" with 0 (keep negative numbers like -1)
        # ──────────────────────────────────────────────
        dash_count = 0
        for col in df.columns:
            mask = df[col].astype(str).str.strip().isin(["-", "–", "—"])
            dash_count += mask.sum()
            df.loc[mask, col] = 0
        steps.append(f"✅ Replaced {dash_count} standalone dash values ('-') with 0 (negative numbers kept)")

        # ──────────────────────────────────────────────
        # STEP 1b – Map Pit names to numeric codes
        # ──────────────────────────────────────────────
        if "Pit" in df.columns:
            # Ordered list: check substring matches (first match wins)
            pit_rules = [
                ("rebosadero", 950),
                ("dumpsur", 3),
                ("franko", 3),
                ("celso", 6),
                ("kuroki", 7),
                ("llano", 4),
                ("mantoruso", 5),
                ("ruso", 5),
                ("mantoverde", 1),
                ("mv01", 1),
                ("mv02", 10),
                ("mv07", 2),
            ]

            def map_pit(val):
                if pd.isna(val) or str(val).strip() == "":
                    return 0
                key = re.sub(r"[\s._\-]+", "", str(val).strip().lower())
                for pattern, code in pit_rules:
                    if pattern in key:
                        return code
                return 0

            df["Pit"] = df["Pit"].apply(map_pit)
            steps.append("✅ Mapped Pit names to numeric codes (CELSO→6, FRANKO→3, KUROKI→7, etc.)")
        else:
            steps.append("⚠️ Column 'Pit' not found")

        # ──────────────────────────────────────────────
        # STEP 2 – Clean Density: remove empty, zero, non-numeric
        # ──────────────────────────────────────────────
        if "Density" in df.columns:
            before = len(df)
            df["Density"] = pd.to_numeric(df["Density"], errors="coerce")
            df = df[df["Density"].notna() & (df["Density"] != 0)]
            removed = before - len(df)
            steps.append(f"✅ Cleaned Density — removed {removed} rows (empty / zero / invalid)")
        else:
            steps.append("❌ Column 'Density' not found")

        # ──────────────────────────────────────────────
        # STEP 3 – Remove invalid coordinates
        # ──────────────────────────────────────────────
        col_x = "Local X (Design)"
        col_y = "Local Y (Design)"
        if col_x in df.columns and col_y in df.columns:
            before = len(df)
            df[col_x] = pd.to_numeric(df[col_x], errors="coerce")
            df[col_y] = pd.to_numeric(df[col_y], errors="coerce")
            df = df[df[col_x].notna() & df[col_y].notna()]
            df = df[(df[col_x] >= 0) & (df[col_y] >= 0)]
            removed = before - len(df)
            steps.append(f"✅ Removed {removed} rows with missing or negative coordinates")
        else:
            steps.append("❌ Coordinate columns 'Local X/Y (Design)' not found")

        # ──────────────────────────────────────────────
        # STEP 4 – Cross-fill Hole Length (Design) ↔ (Actual)
        # ──────────────────────────────────────────────
        hl_d = "Hole Length (Design)"
        hl_a = "Hole Length (Actual)"
        if hl_d in df.columns and hl_a in df.columns:
            before = len(df)
            df[hl_d] = pd.to_numeric(df[hl_d], errors="coerce")
            df[hl_a] = pd.to_numeric(df[hl_a], errors="coerce")
            # Replace 0 with NaN for cross-fill purposes
            df[hl_d] = df[hl_d].replace(0, pd.NA)
            df[hl_a] = df[hl_a].replace(0, pd.NA)
            df[hl_d] = df[hl_d].fillna(df[hl_a])
            df[hl_a] = df[hl_a].fillna(df[hl_d])
            df = df.dropna(subset=[hl_d, hl_a], how="all")
            removed = before - len(df)
            steps.append(f"✅ Cross-filled Hole Length (Design ↔ Actual) — removed {removed} fully empty rows")
        else:
            steps.append("⚠️ Hole Length columns not found")

        # ──────────────────────────────────────────────
        # STEP 5 – Cross-fill Explosive (Design) ↔ (Actual)
        # ──────────────────────────────────────────────
        ex_d = "Explosive (kg) (Design)"
        ex_a = "Explosive (kg) (Actual)"
        if ex_d in df.columns and ex_a in df.columns:
            before = len(df)
            df[ex_d] = pd.to_numeric(df[ex_d], errors="coerce")
            df[ex_a] = pd.to_numeric(df[ex_a], errors="coerce")
            df[ex_d] = df[ex_d].replace(0, pd.NA)
            df[ex_a] = df[ex_a].replace(0, pd.NA)
            df[ex_d] = df[ex_d].fillna(df[ex_a])
            df[ex_a] = df[ex_a].fillna(df[ex_d])
            df = df.dropna(subset=[ex_d, ex_a], how="all")
            removed = before - len(df)
            steps.append(f"✅ Cross-filled Explosive (Design ↔ Actual) — removed {removed} fully empty rows")
        else:
            steps.append("⚠️ Explosive columns not found")

        # ──────────────────────────────────────────────
        # STEP 6 – Clean Asset column (keep only numbers)
        # ──────────────────────────────────────────────
        asset_col = None
        for c in df.columns:
            if str(c).strip().lower().startswith("asset"):
                asset_col = c
                break

        if asset_col:
            df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
            df[asset_col] = pd.to_numeric(df[asset_col], errors="coerce")
            df[asset_col] = df[asset_col].fillna(0)
            steps.append(f"✅ Cleaned '{asset_col}' — kept only numeric portion, empty → 0")
        else:
            steps.append("⚠️ Column 'Asset' not found")

        # ──────────────────────────────────────────────
        # STEP 7 – Fill empty Water Presence and Water level with 0
        # ──────────────────────────────────────────────
        for wc in ["Water Presence", "Water level"]:
            if wc in df.columns:
                filled = df[wc].isna().sum() + (df[wc].astype(str).str.strip() == "").sum()
                df[wc] = df[wc].replace("", pd.NA)
                df[wc] = pd.to_numeric(df[wc], errors="coerce").fillna(0)
                steps.append(f"✅ Filled {filled} empty values in '{wc}' with 0")
            else:
                steps.append(f"⚠️ Column '{wc}' not found")

        # ──────────────────────────────────────────────
        # STEP 8 – Drop Blast column and select output columns
        # ──────────────────────────────────────────────
        blast_cols = [c for c in df.columns if "blast" in str(c).strip().lower()]
        if blast_cols:
            df = df.drop(columns=blast_cols)
            steps.append(f"✅ Removed column(s) {blast_cols} from output")

        output_columns = [
            "Pit", "Bench", "Borehole",
            "Local X (Design)", "Local Y (Design)", "Diameter (Design)",
            "Density",
            "Hole Length (Design)", "Hole Length (Actual)",
            "Explosive (kg) (Design)", "Explosive (kg) (Actual)",
            "Stemming (Design)", "Stemming (Actual)",
            "Burden (Design)", "Spacing (Design)", "Subdrill (Design)",
            "Water Presence", "Water level", "Asset",
        ]
        available = [c for c in output_columns if c in df.columns]
        df = df[available]
        steps.append(f"✅ Selected {len(available)} output columns")

        steps.append(f"✅ Final dataset: {len(df)} rows (removed {initial_count - len(df)} total)")

        for s in steps:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{s}</span></div>",
                unsafe_allow_html=True,
            )

    # ==================================================
    # RESULTS
    # ==================================================
    st.markdown("---")
    st.subheader("✅ Data After Cleaning & Transformation")
    st.dataframe(df.head(15), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

    # ==================================================
    # DOWNLOAD
    # ==================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    txt_buffer = io.StringIO()
    df.to_csv(txt_buffer, index=False, header=False, sep="\t")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            excel_buffer,
            file_name="MV_QAQC_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📗 Download TXT File (no headers)",
            txt_buffer.getvalue(),
            file_name="MV_QAQC_Cleaned.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam — Omar El Kendi")

else:
    st.info("📂 Please upload one or more Excel/CSV files to begin.")

