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
"""

from shared_config import database

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
