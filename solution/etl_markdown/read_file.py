import os
from dotenv import load_dotenv

from db_utils import setup_database
from ui import launch_ui

load_dotenv(override=True)

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

def main():
    if DEBUG_MODE:
        print("DEBUG: Starting main()")

    engine = setup_database()

    if DEBUG_MODE:
        print("DEBUG: Launching UI")

    launch_ui(engine)

if __name__ == "__main__":
    main()
