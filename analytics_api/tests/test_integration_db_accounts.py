"""What each MySQL account may do, answered by a real server.

`db/init_all.sql` is the file MySQL runs on every start, and the privileges in it are
the only thing standing between a credential and the data. Reading them back from a
server that has actually applied them is what turns a grant list into a guarantee: a
GRANT naming a table that does not exist yet, or an account nothing created, fails
here rather than on a deployment.

Two accounts write the Android schema, one per dataflow. A participant's phone opens
the database itself on the direct path, and its credential is published in the study
config every phone downloads, so that account inserts and reads nothing back. The
micro-server performs every write on the webservice path, so its own account also
reads the enrolment registry it checks, keeps the refusal counters and fills in the
device-metadata row.

Slow enough to be opt-in: `pytest -m integration`.
"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.integration

PARTICIPANT = "aware_android_participant"
SERVER = "aware_android_server"
SCHEMA = "aware_android"


def grants(server, account: str) -> str:
    """Every privilege the server reports for an account, as one blob to search."""
    return server.run(f"SHOW GRANTS FOR '{account}'@'%'")


def can(server, account: str, statement: str, database: str = SCHEMA) -> bool:
    """Whether the account is allowed to run this statement, as the server decides.

    Run inside a transaction that is rolled back, so a permitted statement is
    answered without leaving the row behind.
    """
    done = subprocess.run(
        [
            "mysql",
            f"--socket={server.socket_path}",
            f"-u{account}",
            "-N",
            "-B",
            database,
        ],
        input=f"START TRANSACTION;\n{statement};\nROLLBACK;",
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "MYSQL_PWD": ACCOUNT_PASSWORDS[account]},
    )
    return done.returncode == 0


#: The seed passwords init_all.sql creates the accounts with. A deployment replaces
#: them; here they are what lets a test connect as the account under test.
ACCOUNT_PASSWORDS = {PARTICIPANT: "participantpass", SERVER: "serverpass"}


def columns_seen_by(server, account: str, table: str) -> set[str]:
    """The columns of a table as that account can see them listed."""
    done = subprocess.run(
        ["mysql", f"--socket={server.socket_path}", f"-u{account}", "-N", "-B", SCHEMA],
        input=(
            "SELECT `COLUMN_NAME` FROM `information_schema`.`COLUMNS` "
            f"WHERE `TABLE_SCHEMA` = DATABASE() AND `TABLE_NAME` = '{table}'"
        ),
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "MYSQL_PWD": ACCOUNT_PASSWORDS[account]},
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip())
    return {line.strip() for line in done.stdout.splitlines() if line.strip()}


class TestTheServersAccount:
    def test_it_inserts_across_the_schema(self, mysql_server):
        assert f"INSERT ON `{SCHEMA}`.*" in grants(mysql_server, SERVER)

    def test_it_reads_the_registry_the_gate_checks(self, mysql_server):
        assert can(
            mysql_server,
            SERVER,
            "SELECT 1 FROM `device_enrolment` WHERE `device_id` = 'phone-a' LIMIT 1",
        )

    def test_it_keeps_the_refusal_counters(self, mysql_server):
        assert can(
            mysql_server,
            SERVER,
            "INSERT INTO `refusals` "
            "(`device_id`,`reason`,`attempts`,`rows_refused`,`last_table`,"
            "`first_seen`,`last_seen`) VALUES ('phone-a','no_enrolment',1,1,'battery',1,1) "
            "ON DUPLICATE KEY UPDATE `attempts` = `attempts` + 1",
        )

    def test_it_fills_in_the_device_metadata_row(self, mysql_server):
        """The upsert reads the row it already holds, then updates it."""
        assert can(mysql_server, SERVER, "SELECT `_id`, `model` FROM `aware_device` LIMIT 1")
        assert can(
            mysql_server, SERVER, "UPDATE `aware_device` SET `model` = 'x' WHERE `_id` = 0"
        )

    def test_it_reads_the_column_list_ingest_writes_by(self, mysql_server):
        """Each table is written in the shape it has, and the shape is read from
        information_schema, which lists a table for an account holding any privilege
        on it. Schema-wide INSERT is what makes that list visible."""
        columns = columns_seen_by(mysql_server, SERVER, "battery")

        assert "device_id" in columns
        assert "timestamp" in columns

    def test_it_cannot_read_the_sensor_data_it_writes(self, mysql_server):
        """Ingest delivers rows; reading them back is the dashboard's account."""
        assert not can(mysql_server, SERVER, "SELECT * FROM `battery` LIMIT 1")


class TestTheParticipantAccount:
    def test_it_inserts_across_the_schema(self, mysql_server):
        assert f"INSERT ON `{SCHEMA}`.*" in grants(mysql_server, PARTICIPANT)

    def test_it_cannot_read_the_enrolment_registry(self, mysql_server):
        """The registry names every device in the study and when it joined, and this
        credential is published to every phone."""
        assert not can(mysql_server, PARTICIPANT, "SELECT 1 FROM `device_enrolment` LIMIT 1")

    def test_it_cannot_read_the_refusal_counters(self, mysql_server):
        assert not can(mysql_server, PARTICIPANT, "SELECT 1 FROM `refusals` LIMIT 1")

    def test_it_cannot_read_the_sensor_data_it_writes(self, mysql_server):
        assert not can(mysql_server, PARTICIPANT, "SELECT * FROM `battery` LIMIT 1")

    def test_it_writes_the_study_log_the_gate_exempts(self, mysql_server):
        """A phone's own join event is what every enrolment window is derived from."""
        assert can(
            mysql_server,
            PARTICIPANT,
            "INSERT INTO `aware_studies` (`device_id`,`timestamp`) VALUES ('phone-a',1)",
        )
