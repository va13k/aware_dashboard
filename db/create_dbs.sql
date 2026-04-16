CREATE DATABASE IF NOT EXISTS aware_ios;
CREATE DATABASE IF NOT EXISTS aware_android;

CREATE USER IF NOT EXISTS 'aware_android_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_android.* TO 'aware_android_participant'@'%';

CREATE USER IF NOT EXISTS 'aware_ios_participant'@'%' IDENTIFIED BY 'participantpass';
GRANT INSERT ON aware_ios.* TO 'aware_ios_participant'@'%';

FLUSH PRIVILEGES;