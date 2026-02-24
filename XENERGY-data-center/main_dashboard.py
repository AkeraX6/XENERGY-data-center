import streamlit as st
import importlib.util
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

    mine = st.selectbox("Select Mine", ["Select...", "DGM", "Escondida", "Mantos Blancos"])
    file_type = st.selectbox(
        "Select File Type",
        ["Select...", "Drilling", "QAQC", "Fragmentation", "Excavation", "Shovel Position", "Shovel Position New", "Block Models"]
    )

    proceed_button = st.button("🚀 Proceed", use_container_width=True)

    if proceed_button:
        if mine == "Select..." or file_type == "Select...":
            st.warning("⚠️ Please select both Mine and File Type before proceeding.")
        else:
            mine_codes = {"DGM": "DGM", "Escondida": "ES", "Mantos Blancos": "MB"}
            file_codes = {
                "Drilling": "AUTO",
                "QAQC": "QAQC",
                "Fragmentation": "FRAG",
                "Excavation": "EXCA",
                "Shovel Position": "POSP",
                "Block Models": "MOB",
                "Shovel Position New": "POSP2"
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
    
    # Load and execute selected module inline
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

# ===============================
# NAVIGATION LOGIC
# ===============================
if st.session_state.page == "dashboard":
    dashboard_page()
else:
    module_page()

