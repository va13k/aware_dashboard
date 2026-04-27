CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

-- Read-only user restricted to the analytics API container only
CREATE USER IF NOT EXISTS 'aware_analytics'@'aware_dashboard_api' IDENTIFIED BY 'analyticspass';
GRANT SELECT ON aware_android.* TO 'aware_analytics'@'aware_dashboard_api';
GRANT SELECT ON aware_ios.*     TO 'aware_analytics'@'aware_dashboard_api';

FLUSH PRIVILEGES;