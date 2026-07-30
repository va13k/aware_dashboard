CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

-- The participant passwords below are only a first-boot seed: on a fresh data
-- directory zz-participant-password.sh replaces them with the per-deployment
-- password generated into .env. CREATE USER IF NOT EXISTS means replaying this
-- file on later restarts never resets that password.
CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_analytics'@'%' IDENTIFIED BY 'analyticspass';
GRANT SELECT ON aware_android.* TO 'aware_analytics'@'%';
GRANT SELECT ON aware_ios.*     TO 'aware_analytics'@'%';

FLUSH PRIVILEGES;
