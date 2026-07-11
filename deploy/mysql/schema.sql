-- workbuddy-tool / antigravity 空库 DDL
-- 本地 docker-compose 与生产均可复用；启动时 init_db() 也会幂等建表。

CREATE DATABASE IF NOT EXISTS antigravity
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE antigravity;

CREATE TABLE IF NOT EXISTS accounts (
  uid VARCHAR(64) NOT NULL PRIMARY KEY,
  nickname VARCHAR(255) NOT NULL DEFAULT '',
  platform VARCHAR(32) NOT NULL DEFAULT 'codebuddy',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  status_reason VARCHAR(512) NOT NULL DEFAULT '',
  plan_type VARCHAR(32) NOT NULL DEFAULT 'free',
  domain VARCHAR(255) NOT NULL DEFAULT '',
  enterprise_id VARCHAR(128) NOT NULL DEFAULT '',
  enterprise_name VARCHAR(255) NOT NULL DEFAULT '',
  auth_token TEXT,
  auth_raw MEDIUMTEXT,
  ck TEXT,
  api_key TEXT,
  profile_raw MEDIUMTEXT,
  usage_raw MEDIUMTEXT,
  account_group VARCHAR(128) NOT NULL DEFAULT '',
  created_at DATETIME NULL,
  last_used DATETIME NULL,
  last_checkin_time DATETIME NULL,
  streak_days INT NOT NULL DEFAULT 0,
  checkin_rewards JSON NULL,
  daily_credit INT NOT NULL DEFAULT 0,
  total_credits INT NOT NULL DEFAULT 0,
  hourly_suggestions INT NOT NULL DEFAULT 0,
  hourly_suggestions_limit INT NOT NULL DEFAULT 0,
  weekly_chat INT NOT NULL DEFAULT 0,
  weekly_chat_limit INT NOT NULL DEFAULT 0,
  credits_remaining DOUBLE NOT NULL DEFAULT 0,
  credits_total DOUBLE NOT NULL DEFAULT 0,
  reset_time DATETIME NULL,
  quota_last_updated DATETIME NULL,
  quota_last_error TEXT NULL,
  quota_last_error_at DATETIME NULL,
  quota_packages JSON NULL,
  quota_payment_type VARCHAR(64) NOT NULL DEFAULT '',
  INDEX idx_accounts_platform (platform),
  INDEX idx_accounts_last_used (last_used)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings (
  `key` VARCHAR(128) NOT NULL PRIMARY KEY,
  `value` MEDIUMTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
