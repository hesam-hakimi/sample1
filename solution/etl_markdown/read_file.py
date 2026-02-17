import os

from db_utils import setup_database
from ai_utils import get_search_client
from ui import launch_ui

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def main():
    if DEBUG_MODE:
        print("DEBUG: starting main()")

    engine = setup_database()
    search_client = get_search_client()

    launch_ui(engine, search_client)


if __name__ == "__main__":
    main()
