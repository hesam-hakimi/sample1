from __future__ import annotations

import os
from dotenv import load_dotenv

from db_utils import setup_database
from ai_utils import get_msi_credential, get_search_clients
from ui import launch_ui

load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def main() -> None:
    if DEBUG_MODE:
        print("DEBUG: Starting main()")

    engine = setup_database()

    cred = get_msi_credential()
    _, search_client = get_search_clients(cred)

    if DEBUG_MODE:
        print("DEBUG: Launching UI")

    launch_ui(engine, search_client)


if __name__ == "__main__":
    main()
