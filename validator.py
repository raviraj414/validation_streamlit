
# validator.py
import streamlit as st
from db import signup_user, login_user, get_last_processed_cmd_id

st.set_page_config(page_title="Command Classifier", layout="wide")

# -------------------- Session State --------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None

# -------------------- Auth UI --------------------
def signup():
    st.subheader("Sign Up")
    name = st.text_input("Name")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign Up"):
        if signup_user(name, email, password):
            st.success("Signup successful! Please login.")
        else:
            st.error("Signup failed. Email may already exist.")

def login():
    st.subheader("Login")
    login_type = st.selectbox("Login as", ["Validator", "Viewer", "Admin"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(email, password)
        if user:
            if user["role"].lower() != login_type.lower():
                st.error("Incorrect role selected.")
                return

            # Persist session
            st.session_state.logged_in = True
            st.session_state.user = user

            # Initialize validator-specific state at login
            if login_type == "Validator":
                st.session_state.current_index = get_last_processed_cmd_id(user["id"]) or 0
                # reset dashboard caches to force fresh load
                st.session_state.pop("cmds_data", None)
                st.session_state.pop("sub_idx", None)

            st.rerun()
        else:
            st.error("Invalid credentials.")

# -------------------- App Entry --------------------
if not st.session_state.logged_in:
    menu = ["Login", "Sign Up"]
    choice = st.sidebar.selectbox("Menu", menu)
    if choice == "Login":
        login()
    else:
        signup()
else:
    role = st.session_state.user["role"].lower()

    if role == "admin":
        import admin_dashboard
        admin_dashboard.admin_dashboard()

    elif role == "validator":
        import validator_dashboard
        validator_dashboard.validator_dashboard()

    else:
        # Placeholder for viewer; you can create viewer_dashboard similarly
        st.title("👀 Viewer")
        st.info("Viewer dashboard coming soon.")
        if st.sidebar.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()

