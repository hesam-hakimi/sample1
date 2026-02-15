We have a Streamlit app in app/ui/streamlit_app.py. It currently crashes because assets/td_logo.png is invalid (it’s ASCII text, not a PNG), causing PIL.UnidentifiedImageError when calling st.image.

Please implement a robust logo loader:

Add a helper load_logo_safe(path: str) -> PIL.Image.Image | None that:

checks file exists

tries Image.open(path) and img.verify() safely

returns None if invalid (catch UnidentifiedImageError, OSError, etc.)

If logo is invalid/missing, do NOT crash. Show a fallback “TD” badge (simple st.markdown with CSS or st.caption), and continue.

Replace deprecated st.image(..., use_container_width=...) with the new API:

prefer st.image(img, width="stretch")

but keep backward compatibility: if TypeError occurs (older Streamlit), fall back to use_container_width=True

Add a quick validation log message to the debug panel showing whether the logo loaded or fallback was used.

Add/ensure .gitignore contains .env and add .env.example if missing (names only).

After patching, provide the exact command to run the app and verify it no longer crashes even if the logo file is invalid.
