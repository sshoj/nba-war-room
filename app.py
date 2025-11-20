import streamlit as st
import subprocess
import sys
import os

st.set_page_config(page_title="Debug Mode")
st.title("🛠️ Debugging Your Environment")

# 1. Check Python Version
st.write(f"**Python Version:** `{sys.version}`")

# 2. Check Current Directory (To verify file location)
st.write(f"**Current Directory:** `{os.getcwd()}`")
st.write("**Files in this folder:**")
try:
    files = os.listdir(".")
    st.code("\n".join(files))
except Exception as e:
    st.error(f"Cannot read directory: {e}")

# 3. Check Installed Packages
st.write("**Installed Packages:**")
try:
    # Run 'pip freeze' to see what is actually installed
    result = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
    st.text(result.decode("utf-8"))
except Exception as e:
    st.error(f"Failed to check packages: {e}")

# 4. Try Importing nba_api safely
st.write("---")
st.write("**Attempting to import nba_api...**")
try:
    import nba_api
    st.success("✅ nba_api is installed and working!")
except ImportError:
    st.error("❌ nba_api is NOT installed.")
    st.info("This means requirements.txt was ignored or failed silently.")
