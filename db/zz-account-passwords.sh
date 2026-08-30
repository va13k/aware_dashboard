#!/bin/sh
# Give every account 00-bootstrap.sql creates this deployment's own password.
#
# Runs once, on an empty data directory, and alphabetically after the bootstrap so
# every account already exists. The passwords set here survive later restarts:
# init_all.sql only ever uses CREATE USER IF NOT EXISTS, even though --init-file
# replays it on every start.
#
# The bootstrap creates each account with a word written into this repository, which
# is the same word in every deployment of this software. That is acceptable for the
# length of the initialisation --- the server is reachable only over its socket until
# the entrypoint finishes, so nothing on a network can use one --- and unacceptable
# for a second longer. On the direct dataflow the port this server then opens is
# bound to every address a participant might reach it from.
#
# So a missing variable is fatal rather than a warning. Carrying on would leave a
# database whose password is published, and a deployment that looks finished is the
# worst place to find that out. setup/deploy_config.py generates all four before
# `docker compose up` and writes them to .env, which compose passes to this service.
set -e

apply() {
    mysql --protocol=socket -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
$1
FLUSH PRIVILEGES;
SQL
}

require() {
    if [ -z "$2" ]; then
        echo "zz-account-passwords: $1 is unset." >&2
        echo "  Every account this creates would keep the password written into" >&2
        echo "  db/00-bootstrap.sql, which is public. Run ./setup.sh, which" >&2
        echo "  generates them, rather than starting the database on its own." >&2
        exit 1
    fi
}

require PARTICIPANT_DB_PASSWORD "$PARTICIPANT_DB_PASSWORD"
require ANDROID_SERVER_DB_PASSWORD "$ANDROID_SERVER_DB_PASSWORD"
require ANALYTICS_DB_PASSWORD "$ANALYTICS_DB_PASSWORD"

# The accounts phones open the database with on the direct dataflow, and that the
# iOS micro-server holds on its own. One password for both platforms' participants
# because a study publishes one, and a phone is given the account for its own.
apply "ALTER USER 'aware_android_participant'@'%' IDENTIFIED BY '${PARTICIPANT_DB_PASSWORD}';
ALTER USER 'aware_ios_participant'@'%' IDENTIFIED BY '${PARTICIPANT_DB_PASSWORD}';"

# The Android micro-server's own, which performs every write on the webservice
# dataflow. Separate from the participants' because that one is published to every
# phone in the study on the direct path, and this account may read the enrolment
# registry and update device rows that a phone's account may not.
apply "ALTER USER 'aware_android_server'@'%' IDENTIFIED BY '${ANDROID_SERVER_DB_PASSWORD}';"

# The dashboard's own reader. It holds SELECT over both schemas --- every row of
# every participant's data --- so it is the one seed worth leaving least.
apply "ALTER USER 'aware_analytics'@'%' IDENTIFIED BY '${ANALYTICS_DB_PASSWORD}';"

echo "zz-account-passwords: applied this deployment's passwords to all four accounts." >&2
