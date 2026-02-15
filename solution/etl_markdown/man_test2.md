In app/ui/streamlit_app.py, the TD logo is displaying huge (it fills the page). Fix the header UI so the logo is small and the page looks like a bank header bar.

Requirements:

Build a header bar at the top (white background, subtle bottom border, padding).

Put logo on the left, title/subtitle next to it, and keep the rest of the page content below.

The logo MUST NOT use width="stretch" or use_container_width=True. Render it as a fixed size like st.image(logo, width=110) and preserve aspect ratio.

If the logo is large, also resize in PIL before showing: logo.thumbnail((140, 140)).

Keep the previous “safe logo load” behavior: if invalid/missing, show a small fallback “TD” badge (not huge).

Ensure the header remains compact on wide layout (st.set_page_config(layout="wide") is OK).

Implement the code changes directly and keep the rest of the app behavior the same.
