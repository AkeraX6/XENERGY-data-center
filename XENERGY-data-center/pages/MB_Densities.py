import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
import csv
from datetime import datetime

# ==========================================================
# COLUMN DEFINITIONS (Mantos Blancos input format)
# ==========================================================
# Expected headers in input file:
# HOLE ID | COORDENADA ESTE | COORDENADA NORTE | Collar Z | Length |
# Stemming | Burden | Spacing | Subdrill Length | Drill Rig
COLUMN_NAMES = [
    "Hole_ID", "Coord_Este", "Coord_Norte", "Collar_Z", "Length",
    "Stemming", "Burden", "Spacing", "Subdrill_Length", "Drill_Rig",
]

# Map possible source headers (case/space/accents tolerant) -> internal names
HEADER_ALIASES = {
    "hole id": "Hole_ID",
    "holeid": "Hole_ID",
    "hole_id": "Hole_ID",
    "coordenada este": "Coord_Este",
    "coord este": "Coord_Este",
    "este": "Coord_Este",
    "coord_este": "Coord_Este",
    "coordenada norte": "Coord_Norte",
    "coord norte": "Coord_Norte",
    "norte": "Coord_Norte",
    "coord_norte": "Coord_Norte",
    "collar z": "Collar_Z",
    "collarz": "Collar_Z",
    "collar_z": "Collar_Z",
    "length": "Length",
    "stemming": "Stemming",
    "burden": "Burden",
    "spacing": "Spacing",
    "subdrill length": "Subdrill_Length",
    "subdrill_length": "Subdrill_Length",
    "subdrill": "Subdrill_Length",
    "drill rig": "Drill_Rig",
    "drill_rig": "Drill_Rig",
    "rig": "Drill_Rig",
}

# Density palette (same as Escondida)
DENSITY_OPTIONS = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.33, 1.35, 1.40]

DENSITY_COLORS = {
    0.80: "#00C853",
    0.85: "#76FF03",
    0.90: "#C6FF00",
    0.95: "#FFD600",
    1.00: "#FF9100",
    1.05: "#FF3D00",
    1.10: "#D50000",
    1.15: "#AA00FF",
    1.20: "#2962FF",
    1.25: "#00B0FF",
    1.30: "#795548",
    1.33: "#00695C",
    1.35: "#78909C",
    1.40: "#37474F",
}

# Color for holes without a density assigned yet
UNASSIGNED_COLOR = "#BDBDBD"

# ==========================================================
# HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Mantos Blancos — Density Editor</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;color:gray;'>Upload a drilling plan, assign densities per hole, and export the result.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_mb_densities"):
    st.session_state.page = "dashboard"
    st.rerun()


# ==========================================================
# HELPERS
# ==========================================================
def detect_delimiter(text: str) -> str:
    for delim in ["\t", ";", ","]:
        if delim in text:
            try:
                dialect = csv.Sniffer().sniff(text, delimiters=delim)
                return dialect.delimiter
            except csv.Error:
                pass
            return delim
    return r"\s+"


def _normalize_header(h: str) -> str:
    return str(h).strip().lower().replace("\u00a0", " ")


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns from input file to internal names using HEADER_ALIASES."""
    new_cols = {}
    for c in df.columns:
        key = _normalize_header(c)
        if key in HEADER_ALIASES:
            new_cols[c] = HEADER_ALIASES[key]
    df = df.rename(columns=new_cols)

    # Add missing columns as NaN
    for col in COLUMN_NAMES:
        if col not in df.columns:
            df[col] = pd.NA

    # Keep only the expected columns, in order
    df = df[COLUMN_NAMES].copy()
    return df


def load_file(uploaded_file) -> tuple[pd.DataFrame, str]:
    """Read uploaded file (xlsx/csv/txt/tsv) with header row, map columns."""
    name = uploaded_file.name.lower()
    delim = "\t"

    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file, header=0)
    else:
        raw = uploaded_file.read().decode("utf-8", errors="replace")
        uploaded_file.seek(0)
        delim = detect_delimiter(raw[:4096])
        if delim == r"\s+":
            df = pd.read_csv(io.StringIO(raw), sep=r"\s+", header=0, engine="python")
        else:
            df = pd.read_csv(io.StringIO(raw), sep=delim, header=0, engine="python")

    df = _map_columns(df)

    # Type conversions
    df["Hole_ID"] = df["Hole_ID"].astype(str).str.strip()
    numeric_cols = ["Coord_Este", "Coord_Norte", "Collar_Z", "Length",
                    "Stemming", "Burden", "Spacing", "Subdrill_Length"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows without coordinates
    df = df.dropna(subset=["Coord_Este", "Coord_Norte"]).reset_index(drop=True)

    # Initialize empty DENSITY column (to be filled by user)
    df["DENSITY"] = pd.NA

    return df, delim


def build_figure(df: pd.DataFrame, color_map: dict, show_labels: bool, marker_size: int, label_size: int) -> go.Figure:
    """Scatter of all holes colored by DENSITY, optional HOLE_ID labels."""
    fig = go.Figure()

    # Unassigned holes
    unassigned = df[df["DENSITY"].isna()]
    if len(unassigned) > 0:
        fig.add_trace(go.Scatter(
            x=unassigned["Coord_Este"],
            y=unassigned["Coord_Norte"],
            mode="markers+text" if show_labels else "markers",
            text=unassigned["Hole_ID"] if show_labels else None,
            textposition="top center",
            textfont=dict(size=label_size, color="#333"),
            name="Unassigned",
            marker=dict(
                size=marker_size,
                symbol="circle",
                color=UNASSIGNED_COLOR,
                line=dict(width=1, color="#333"),
            ),
            customdata=unassigned[["Hole_ID"]].values,
            hovertemplate=(
                "<b>Hole:</b> %{customdata[0]}<br>"
                "<b>Este:</b> %{x:.1f}<br>"
                "<b>Norte:</b> %{y:.1f}<br>"
                "<b>Density:</b> —<extra></extra>"
            ),
        ))

    # Assigned holes, grouped by density value
    for density_val in sorted(df["DENSITY"].dropna().unique()):
        sub = df[df["DENSITY"] == density_val]
        color = color_map.get(density_val, "#888888")
        fig.add_trace(go.Scatter(
            x=sub["Coord_Este"],
            y=sub["Coord_Norte"],
            mode="markers+text" if show_labels else "markers",
            text=sub["Hole_ID"] if show_labels else None,
            textposition="top center",
            textfont=dict(size=label_size, color="#222"),
            name=f"Density {density_val}",
            marker=dict(
                size=marker_size,
                symbol="circle",
                color=color,
                line=dict(width=1, color="#333"),
            ),
            customdata=sub[["Hole_ID", "DENSITY"]].values,
            hovertemplate=(
                "<b>Hole:</b> %{customdata[0]}<br>"
                "<b>Este:</b> %{x:.1f}<br>"
                "<b>Norte:</b> %{y:.1f}<br>"
                "<b>Density:</b> %{customdata[1]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        xaxis_title="Coordenada Este",
        yaxis_title="Coordenada Norte",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        legend_title="Density",
        margin=dict(l=40, r=20, t=30, b=40),
        height=750,
        dragmode="lasso",
        plot_bgcolor="#FAFAFA",
    )
    return fig


# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader(
    "📤 Upload drilling plan file (xlsx, csv, txt, tsv)",
    type=["xlsx", "xls", "csv", "txt", "tsv"],
)

if uploaded_file is not None:
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("_mb_density_file_key") != file_key:
        try:
            df_loaded, delim = load_file(uploaded_file)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            st.stop()
        st.session_state["_mb_density_file_key"] = file_key
        st.session_state["mb_density_df"] = df_loaded.copy()
        st.session_state["mb_density_df_original"] = df_loaded.copy()
        st.session_state["mb_density_delim"] = delim
        st.session_state["mb_density_changes"] = []
        st.session_state["mb_density_custom_colors"] = {}

if "mb_density_df" not in st.session_state:
    st.info("📂 Please upload a file to begin.")
    st.stop()

df = st.session_state["mb_density_df"]
original_df = st.session_state["mb_density_df_original"]
changes_log = st.session_state["mb_density_changes"]
custom_colors = st.session_state["mb_density_custom_colors"]

assigned_count = int(df["DENSITY"].notna().sum())
st.success(
    f"✅ Loaded {len(df)} holes  |  "
    f"{assigned_count} assigned  |  {len(df) - assigned_count} unassigned"
)

# ==========================================================
# CONTROLS
# ==========================================================
if "mb_target_density" not in st.session_state:
    st.session_state["mb_target_density"] = 1.00

st.subheader("🎨 Select Target Density")

btn_cols = st.columns(7)
for idx, d in enumerate(DENSITY_OPTIONS):
    color = DENSITY_COLORS.get(d, "#888888")
    is_selected = (st.session_state["mb_target_density"] == d)
    border = "3px solid #fff" if is_selected else "1px solid #555"
    with btn_cols[idx % 7]:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:2px;'>"
            f"<div style='width:18px;height:18px;border-radius:50%;background:{color};border:{border};"
            f"margin:0 auto;'></div></div>",
            unsafe_allow_html=True,
        )
        if st.button(
            f"{'✔ ' if is_selected else ''}{d}",
            key=f"mb_density_btn_{d}",
            use_container_width=True,
        ):
            st.session_state["mb_target_density"] = d
            st.rerun()

target_density = st.session_state["mb_target_density"]
active_color = DENSITY_COLORS.get(target_density, "#888888")
st.markdown(
    f"**Active density:** <span style='color:{active_color};font-size:18px;font-weight:700;'>"
    f"● {target_density}</span>",
    unsafe_allow_html=True,
)

# --- Display + edit controls ---
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1.6, 1.6, 1, 1])
with ctrl1:
    edit_mode = st.radio(
        "Edit Mode",
        ["Lasso / Box Select", "Range (X/Y bounds)", "Single Hole (dropdown)"],
        index=0,
        horizontal=False,
    )
with ctrl2:
    show_labels = st.checkbox("Show HOLE ID labels", value=True)
    marker_size = st.slider("Marker size", 6, 24, 12)
    label_size = st.slider("Label size", 7, 18, 10)
with ctrl3:
    if st.button("↩ Undo Last", use_container_width=True, disabled=len(changes_log) == 0):
        last = changes_log.pop()
        match_mask = df["Hole_ID"].astype(str) == str(last["Hole_ID"])
        df.loc[match_mask, "DENSITY"] = last["Old_Density"]
        st.session_state["mb_density_df"] = df
        st.rerun()
with ctrl4:
    if st.button("🔄 Reset All", use_container_width=True):
        st.session_state["mb_density_df"] = original_df.copy()
        st.session_state["mb_density_changes"] = []
        st.rerun()

# --- Range mode inputs ---
if edit_mode == "Range (X/Y bounds)":
    r1, r2, r3, r4, r5 = st.columns([1, 1, 1, 1, 1])
    with r1:
        x_min = st.number_input("X min", value=float(df["Coord_Este"].min()), format="%.1f")
    with r2:
        x_max = st.number_input("X max", value=float(df["Coord_Este"].max()), format="%.1f")
    with r3:
        y_min = st.number_input("Y min", value=float(df["Coord_Norte"].min()), format="%.1f")
    with r4:
        y_max = st.number_input("Y max", value=float(df["Coord_Norte"].max()), format="%.1f")
    with r5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Apply Range Edit", use_container_width=True):
            mask = (
                (df["Coord_Este"] >= x_min) & (df["Coord_Este"] <= x_max) &
                (df["Coord_Norte"] >= y_min) & (df["Coord_Norte"] <= y_max) &
                (df["DENSITY"] != target_density)
            )
            affected = df.loc[mask]
            if len(affected) > 0:
                for idx_row in affected.index:
                    changes_log.append({
                        "Hole_ID": df.at[idx_row, "Hole_ID"],
                        "Old_Density": df.at[idx_row, "DENSITY"],
                        "New_Density": target_density,
                        "Timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                df.loc[mask, "DENSITY"] = target_density
                st.session_state["mb_density_df"] = df
                st.success(f"✅ Updated {len(affected)} holes.")
                st.rerun()
            else:
                st.warning("No holes in that range need updating.")

# --- Single hole mode ---
if edit_mode == "Single Hole (dropdown)":
    s1, s2 = st.columns([3, 1])
    with s1:
        hole_choice = st.selectbox(
            "Select hole ID",
            options=df["Hole_ID"].astype(str).tolist(),
            key="mb_single_hole",
        )
    with s2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Assign density", use_container_width=True):
            mask = df["Hole_ID"].astype(str) == str(hole_choice)
            for idx_row in df.loc[mask].index:
                changes_log.append({
                    "Hole_ID": df.at[idx_row, "Hole_ID"],
                    "Old_Density": df.at[idx_row, "DENSITY"],
                    "New_Density": target_density,
                    "Timestamp": datetime.now().strftime("%H:%M:%S"),
                })
            df.loc[mask, "DENSITY"] = target_density
            st.session_state["mb_density_df"] = df
            st.toast(f"Hole {hole_choice} → {target_density}")
            st.rerun()

# --- Color customization ---
unique_densities = sorted(df["DENSITY"].dropna().unique().tolist())
color_map = {}
for d in unique_densities:
    key = str(d)
    if key in custom_colors:
        color_map[d] = custom_colors[key]
    elif d in DENSITY_COLORS:
        color_map[d] = DENSITY_COLORS[d]
    else:
        color_map[d] = "#888888"

if unique_densities:
    with st.expander("🎨 Customize Colors", expanded=False):
        cc_cols = st.columns(min(len(unique_densities), 7) or 1)
        for i, d in enumerate(unique_densities):
            key = str(d)
            current_color = color_map.get(d, "#888888")
            with cc_cols[i % len(cc_cols)]:
                new_color = st.color_picker(f"{d}", value=current_color, key=f"mb_cp_{d}")
                if new_color != current_color:
                    custom_colors[key] = new_color
                    color_map[d] = new_color

st.markdown("---")

# ==========================================================
# SCATTER PLOT
# ==========================================================
st.subheader("📊 Drill Plan — Click / Lasso to assign density")

fig = build_figure(df, color_map, show_labels, marker_size, label_size)

if edit_mode == "Lasso / Box Select":
    event = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode=["points", "box", "lasso"],
        key="mb_density_plot",
    )

    if event and event.selection and event.selection.points:
        selected_points = event.selection.points
        updated_count = 0

        for pt in selected_points:
            pt_x = pt.get("x")
            pt_y = pt.get("y")
            if pt_x is None or pt_y is None:
                continue

            mask = (
                (df["Coord_Este"] == pt_x) &
                (df["Coord_Norte"] == pt_y) &
                (df["DENSITY"] != target_density)
            )
            affected = df.loc[mask]
            for idx_row in affected.index:
                changes_log.append({
                    "Hole_ID": df.at[idx_row, "Hole_ID"],
                    "Old_Density": df.at[idx_row, "DENSITY"],
                    "New_Density": target_density,
                    "Timestamp": datetime.now().strftime("%H:%M:%S"),
                })
                df.at[idx_row, "DENSITY"] = target_density
                updated_count += 1

        if updated_count > 0:
            st.session_state["mb_density_df"] = df
            st.toast(f"Updated {updated_count} hole(s) → density {target_density}")
            st.rerun()
else:
    st.plotly_chart(fig, use_container_width=True, key="mb_density_plot_static")

# ==========================================================
# DATA PREVIEW
# ==========================================================
st.subheader("📋 Data Preview")
st.dataframe(df.head(30), use_container_width=True, hide_index=True)

# ==========================================================
# CHANGE HISTORY
# ==========================================================
with st.expander("📜 Change History", expanded=False):
    if changes_log:
        log_df = pd.DataFrame(changes_log)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
        st.info(f"Total edits: {len(changes_log)}")
    else:
        st.write("No changes yet.")

# ==========================================================
# EXPORT
# ==========================================================
st.markdown("---")
st.subheader("💾 Export")

# Build export dataframe with original-style headers
export_df = pd.DataFrame({
    "HOLE ID": df["Hole_ID"],
    "COORDENADA ESTE": df["Coord_Este"],
    "COORDENADA NORTE": df["Coord_Norte"],
    "Collar Z": df["Collar_Z"],
    "Length": df["Length"],
    "Stemming": df["Stemming"],
    "Burden": df["Burden"],
    "Spacing": df["Spacing"],
    "Subdrill Length": df["Subdrill_Length"],
    "Drill Rig": df["Drill_Rig"],
    "DENSITY": df["DENSITY"],
})

excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

delim_char = st.session_state.get("mb_density_delim", "\t")
if delim_char == r"\s+":
    delim_char = "\t"
txt_buffer = io.StringIO()
export_df.to_csv(txt_buffer, sep=delim_char, index=False)

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel",
        excel_buffer,
        file_name="MB_Densities.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col2:
    st.download_button(
        "📄 Download TXT (with header)",
        txt_buffer.getvalue(),
        file_name="MB_Densities.txt",
        mime="text/plain",
        use_container_width=True,
    )

# ==========================================================
# STATISTICS
# ==========================================================
with st.expander("📈 Density Statistics", expanded=False):
    if df["DENSITY"].notna().any():
        stats = df.dropna(subset=["DENSITY"]).groupby("DENSITY").agg(
            Count=("Hole_ID", "count"),
            Avg_Este=("Coord_Este", "mean"),
            Avg_Norte=("Coord_Norte", "mean"),
        ).reset_index()
        stats["Avg_Este"] = stats["Avg_Este"].round(1)
        stats["Avg_Norte"] = stats["Avg_Norte"].round(1)
        st.dataframe(stats, use_container_width=True, hide_index=True)
    else:
        st.write("No densities assigned yet.")

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam — Omar El Kendi")
