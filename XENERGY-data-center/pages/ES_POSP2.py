import streamlit as st
import pandas as pd
import re
import io

# ==========================================================
# SMALL HELPERS
# ==========================================================
def normalize_name(name: str) -> str:
    """Uppercase, remove spaces and underscores to compare column names."""
    return re.sub(r"[\s_]+", "", str(name)).upper()

def find_column(df, candidates):
    """Find a column in df whose normalized name matches any of candidates."""
    norm_candidates = {normalize_name(c) for c in candidates}
    for col in df.columns:
        if normalize_name(col) in norm_candidates:
            return col
    return None

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Shovel Position New (ES_POSP2)</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Processing of Shovel Position New data.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# 🔙 Back to Menu
if st.button("⬅️ Back to Menu", key="back_esposp2"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel/CSV file (Shovel Position New)", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:

    # ---------- Read file (Excel or CSV) ----------
    file_name = uploaded_file.name.lower()

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

    if file_name.endswith(".csv"):
        df = read_csv_smart(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("📄 Original Data (Before Processing)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows: {len(df)}")

    original_rows = len(df)
    steps = []

    # ==========================================================
    # PROCESSING STEPS
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # ---------- Detect columns (case/space-insensitive) ----------
        col_fecha = find_column(df, ["FECHA"])
        col_turno = find_column(df, ["TURNO"])
        col_pala = find_column(df, ["PALA"])
        col_x = find_column(df, ["X"])
        col_y = find_column(df, ["Y"])
        col_z = find_column(df, ["Z"])
        col_pases = find_column(df, ["PASES"])

        missing_cols = []
        for name, col in [
            ("FECHA", col_fecha),
            ("TURNO", col_turno),
            ("PALA", col_pala),
            ("X", col_x),
            ("Y", col_y),
            ("Z", col_z),
        ]:
            if col is None:
                missing_cols.append(name)

        if missing_cols:
            st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
        else:
            # ---------- 1) Split FECHA into Day / Month / Year ----------
            df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
            before = len(df)
            df = df[df[col_fecha].notna()]
            deleted = before - len(df)
            if deleted > 0:
                steps.append(f"🗑️ FECHA invalid/empty rows removed: {deleted}")

            df["Day"] = df[col_fecha].dt.day.astype(int)
            df["Month"] = df[col_fecha].dt.month.astype(int)
            df["Year"] = df[col_fecha].dt.year.astype(int)
            steps.append("✔️ FECHA split into Day / Month / Year.")

            # ---------- 2) Turno: Keep as-is and duplicate ----------
            df["Turno1"] = df[col_turno]
            df["Turno2"] = df[col_turno]
            steps.append("✔️ Turno duplicated into two columns.")

            # ---------- 3) Pala: Keep as-is ----------
            df["Pala"] = df[col_pala]
            steps.append("✔️ Pala column kept.")

            # ---------- 4) Add Hour and Minute columns filled with 1000 ----------
            df["Hour"] = 1000
            df["Minute"] = 1000
            steps.append("✔️ Hour and Minute columns added (filled with 1000).")

            # ---------- 5) X, Y, Z: Keep as-is ----------
            df["X"] = df[col_x]
            df["Y"] = df[col_y]
            df["Z"] = df[col_z]
            steps.append("✔️ X, Y, Z columns kept.")

            # ---------- Summary ----------
            total_deleted = original_rows - len(df)
            if total_deleted > 0:
                steps.append(f"📉 Total rows removed: {total_deleted}")
            else:
                steps.append("📊 No rows removed during processing.")

        # Show steps in green cards
        for step in steps:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:8px;border-radius:6px;margin-bottom:6px;'>"
                f"<span style='color:#137333;font-weight:500;font-size:13px;'>{step}</span></div>",
                unsafe_allow_html=True,
            )

    # ==========================================================
    # AFTER PROCESSING — RESULTS
    # ==========================================================
    st.markdown("---")
    st.subheader("✅ Processed Data Preview")

    # Final output in required order: Day, Month, Year, Turno, Turno, Pala, Hour, Minute, X, Y, Z
    output_cols = ["Day", "Month", "Year", "Turno1", "Turno2", "Pala", "Hour", "Minute", "X", "Y", "Z"]
    existing_output_cols = [c for c in output_cols if c in df.columns]
    export_df = df[existing_output_cols].copy()

    st.dataframe(export_df.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(export_df)} rows × {len(export_df.columns)} columns.")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Files")

    option = st.radio("Choose download option:", ["⬇️ Download All Output Columns", "🧩 Download Custom Columns"])

    if option == "⬇️ Download All Output Columns":
        final_df = export_df
    else:
        selected_columns = st.multiselect(
            "Select columns (drag to reorder):",
            options=list(export_df.columns),
            default=list(export_df.columns),
        )
        final_df = export_df[selected_columns] if selected_columns else export_df

    # For Excel export, rename Turno1/Turno2 to just Turno for display
    excel_df = final_df.copy()
    excel_df.columns = [c.replace("Turno1", "Turno").replace("Turno2", "Turno") for c in excel_df.columns]

    # Excel (with headers)
    excel_buffer = io.BytesIO()
    excel_df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    # TXT (tab-separated, no headers)
    txt_buffer = io.StringIO()
    final_df.to_csv(txt_buffer, index=False, header=False, sep="\t")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel (with headers)",
            excel_buffer,
            file_name="Escondida_POSP2_Shovel_Position_New.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📄 Download TXT (no headers)",
            txt_buffer.getvalue(),
            file_name="Escondida_POSP2_Shovel_Position_New.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload an Excel or CSV file with columns: Fecha, Turno, Pala, X, Y, Z, Pases")
