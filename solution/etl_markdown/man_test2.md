Fix Streamlit crash: NameError: name 'display' is not defined in app/ui/streamlit_app.py line ~90.
There is a CSS line `display: inline-block;` accidentally placed in Python code (not inside a string).
Move ALL CSS rules into a single st.markdown("""<style>...</style>""", unsafe_allow_html=True) block.
Ensure no raw CSS properties remain as Python statements.
Then run:
- python -m compileall app/ui/streamlit_app.py
- streamlit run app/ui/streamlit_app.py
and confirm the app loads.
