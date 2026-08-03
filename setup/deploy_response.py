import json
import os
from pathlib import Path


def main() -> None:
    payload = {
        "success": True,
        "researcher_username": os.environ.get("RESEARCHER_USERNAME", ""),
        "researcher_password": os.environ.get("RESEARCHER_PASSWORD", ""),
        "participant_db_password": os.environ.get("PARTICIPANT_DB_PASSWORD", ""),
    }

    urls_path = Path("/project/deployment-urls.json")
    if urls_path.exists():
        try:
            payload["urls"] = json.loads(urls_path.read_text(encoding="utf-8"))
        except Exception:
            payload["urls"] = {}

    print(json.dumps(payload), end="")


if __name__ == "__main__":
    main()
