CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

-- The passwords below are only a first-boot seed: on a fresh data directory
-- zz-participant-password.sh replaces them with the per-deployment passwords
-- generated into .env. CREATE USER IF NOT EXISTS means replaying this file on later
-- restarts never resets those passwords.

-- The account an Android phone opens the database with itself, which is what the
-- direct dataflow asks of a phone. Inserts and nothing else: a phone delivers rows
-- and reads nothing back, and its credential travels in the study config every phone
-- downloads.
CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

-- The account the iOS micro-server writes with. iOS is webservice-only --- an iPhone
-- has no direct-database client --- so this is a server's credential, and the reads
-- its ingest makes are granted beside the tables they name.
CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

-- The Android micro-server's own account. On the webservice dataflow every write is
-- the server's and no phone opens MySQL at all, so ingest authenticates as the server
-- rather than as a participant.
--
-- Schema-wide INSERT is the data itself, and it is also what makes each table visible
-- in information_schema, which is where ingest reads the column list it writes a table
-- in the shape of: a table is listed there for an account holding any privilege on it.
-- The rows ingest reads back are granted table by table, beside the tables they name,
-- so this account sees the registry it checks and the metadata row it fills in rather
-- than the sensor data it writes.
CREATE USER IF NOT EXISTS 'aware_android_server'@'%' IDENTIFIED BY 'serverpass';
GRANT INSERT ON aware_android.* TO 'aware_android_server'@'%';

CREATE USER IF NOT EXISTS 'aware_analytics'@'%' IDENTIFIED BY 'analyticspass';
GRANT SELECT ON aware_android.* TO 'aware_analytics'@'%';
GRANT SELECT ON aware_ios.*     TO 'aware_analytics'@'%';

FLUSH PRIVILEGES;
