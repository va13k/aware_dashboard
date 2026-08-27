"""Tests for the one path that speaks to a phone.

Two of these guard findings that only reading the client produced, and both would
have shipped a mechanism that reaches nobody while looking correct. The client
subscribes to a study-scoped topic built from a study key it parses as an integer,
and every device this deployment has enrolled holds ``0`` there --- so a publisher
addressing the study key publishes into a topic nothing listens on, and says nothing
about it. And the channel name is the last segment of the topic, which is what the
client's own routing keys on.

The third guards a privacy property. The credential a phone carries is served to
every participant in one file, so the only thing separating a participant from
prompting the rest of the study is that the account may not publish at all.
"""

import pathlib

import pytest

from shared_config import messaging


class TestTheTopicAPhoneListensOn:
    """messaging.topic: addressed so the client's own routing finds it."""

    def test_a_channel_is_the_last_segment(self):
        # The client compares the whole topic against `<device_id>/<channel>`, so the
        # channel has to end it rather than appear anywhere in it.
        assert messaging.topic("abc-123", messaging.ESM) == "abc-123/esm"

    def test_a_researcher_notice_has_its_own_notification_channel(self):
        assert messaging.topic("abc-123", messaging.NOTICE_CHANNEL) == "abc-123/notice"

    def test_the_topic_carries_no_study_scope(self):
        # The client's study-scoped subscription is built from a study key it reads
        # with getInt against a text column, which is 0 for every enrolled device.
        # Addressing the study key would publish where nothing is listening.
        assert not messaging.topic("abc-123", messaging.SYNC).startswith("9")
        assert messaging.topic("abc-123", messaging.SYNC).count("/") == 1

    def test_a_channel_the_client_does_not_route_is_refused(self):
        with pytest.raises(ValueError):
            messaging.topic("abc-123", "reminders")

    def test_every_channel_is_one_the_client_acts_on(self):
        client = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "aware-client-main/aware-core/src/main/java/com/aware/Mqtt.java"
        )
        if not client.exists():
            pytest.skip("the Android client is not checked out beside this project")
        source = client.read_text(encoding="utf-8")
        # Read from the client rather than restated: a channel it does not route is a
        # message that arrives, is stored, and does nothing.
        for channel in messaging.CHANNELS:
            assert f'"/{channel}"' in source or f"/{channel}" in source


class TestWhichPortAndWhetherItIsEncrypted:
    """The client reads TLS from the port alone, so the port is the setting."""

    def test_https_puts_participants_on_the_tls_port(self):
        assert messaging.port_for("https") == messaging.TLS_PORT
        assert messaging.uses_tls("https")

    def test_http_puts_them_on_the_plaintext_port(self):
        # 1883 is the one port the client opens as tcp; anything else it opens as ssl,
        # so a deployment with no certificate has to be on this one or the phone's
        # handshake fails against a server presenting nothing.
        assert messaging.port_for("http") == messaging.PLAIN_PORT
        assert not messaging.uses_tls("http")


class TestWhoMayDoWhat:
    """messaging.acl: the shared credential is a phone's, and phones do not publish."""

    def test_a_phone_may_receive_on_every_channel(self):
        rules = messaging.acl()
        participant = rules.split(f"user {messaging.PARTICIPANT_USER}")[1]
        for channel in messaging.CHANNELS:
            assert f"topic read +/{channel}" in participant

    def test_a_phone_may_publish_on_none_of_them(self):
        # The credential is in a config every participant is served, so a phone that
        # could publish could prompt anybody in the study.
        participant = messaging.acl().split(f"user {messaging.PARTICIPANT_USER}")[1]
        assert "topic write" not in participant

    def test_the_server_may_publish_on_every_channel(self):
        publisher = messaging.acl().split(f"user {messaging.PUBLISHER_USER}")[1]
        publisher = publisher.split(f"user {messaging.PARTICIPANT_USER}")[0]
        for channel in messaging.CHANNELS:
            assert f"topic write +/{channel}" in publisher

    def test_the_channels_are_named_rather_than_wildcarded(self):
        # A subscription to `#` is answered by whatever the acl permits, so naming the
        # five channels is what keeps a phone out of $SYS and out of any topic added
        # later without a thought for who can read it.
        assert "topic read #" not in messaging.acl()
        assert "$SYS" not in messaging.acl()

    def test_the_study_scoped_form_the_client_subscribes_to_is_permitted(self):
        # The client subscribes to it whether or not anything publishes there, and a
        # refused subscription is a string of errors on a phone at every connect.
        rules = messaging.acl()
        assert f"topic read {messaging.STUDY_SCOPE}/+/{messaging.ESM}" in rules


class TestTheBrokersOwnConfiguration:
    def test_anonymous_access_is_refused_either_way(self):
        for protocol in ("http", "https"):
            assert "allow_anonymous false" in messaging.broker_config(protocol)

    def test_the_api_reaches_it_over_the_compose_network_either_way(self):
        # The publisher is inside the deployment, so it does not depend on whichever
        # port participants were given.
        for protocol in ("http", "https"):
            assert "listener 1883 0.0.0.0" in messaging.broker_config(protocol)

    def test_a_tls_deployment_opens_the_encrypted_port_with_its_certificate(self):
        config = messaging.broker_config("https", "/certs/full.pem", "/certs/key.pem")
        assert f"listener {messaging.TLS_PORT}" in config
        assert "certfile /certs/full.pem" in config

    def test_a_plaintext_deployment_opens_no_tls_listener(self):
        assert str(messaging.TLS_PORT) not in messaging.broker_config("http")


class TestWhatAPhoneIsServed:
    """messaging.study_settings: the client's own keys, filled in."""

    def test_the_block_turns_the_sensor_on(self):
        settings = messaging.study_settings("host.example", "https", "u", "p")
        assert settings["status_mqtt"] is True

    def test_a_study_with_no_broker_leaves_the_sensor_off(self):
        assert messaging.study_settings("", "http", "", "")["status_mqtt"] is False

    def test_the_port_follows_the_protocol(self):
        assert messaging.study_settings("h", "https", "u", "p")["mqtt_port"] == messaging.TLS_PORT

    def test_delivery_is_at_least_once(self):
        # The phone records what it received, so a duplicate is visible where a
        # silently dropped prompt would not be.
        assert messaging.study_settings("h", "http", "u", "p")["mqtt_qos"] >= 1

    def test_every_key_is_one_the_client_reads(self):
        expected = {
            "status_mqtt",
            "mqtt_server",
            "mqtt_port",
            "mqtt_username",
            "mqtt_password",
            "mqtt_keep_alive",
            "mqtt_qos",
        }
        assert set(messaging.study_settings("h", "http", "u", "p")) == expected


class TestTheRateLimit:
    """messaging.over_limit: what stops a researcher filling somebody's phone.

    Enforced below the interface on purpose. Nothing in the mechanism prevents it,
    and a limit that lives only in a form is a limit that a script does not have.
    """

    def test_a_device_under_the_limit_may_be_sent_another(self):
        assert messaging.over_limit(messaging.QUESTION, messaging.PROMPT_LIMIT - 1) is None

    def test_a_device_at_the_limit_may_not(self):
        refusal = messaging.over_limit(messaging.QUESTION, messaging.PROMPT_LIMIT)
        assert refusal is not None
        # The sentence carries the limit and the window, because a researcher who is
        # refused needs to know when they may try again rather than that they failed.
        assert str(messaging.PROMPT_LIMIT) in refusal
        assert "minutes" in refusal

    def test_a_sync_request_is_allowed_more_often_than_a_prompt(self):
        # One costs a participant nothing and shows them nothing; the other
        # interrupts them. Counting them the same would either throttle a researcher
        # chasing missing data or licence them to interrupt somebody thirty times.
        assert messaging.limit_for(messaging.SYNC_REQUEST) > messaging.limit_for(messaging.QUESTION)

    def test_a_notice_counts_against_the_prompt_limit(self):
        assert messaging.limit_for(messaging.NOTICE) == messaging.PROMPT_LIMIT


class TestTheSentRecord:
    """The one state of a prompt this side owns."""

    def test_the_record_is_kept_where_the_rollup_will_not_find_it(self):
        schema = (
            pathlib.Path(__file__).resolve().parent.parent / "db/dashboard-tables.sql"
        ).read_text(encoding="utf-8")
        block = schema.split(f"CREATE TABLE IF NOT EXISTS `{messaging.SENT_TABLE}`")[1]
        block = block.split("ENGINE=InnoDB")[0]
        # The coverage builder walks every timestamped table it finds, so a record of
        # researcher actions carrying a `timestamp` column would arrive on the
        # coverage grid as a sensor nobody configured.
        assert "`timestamp`" not in block
        assert "`sent_at`" in block

    def test_the_dashboard_may_read_and_write_it(self):
        schema = (
            pathlib.Path(__file__).resolve().parent.parent / "db/dashboard-tables.sql"
        ).read_text(encoding="utf-8")
        assert f"ON `aware_android`.`{messaging.SENT_TABLE}` TO 'aware_analytics'@'%'" in schema


class TestAskingAPhoneForAnUpdate:
    """The request that makes a phone re-read what the study tells it.

    Without it a researcher changes a question or a schedule and then waits on each
    phone's own timer, unable to tell a phone that has not looked yet from one that
    has nothing to report.
    """

    def test_the_action_is_the_clients_own(self):
        client = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "aware-client-main/aware-core/src/main/java/com/aware/Aware.java"
        )
        if not client.exists():
            pytest.skip("the Android client is not checked out beside this project")
        source = client.read_text(encoding="utf-8")
        # Read from the client rather than restated: an action it does not register
        # is a broadcast that arrives and is answered by nothing.
        assert f'"{messaging.CONFIG_ACTION}"' in source
        assert "enqueueStudyConfigSync" in source

    def test_it_travels_on_the_channel_a_phone_re_broadcasts(self):
        # The same channel as a sync request, because both are an Android action the
        # client turns back into an intent rather than something it displays.
        assert messaging.action_for(messaging.UPDATE_REQUEST) == messaging.CONFIG_ACTION
        assert messaging.action_for(messaging.SYNC_REQUEST) == messaging.SYNC_ACTION

    def test_it_is_held_to_the_looser_limit(self):
        # It shows a participant nothing, so counting it against the prompt limit
        # would throttle a researcher rolling out a study change for no benefit.
        assert messaging.limit_for(messaging.UPDATE_REQUEST) == messaging.SYNC_LIMIT
        assert messaging.UPDATE_REQUEST in messaging.QUIET_KINDS
