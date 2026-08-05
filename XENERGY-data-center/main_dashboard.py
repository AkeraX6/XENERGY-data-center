import streamlit as st
import importlib.util
import traceback
import gc
from pathlib import Path

# ===============================
# PAGE CONFIGURATION
# ===============================
st.set_page_config(
    page_title="MAXAM Data Process Center",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Hide Streamlit default UI elements
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ===============================
# SESSION STATE INITIALIZATION
# ===============================
if "page" not in st.session_state:
    st.session_state.page = "dashboard"

# ===============================
# HEADER IMAGE
# ===============================
image_path = Path(__file__).parent / "Cover.png"

if image_path.exists():
    st.image(str(image_path), use_container_width=True)
else:
    st.warning("⚠️ Cover image not found: Cover.png")

# ===============================
# PAGE: DASHBOARD
# ===============================
def dashboard_page():
    st.subheader("🧭 Select Processing Module")

    mine = st.selectbox("Select Mine", ["Select...", "Chinalco", "DGM", "Escondida", "Manto Verde", "Mantos Blancos"])
    file_type = st.selectbox(
        "Select File Type",
        ["Select...", "Drilling", "QAQC", "Fragmentation", "Excavation", "Shovel Position", "Block Models", "Drone Fragmentation", "Drill Profile", "Densities", "Ahorros"]
    )

    proceed_button = st.button("🚀 Proceed", use_container_width=True)

    if proceed_button:
        if mine == "Select..." or file_type == "Select...":
            st.warning("⚠️ Please select both Mine and File Type before proceeding.")
        else:
            mine_codes = {"Chinalco": "CHI", "DGM": "DGM", "Escondida": "ES", "Manto Verde": "MV", "Mantos Blancos": "MB"}
            file_codes = {
                "Drilling": "AUTO",
                "QAQC": "QAQC",
                "Fragmentation": "FRAG",
                "Excavation": "EXCA",
                "Shovel Position": "POSP",
                "Block Models": "MOB",
                "Drone Fragmentation": "DRONE",
                "Drill Profile": "PROF",
                "Densities": "Densities",
                "Ahorros": "AHORROS",
            }

            mine_code = mine_codes[mine]
            file_code = file_codes[file_type]

            # Save selected module name in session
            st.session_state.selected_module = f"{mine_code}_{file_code}.py"
            st.session_state.page = "module"
            st.rerun()

# ===============================
# PAGE: MODULE
# ===============================
def module_page():
    pages_dir = Path(__file__).parent / "pages"
    module_name = st.session_state.selected_module
    module_path = pages_dir / module_name

    # Header with Back button
    col1, col2 = st.columns([0.15, 0.85])
    with col1:
        if st.button("⬅️ Back to Menu"):
            st.session_state.page = "dashboard"
            st.rerun()
    with col2:
        st.markdown(f"### ⚙️ Loaded Module: `{module_name}`")

    # Check file existence
    if not module_path.exists():
        st.error(f"❌ The file `{module_name}` was not found in `/pages` folder.")
        return

    # Load and execute selected module inline with error containment so a
    # single-page crash does not take down the whole Streamlit Cloud app.
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except MemoryError:
        st.error(
            "🧠 The app ran out of memory while processing this module.\n\n"
            "Try uploading a smaller file, or split your dataset into batches."
        )
        gc.collect()
    except Exception as e:
        st.error(f"❌ Error while running `{module_name}`: {e}")
        with st.expander("🔍 Show technical details"):
            st.code(traceback.format_exc())
        if st.button("↩️ Return to Menu", key="err_back"):
            st.session_state.page = "dashboard"
            st.rerun()
    finally:
        # Release large objects between page switches to keep memory low on
        # Streamlit Community Cloud (1 GB RAM limit).
        gc.collect()

# ===============================
# NAVIGATION LOGIC
# ===============================
if st.session_state.page == "dashboard":
    dashboard_page()
else:
    module_page()
