CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

CREATE USER IF NOT EXISTS 'aware_admin'@'%' IDENTIFIED BY 'adminpass';
GRANT ALL PRIVILEGES ON aware_ios.*     TO 'aware_admin'@'%';
GRANT ALL PRIVILEGES ON aware_android.* TO 'aware_admin'@'%';

CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT, CREATE ON aware_ios.* TO 'aware_ios_participant'@'%';

FLUSH PRIVILEGES;