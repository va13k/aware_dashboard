"""Tests for resolving one declared database into what each reader can use.

The point of the module is that copying the address around is the wrong answer.
Who is asking changes it: a phone needs somewhere reachable from a participant's
network, while a service sitting beside MySQL on the compose network needs the name
it has there. Sending a container to the public host would route it out to the
internet and back for a neighbour, or fail outright when the published port is
bound to loopback on the webservice dataflow.

So these check both halves of that distinction, and that a change to the
declaration reaches every reader rather than leaving one pointing at the old
server --- which is the failure the module exists to prevent, and the one that looks
exactly like a study that stopped collecting.

Who writes is resolved here too: each dataflow puts a different holder on the ingest
path, and the account each holds is what its credential belongs to.
"""

from shared_config import database, dataflow

BUNDLED = {
    "host": "db.internal",
    "android": {"port": 3306, "name": "aware_android"},
    "ios": {"port": 3306, "name": "aware_ios"},
}

EXTERNAL = {
    "host": "db.uni.example.org",
    "android": {"port": 3307, "name": "study_android"},
    "ios": {"port": 3307, "name": "study_ios"},
}


class TestTheBoundary:
    def test_a_bundled_database_is_reached_by_its_compose_name(self):
        """Not the public host: that would send a container out to the internet for
        a neighbour, and the published port may be loopback-only."""
        assert database.service_host(BUNDLED) == "mysql"

    def test_a_declared_external_host_is_used_as_given(self):
        """There is no internal route to it, and sending everything there was the
        point of declaring it."""
        assert database.service_host(EXTERNAL) == "db.uni.example.org"

    def test_every_internal_alias_means_the_bundled_database(self):
        for alias in ("", "db.internal", "mysql", "localhost", "127.0.0.1", "0.0.0.0"):
            assert database.is_internal(alias), alias

    def test_a_real_host_is_not_mistaken_for_an_alias(self):
        assert not database.is_internal("db.uni.example.org")
        assert not database.is_internal("10.0.0.5")

    def test_an_undeclared_host_reads_as_the_internal_name(self):
        assert database.declared_host({}) == "db.internal"
        assert database.service_host({}) == "mysql"


class TestResolution:
    def test_the_readers_follow_a_changed_declaration(self):
        """The whole purpose: one edit, and nothing is left pointing at the old
        server."""
        resolved = database.resolved_env(EXTERNAL, "s3cret")

        assert resolved["DB_SERVICE_HOST"] == "db.uni.example.org"
        for url in (resolved["ANDROID_DATABASE_URL"], resolved["IOS_DATABASE_URL"]):
            assert "db.uni.example.org:3307" in url
            assert "mysql:3306" not in url

    def test_each_platform_gets_its_own_schema(self):
        resolved = database.resolved_env(BUNDLED, "pw")

        assert resolved["ANDROID_DATABASE_URL"].endswith("/aware_android")
        assert resolved["IOS_DATABASE_URL"].endswith("/aware_ios")

    def test_the_analytics_account_reads_the_data(self):
        url = database.analytics_url(BUNDLED, "android", "pw")

        assert f"//{database.ANALYTICS_USER}:pw@" in url

    def test_a_missing_port_falls_back_to_mysqls_rather_than_being_guessed(self):
        assert database.platform_port({"android": {}}, "android") == 3306
        assert database.platform_port({"android": {"port": "bad"}}, "android") == 3306

    def test_a_missing_schema_name_falls_back_per_platform(self):
        assert database.platform_schema({}, "android") == "aware_android"
        assert database.platform_schema({}, "ios") == "aware_ios"

    def test_the_password_comes_from_the_deployment_not_the_study(self):
        """It belongs to the deployment's own analytics account, so it is passed in
        rather than read out of the study model."""
        assert "given-password" in database.analytics_url(BUNDLED, "android", "given-password")


ANDROID_ACCOUNTS = {
    "host": "db.internal",
    "android": {
        "port": 3306,
        "name": "aware_android",
        "username": "aware_android_participant",
        "password": "phone-pw",
        "server_username": "aware_android_server",
        "server_password": "server-pw",
    },
}


class TestWhoWrites:
    """Which account the study's Android writes authenticate as.

    A phone opens the database itself on the direct path and the micro-server
    performs every write on the webservice one, so the holder differs and so does the
    account. Reading one answer from here is what keeps the generated micro-server
    configuration, the deploy that settles the credential and the Configurator's
    password field from each choosing a different account.
    """

    def test_a_phone_writes_with_the_participant_account(self):
        assert database.android_credentials(ANDROID_ACCOUNTS, dataflow.DIRECT) == (
            "aware_android_participant",
            "phone-pw",
        )

    def test_the_server_writes_with_its_own_account(self):
        assert database.android_credentials(ANDROID_ACCOUNTS, dataflow.WEBSERVICE) == (
            "aware_android_server",
            "server-pw",
        )

    def test_the_two_accounts_hold_separate_passwords(self):
        """The participant one is published to every phone on the direct path, and the
        server's account may read the enrolment registry a phone's may not."""
        phone = database.android_credentials(ANDROID_ACCOUNTS, dataflow.DIRECT)
        server = database.android_credentials(ANDROID_ACCOUNTS, dataflow.WEBSERVICE)

        assert phone[0] != server[0]
        assert phone[1] != server[1]

    def test_the_micro_server_reads_its_account_whatever_the_study_runs(self):
        """Its instance is configured on either dataflow, so the configuration names
        the same account either way."""
        assert database.android_server_credentials(ANDROID_ACCOUNTS) == (
            "aware_android_server",
            "server-pw",
        )

    def test_an_account_the_model_omits_falls_back_to_the_one_created(self):
        """A study written before the field carried a server account still names the
        account the bootstrap SQL creates."""
        assert database.android_server_credentials({"android": {}}) == (
            database.ANDROID_SERVER_USER,
            "",
        )
        assert database.android_credentials({}, dataflow.DIRECT) == (
            database.ANDROID_PARTICIPANT_USER,
            "",
        )

    def test_each_password_is_recorded_under_its_own_variable(self):
        """`.env` holds one variable per account, so writing back a change to one
        never advertises it as the other's."""
        keys = {
            choice: database.android_ingest_account(choice)["env_key"]
            for choice in (dataflow.DIRECT, dataflow.WEBSERVICE)
        }

        assert keys[dataflow.DIRECT] == "PARTICIPANT_DB_PASSWORD"
        assert keys[dataflow.WEBSERVICE] == "ANDROID_SERVER_DB_PASSWORD"

    def test_an_unknown_dataflow_reads_as_the_direct_path(self):
        """The same answer `dataflow.declared` gives such a study."""
        assert database.android_ingest_account("nonsense") == (
            database.android_ingest_account(dataflow.DIRECT)
        )


class TestWhatIsAskedOfTheConnection:
    """database.tls_required / tls_authority: one answer, and who gets to give it.

    Encryption is settled on a database this deployment runs and declared on one the
    researcher names, because the second is somebody else's server: a MySQL built
    without TLS, or a MariaDB that generated no certificate, is a database this
    software could otherwise never be pointed at.
    """

    def test_a_bundled_database_is_encrypted_whatever_is_declared(self):
        # Both ends are ours, so an answer arriving for it is a form field that was
        # never asked rather than a decision to apply.
        for stated in (True, False):
            assert database.tls_required({**BUNDLED, "tls": {"require": stated}})

    def test_a_named_database_declaring_nothing_is_encrypted(self):
        # Silence has meant TLS since every account was created requiring it, so the
        # arrival of the setting cannot turn a running study's encryption off.
        assert database.tls_required(EXTERNAL)

    def test_a_named_database_can_say_it_cannot_encrypt(self):
        assert not database.tls_required({**EXTERNAL, "tls": {"require": False}})

    def test_the_authority_is_read_from_the_connection_block(self):
        declared = {**EXTERNAL, "tls": {"ca_certificate": "PEM"}}
        assert database.tls_authority(declared) == "PEM"

    def test_a_study_written_before_the_block_keeps_its_authority(self):
        # The same certificate, in the only place a study used to be able to keep
        # it. Losing it on an upgrade would leave devices unable to verify a server
        # they were verifying yesterday.
        legacy = {**EXTERNAL, "android": {**EXTERNAL["android"], "ca_certificate": "PEM"}}
        assert database.tls_authority(legacy) == "PEM"

    def test_the_connection_block_wins_over_the_older_place(self):
        both = {
            **EXTERNAL,
            "tls": {"ca_certificate": "NEW"},
            "android": {**EXTERNAL["android"], "ca_certificate": "OLD"},
        }
        assert database.tls_authority(both) == "NEW"

    def test_an_unencrypted_study_has_nothing_to_verify(self):
        # Publishing an authority for a connection no client will check is a promise
        # every interface would then have to un-make.
        declared = {**EXTERNAL, "tls": {"require": False, "ca_certificate": "PEM"}}
        assert database.tls_authority(declared) == ""

    def test_the_deployments_own_readers_are_told(self):
        # The API reads `.env` and not the study model, so the answer travels as a
        # variable or it does not travel at all.
        assert database.resolved_env(EXTERNAL, "pw")["DB_REQUIRE_TLS"] == "1"
        assert (
            database.resolved_env({**EXTERNAL, "tls": {"require": False}}, "pw")[
                "DB_REQUIRE_TLS"
            ]
            == "0"
        )

    def test_declaring_one_part_leaves_the_other_alone(self):
        databases = {**EXTERNAL, "tls": {"require": True, "ca_certificate": "PEM"}}
        database.declare_tls(databases, require=False)
        assert databases["tls"] == {"require": False, "ca_certificate": "PEM"}


class TestEveryAccountTheDeploymentOpensItWith:
    """profiles: one list, so no path provisions the accounts another path needs.

    The accounts were derived separately by the deploy, by the check and by the
    services that connect, and a database ended up holding the ones the Android path
    knew about and missing the iOS micro-server's and the dashboard's. That failure
    is invisible from the ingest side --- the study collects --- and total from the
    reading side, which is the shape these guard.
    """

    def test_both_platforms_and_the_dashboard_are_named(self):
        assert [entry["username"] for entry in database.profiles(EXTERNAL)] == [
            "aware_android_participant",
            "aware_android_server",
            "aware_ios_participant",
            "aware_analytics",
            "aware_backup",
        ]

    def test_each_account_carries_the_schema_it_works_in(self):
        schemas = {entry["username"]: entry["schemas"] for entry in database.profiles(EXTERNAL)}
        assert schemas["aware_android_server"] == ["study_android"]
        assert schemas["aware_ios_participant"] == ["study_ios"]

    def test_the_dashboard_reads_both_of_them(self):
        """It is handed a URL into each schema, so an account granted on one is a
        dashboard that shows half a study and reports the other half as empty."""
        schemas = {entry["username"]: entry["schemas"] for entry in database.profiles(EXTERNAL)}
        assert schemas["aware_analytics"] == ["study_android", "study_ios"]

    def test_who_writes_is_stated_rather_than_read_from_the_name(self):
        """`aware_ios_participant` is the iOS micro-server's account and carries
        rows; `aware_analytics` reads them. Their names say the opposite."""
        writes = {entry["username"]: entry["writes"] for entry in database.profiles(EXTERNAL)}
        assert writes["aware_ios_participant"] is True
        assert writes["aware_analytics"] is False

    def _by_name(self, *secrets):
        return {
            entry["username"]: entry for entry in database.profiles(EXTERNAL, *secrets)
        }

    def test_the_dashboard_password_comes_from_the_deployment(self):
        assert self._by_name("chosen")["aware_analytics"]["password"] == "chosen"
        assert (
            self._by_name()["aware_analytics"]["password"]
            == database.ANALYTICS_SEED_PASSWORD
        )

    def test_the_backup_account_reads_and_writes_both_schemas(self):
        """A dump reads every table and a restore drops and recreates them, so this
        one works across the study rather than in one platform's half of it."""
        backup = self._by_name()["aware_backup"]

        assert backup["schemas"] == ["study_android", "study_ios"]
        assert backup["privilege"] == "ALL PRIVILEGES"

    def test_the_backup_account_holds_no_seed_password(self):
        """Nothing in db/*.sql creates it, so there is no first-boot password to
        fall back to: a blank is a deployment that has not settled one, which the
        backup page reports rather than working around."""
        assert self._by_name()["aware_backup"]["password"] == ""
        assert self._by_name("", "chosen")["aware_backup"]["password"] == "chosen"

    def test_what_each_account_is_granted_is_stated_on_it(self):
        """One flag with two answers cannot separate an account that appends rows
        from one that drops and recreates the tables they live in."""
        granted = {
            entry["username"]: entry["privilege"]
            for entry in database.profiles(EXTERNAL)
        }

        assert granted["aware_ios_participant"] == "INSERT"
        assert granted["aware_analytics"] == "SELECT"
        assert granted["aware_backup"] == "ALL PRIVILEGES"


class TestWhoAdministersTheStudysDatabase:
    """database.admin_password: the administrator's, not the container's.

    One field used to carry both the bundled server's `root` password and the
    administrator of whichever database the study named. MySQL bakes root's into the
    data directory at first start and ignores the variable after, so naming a managed
    server overwrote the value the bundled one still needed --- and moving back
    authenticated to it with somebody else's password.
    """

    def test_the_administrator_has_a_key_of_its_own(self):
        env = {
            database.ADMIN_PASSWORD_ENV: "the administrator's",
            "MYSQL_ROOT_PASSWORD": "the container's",
        }
        assert database.admin_password(env) == "the administrator's"

    def test_a_deployment_written_before_the_split_still_opens_its_database(self):
        # Upgraded in place: .env holds only the older key, and it is the password
        # that deployment's database actually takes.
        assert database.admin_password({"MYSQL_ROOT_PASSWORD": "older"}) == "older"

    def test_nothing_named_reads_as_nothing(self):
        assert database.admin_password({}) == ""
        assert database.admin_password({database.ADMIN_PASSWORD_ENV: "  "}) == ""
