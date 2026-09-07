"""Publish the certificate authority a bundled database signs its certificate with.

The authority comes into being when MySQL starts for the first time, and that start
happens after the deploy which wrote the study. The stack is up by the time this
script runs, so the authority is read out of the running container here and the
study republished carrying it. A phone is then served a config that lets it verify
the database it connects to.

The condition is asked once here and answered the same way for either platform,
because both entry scripts call this rather than carrying the question themselves.
"""

import argparse
import json
import pathlib
import subprocess
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT = pathlib.Path("/project")
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

SERVED_CONFIG = PROJECT / "studies" / "studyConfig.json"


def study_awaits_authority() -> bool:
    """Whether this deployment holds an authority the served config still wants.

    Two things make it true together: the study runs the bundled database, and the
    config the phones are served carries no authority yet. The placement settles the
    first half of the question on its own --- a bundled connection is encrypted, and
    the certificate it is checked against is one this deployment generated. A study
    whose source this machine reads as something else is left to the deploy that
    owns it.

    The served file answers the second question rather than the study model. The
    deploy reads the authority out of the running container and writes it into what
    the phones fetch, so that file is where a published authority is visible. A
    served config this machine reads as absent belongs to a study whose publication
    is still ahead of it, which is the run this script exists for.
    """
    try:
        from shared_config import placement
        from shared_config.source_store import read_source

        source = read_source()
    except Exception:
        return False

    if placement.declared(source) != placement.BUNDLED:
        return False

    try:
        served = json.loads(SERVED_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return True

    published = (served.get("database") or {}).get("database_certificate_authority") or ""
    return not published.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--docker-prefix",
        action="append",
        default=[],
        help="Optional command prefix before docker, for example: --docker-prefix sudo",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not study_awaits_authority():
        return 0

    print("  Publishing the certificate authority the database generated...")
    command = [sys.executable, str(SCRIPT_DIR / "deploy_config.py")]
    for prefix in args.docker_prefix:
        command += ["--docker-prefix", prefix]
    return subprocess.run(command, cwd=str(PROJECT)).returncode


if __name__ == "__main__":
    sys.exit(main())
