SET FOREIGN_KEY_CHECKS = 0;

-- ========================
-- API LOGS
-- ========================
DROP TABLE IF EXISTS api_logs;
CREATE TABLE api_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  method VARCHAR(255),
  url VARCHAR(255),
  client_ip VARCHAR(255),
  headers LONGTEXT,
  query_params LONGTEXT,
  request_body LONGTEXT,
  user_agent VARCHAR(255),
  response_status INT,
  response_size INT,
  response_body LONGTEXT,
  process_time FLOAT,
  raw_request_body LONGTEXT,
  error_message LONGTEXT,
  error_details LONGTEXT,
  username VARCHAR(255),
  INDEX ix_api_logs_method (method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- ACTIVITY LOG
-- ========================
DROP TABLE IF EXISTS activity_log;
CREATE TABLE activity_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(255) NOT NULL,
  type VARCHAR(255) NOT NULL,
  details LONGTEXT,
  platform VARCHAR(255) DEFAULT 'WEB',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- ANNOUNCEMENT
-- ========================
DROP TABLE IF EXISTS announcement;
CREATE TABLE announcement (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid CHAR(36) NOT NULL,
  user_role VARCHAR(255) NOT NULL,
  title VARCHAR(255) NOT NULL,
  text LONGTEXT NOT NULL,
  created_by VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY idx_announcement_uuid (uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- APP VERSIONS
-- ========================
DROP TABLE IF EXISTS app_versions;
CREATE TABLE app_versions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid CHAR(36) NOT NULL,
  version VARCHAR(255),
  created_at DATETIME,
  UNIQUE KEY idx_app_versions_uuid (uuid),
  INDEX ix_app_versions_version (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- CALLBACK API LOGS
-- ========================
DROP TABLE IF EXISTS callback_api_logs;
CREATE TABLE callback_api_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  url VARCHAR(255) NOT NULL,
  source VARCHAR(50) NOT NULL,
  log_source VARCHAR(50) NOT NULL,
  request_body JSON,
  response_status INT,
  response_message LONGTEXT,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  additional_info JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- CHANGE PASSWORD LOGS
-- ========================
DROP TABLE IF EXISTS change_password_logs;
CREATE TABLE change_password_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(255) NOT NULL,
  password VARCHAR(255) NOT NULL,
  changed_by VARCHAR(255) NOT NULL,
  changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- IP WHITELISTS
-- ========================
DROP TABLE IF EXISTS ip_whitelists;
CREATE TABLE ip_whitelists (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ip_address VARCHAR(45) NOT NULL,
  entity_type VARCHAR(50) NOT NULL,
  entity_id BIGINT NOT NULL,
  description LONGTEXT,
  is_active TINYINT(1) DEFAULT 1,
  created_by BIGINT,
  updated_by BIGINT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- LOGIN ACTIVITY
-- ========================
DROP TABLE IF EXISTS login_activity;
CREATE TABLE login_activity (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255),
  username VARCHAR(255) NOT NULL,
  user_role VARCHAR(255),
  login_date DATETIME,
  ip VARCHAR(255),
  location VARCHAR(255),
  browser VARCHAR(255),
  os VARCHAR(255),
  device VARCHAR(255),
  attempt INT DEFAULT 0,
  conn_number INT DEFAULT 0,
  remarks VARCHAR(255),
  date DATE NOT NULL,
  INDEX ix_login_activity_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- NOTIFICATION PANEL
-- ========================
DROP TABLE IF EXISTS notification_panel;
CREATE TABLE notification_panel (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid CHAR(36) NOT NULL,
  sender VARCHAR(255),
  receiver VARCHAR(255),
  title VARCHAR(255),
  details VARCHAR(255),
  status VARCHAR(255),
  response_link VARCHAR(255),
  last_update DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY idx_notification_uuid (uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- USERS
-- ========================
DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid CHAR(36) NOT NULL,
  username VARCHAR(255),
  password VARCHAR(255),
  email VARCHAR(255),
  photo VARCHAR(255),
  users_roles VARCHAR(255),
  acc_type VARCHAR(255),
  user_id VARCHAR(255),
  name VARCHAR(255),
  email_status VARCHAR(255),
  phone_status VARCHAR(255),
  phone VARCHAR(255),
  account_status VARCHAR(255),
  max_login_web INT,
  logged_in_web INT,
  last_login VARCHAR(255),
  login_ip VARCHAR(255),
  first_login TINYINT(1),
  parking_enabled TINYINT(1),
  max_login_mobile INT,
  logged_in_mobile INT,
  total_max_login INT,
  total_logged_in INT,
  fcm_token VARCHAR(255),
  is_tc_accepted TINYINT(1) NOT NULL DEFAULT 1,
  is_2fa_enabled TINYINT(1) DEFAULT 1,
  UNIQUE KEY idx_users_uuid (uuid),
  UNIQUE KEY ix_users_email (email),
  INDEX ix_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- USER ANNOUNCEMENT LIST
-- ========================
DROP TABLE IF EXISTS user_announcement_list;
CREATE TABLE user_announcement_list (
  announcement_id INT NOT NULL,
  username VARCHAR(255) NOT NULL DEFAULT 'ALL',
  PRIMARY KEY (announcement_id, username),
  CONSTRAINT fk_user_announcement_list_announcement
    FOREIGN KEY (announcement_id) REFERENCES announcement(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- USER NOTIFICATIONS
-- ========================
DROP TABLE IF EXISTS user_notifications;
CREATE TABLE user_notifications (
  user_id INT NOT NULL,
  notification_id INT NOT NULL,
  `read` TINYINT(1) DEFAULT 0,
  PRIMARY KEY (user_id, notification_id),
  CONSTRAINT fk_user_notifications_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_user_notifications_notification
    FOREIGN KEY (notification_id) REFERENCES notification_panel(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========================
-- USER TOKENS
-- ========================
DROP TABLE IF EXISTS user_tokens;
CREATE TABLE user_tokens (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(255) NOT NULL,
  user_id INT NOT NULL,
  token VARCHAR(512),
  refresh_token VARCHAR(512),
  status VARCHAR(255) NOT NULL DEFAULT 'Valid',
  expires_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  device VARCHAR(255),
  token_type VARCHAR(255),
  agents VARCHAR(255),
  INDEX ix_user_tokens_username (username),
  INDEX ix_user_tokens_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
