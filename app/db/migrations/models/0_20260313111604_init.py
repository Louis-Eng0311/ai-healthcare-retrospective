from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `code_groups` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `group_code` VARCHAR(20) NOT NULL UNIQUE,
    `group_name` VARCHAR(100) NOT NULL,
    `description` LONGTEXT,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `codes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(50) NOT NULL,
    `value` VARCHAR(50) NOT NULL,
    `display_name` VARCHAR(100) NOT NULL,
    `description` LONGTEXT,
    `sort_order` INT NOT NULL DEFAULT 0,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `group_code_id` VARCHAR(20) NOT NULL,
    UNIQUE KEY `uid_codes_group_c_0372a2` (`group_code_id`, `code`),
    UNIQUE KEY `uid_codes_group_c_b0eba2` (`group_code_id`, `value`),
    CONSTRAINT `fk_codes_code_gro_d72aee53` FOREIGN KEY (`group_code_id`) REFERENCES `code_groups` (`group_code`) ON DELETE CASCADE,
    KEY `idx_codes_group_c_48c083` (`group_code_id`, `is_active`, `sort_order`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `drug_catalog` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `mfds_item_seq` VARCHAR(100) UNIQUE,
    `name` VARCHAR(255) NOT NULL,
    `manufacturer` VARCHAR(255),
    `ingredients` LONGTEXT,
    `warnings` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_drug_catalo_name_89ccbe` (`name`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `drug_info_cache` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `mfds_item_seq` VARCHAR(100) UNIQUE,
    `drug_name_display` VARCHAR(255),
    `manufacturer` VARCHAR(255),
    `efficacy` LONGTEXT,
    `dosage_info` LONGTEXT,
    `precautions` LONGTEXT,
    `interactions` LONGTEXT,
    `side_effects` LONGTEXT,
    `storage_method` VARCHAR(255),
    `expires_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_drug_info_c_expires_c0c53d` (`expires_at`),
    KEY `idx_drug_info_c_drug_na_823cfa` (`drug_name_display`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `phone_verifications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `phone` VARCHAR(30) NOT NULL,
    `token` VARCHAR(100) NOT NULL UNIQUE,
    `verified_at` DATETIME(6),
    `expires_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY `idx_phone_verif_phone_915268` (`phone`, `expires_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `roles` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(9) NOT NULL UNIQUE,
    `name` VARCHAR(30) NOT NULL UNIQUE,
    `description` VARCHAR(255),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(40) NOT NULL UNIQUE,
    `password_hash` VARCHAR(128),
    `name` VARCHAR(20) NOT NULL,
    `gender` VARCHAR(6) NOT NULL COMMENT 'MALE: MALE\nFEMALE: FEMALE',
    `birth_date` DATE NOT NULL,
    `phone` VARCHAR(20) NOT NULL UNIQUE,
    `nickname` VARCHAR(50),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `auth_accounts` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `provider` VARCHAR(20) NOT NULL,
    `provider_user_id` VARCHAR(120),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_auth_accoun_provide_0c6510` (`provider`, `provider_user_id`),
    CONSTRAINT `fk_auth_acc_users_89fd16ec` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `notification_settings` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `intake_reminder` BOOL NOT NULL DEFAULT 1,
    `missed_alert` BOOL NOT NULL DEFAULT 1,
    `ocr_done` BOOL NOT NULL DEFAULT 1,
    `guide_ready` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_notifica_users_ea1f99f3` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `patients` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `display_name` VARCHAR(100),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `owner_user_id` BIGINT NOT NULL,
    `user_id` BIGINT UNIQUE,
    CONSTRAINT `fk_patients_users_bc0d086e` FOREIGN KEY (`owner_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_patients_users_90e23b31` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `caregiver_patient_links` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(30) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `revoked_at` DATETIME(6),
    `caregiver_user_id` BIGINT NOT NULL,
    `patient_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_caregiver_p_caregiv_a5c37c` (`caregiver_user_id`, `patient_id`),
    CONSTRAINT `fk_caregive_users_cd714b05` FOREIGN KEY (`caregiver_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_caregive_patients_e0d7e74d` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_sessions` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `mode` VARCHAR(30),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_chat_ses_patients_6c9ad11b` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_chat_ses_users_520002c0` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_sessio_user_id_1e4c0d` (`user_id`, `created_at`),
    KEY `idx_chat_sessio_patient_e4c386` (`patient_id`, `created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `chat_messages` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `role` VARCHAR(20) NOT NULL,
    `content` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `session_id` BIGINT NOT NULL,
    CONSTRAINT `fk_chat_mes_chat_ses_0d4a2737` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_messag_session_fb3c4b` (`session_id`, `created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `documents` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `file_url` VARCHAR(500) NOT NULL,
    `original_filename` VARCHAR(255),
    `file_type` VARCHAR(30),
    `file_size` BIGINT,
    `checksum` VARCHAR(255),
    `status` VARCHAR(30) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `deleted_at` DATETIME(6),
    `patient_id` BIGINT NOT NULL,
    `uploaded_by_user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_document_patients_7f26fcee` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_document_users_425860e1` FOREIGN KEY (`uploaded_by_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_documents_patient_4027bf` (`patient_id`, `created_at`),
    KEY `idx_documents_uploade_32177e` (`uploaded_by_user_id`, `created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `dur_checks` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `trigger_type` VARCHAR(50) NOT NULL,
    `status` VARCHAR(30) NOT NULL,
    `error_code` VARCHAR(100),
    `error_message` LONGTEXT,
    `started_at` DATETIME(6),
    `finished_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    `triggered_by_user_id` BIGINT,
    CONSTRAINT `fk_dur_chec_patients_688e35da` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dur_chec_users_38350555` FOREIGN KEY (`triggered_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
    KEY `idx_dur_checks_patient_b5f5a4` (`patient_id`, `created_at`),
    KEY `idx_dur_checks_status_f84123` (`status`, `created_at`),
    KEY `idx_dur_checks_trigger_eb0d2e` (`trigger_type`, `created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `guides` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(30) NOT NULL,
    `content` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    `source_document_id` BIGINT,
    CONSTRAINT `fk_guides_patients_eaf6d3a2` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_guides_document_f3c5c365` FOREIGN KEY (`source_document_id`) REFERENCES `documents` (`id`) ON DELETE SET NULL,
    KEY `idx_guides_patient_a3fb33` (`patient_id`, `created_at`),
    KEY `idx_guides_status_309901` (`status`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `guide_feedback` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `rating` INT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `guide_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_guide_fe_guides_ca1c5bbf` FOREIGN KEY (`guide_id`) REFERENCES `guides` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_guide_fe_users_8b0361e8` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_guide_feedb_guide_i_dd1cc9` (`guide_id`, `created_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `guide_summaries` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `caregiver_summary` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `guide_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_guide_su_guides_71a250e5` FOREIGN KEY (`guide_id`) REFERENCES `guides` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `invitation_codes` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(100) NOT NULL UNIQUE,
    `expires_at` DATETIME(6),
    `used_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_invitati_patients_eefe4ef8` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `ocr_jobs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `status` VARCHAR(30) NOT NULL,
    `retry_count` INT NOT NULL DEFAULT 0,
    `error_code` VARCHAR(100),
    `error_message` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `document_id` BIGINT NOT NULL,
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ocr_jobs_document_3e5e0a3f` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ocr_jobs_patients_70933d1d` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    KEY `idx_ocr_jobs_patient_30a314` (`patient_id`, `status`),
    KEY `idx_ocr_jobs_documen_d7c30a` (`document_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `extracted_meds` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `dosage_text` VARCHAR(255),
    `frequency_text` VARCHAR(255),
    `duration_text` VARCHAR(255),
    `confidence` DECIMAL(5,4),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `ocr_job_id` BIGINT NOT NULL,
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_extracte_ocr_jobs_dffe48f1` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_extracte_patients_ac74f869` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    KEY `idx_extracted_m_patient_ae29c1` (`patient_id`),
    KEY `idx_extracted_m_ocr_job_b4a045` (`ocr_job_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `ocr_raw_texts` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `raw_text` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `ocr_job_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_ocr_raw__ocr_jobs_90aa4b64` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_jobs` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `patient_meds` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `source_document_id` BIGINT,
    `source_ocr_job_id` BIGINT,
    `source_extracted_med_id` BIGINT,
    `display_name` VARCHAR(255) NOT NULL,
    `dosage` VARCHAR(255),
    `route` VARCHAR(100),
    `notes` LONGTEXT,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `confirmed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `drug_catalog_id` BIGINT,
    `drug_info_cache_id` BIGINT,
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_patient__drug_cat_4a06997b` FOREIGN KEY (`drug_catalog_id`) REFERENCES `drug_catalog` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_patient__drug_inf_e9295d6d` FOREIGN KEY (`drug_info_cache_id`) REFERENCES `drug_info_cache` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_patient__patients_c8e64c5e` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    KEY `idx_patient_med_patient_65e6f5` (`patient_id`, `is_active`),
    KEY `idx_patient_med_drug_ca_4857e8` (`drug_catalog_id`),
    KEY `idx_patient_med_drug_in_189f71` (`drug_info_cache_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `dur_alerts` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `alert_type` VARCHAR(50) NOT NULL,
    `level` VARCHAR(30) NOT NULL,
    `basis_json` LONGTEXT,
    `message` LONGTEXT,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `dur_check_id` BIGINT NOT NULL,
    `patient_id` BIGINT NOT NULL,
    `patient_med_id` BIGINT NOT NULL,
    `related_patient_med_id` BIGINT,
    CONSTRAINT `fk_dur_aler_dur_chec_f3559fcf` FOREIGN KEY (`dur_check_id`) REFERENCES `dur_checks` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dur_aler_patients_0852b146` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dur_aler_patient__4d0ba2eb` FOREIGN KEY (`patient_med_id`) REFERENCES `patient_meds` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_dur_aler_patient__2f7e0965` FOREIGN KEY (`related_patient_med_id`) REFERENCES `patient_meds` (`id`) ON DELETE SET NULL,
    KEY `idx_dur_alerts_patient_2c985b` (`patient_id`, `created_at`),
    KEY `idx_dur_alerts_patient_391f54` (`patient_med_id`, `created_at`),
    KEY `idx_dur_alerts_alert_t_0f33bb` (`alert_type`, `level`),
    KEY `idx_dur_alerts_dur_che_3808a4` (`dur_check_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `med_schedules` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `start_date` DATE,
    `end_date` DATE,
    `status` VARCHAR(30) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    `patient_med_id` BIGINT NOT NULL,
    CONSTRAINT `fk_med_sche_patients_1a87dd03` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_med_sche_patient__21c24790` FOREIGN KEY (`patient_med_id`) REFERENCES `patient_meds` (`id`) ON DELETE CASCADE,
    KEY `idx_med_schedul_patient_4a5e58` (`patient_id`, `status`),
    KEY `idx_med_schedul_patient_334f7b` (`patient_med_id`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `med_schedule_times` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `time_of_day` TIME(6) NOT NULL,
    `days_of_week` VARCHAR(100),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `schedule_id` BIGINT NOT NULL,
    CONSTRAINT `fk_med_sche_med_sche_969c03e5` FOREIGN KEY (`schedule_id`) REFERENCES `med_schedules` (`id`) ON DELETE CASCADE,
    KEY `idx_med_schedul_schedul_6df293` (`schedule_id`, `is_active`),
    KEY `idx_med_schedul_time_of_716e26` (`time_of_day`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `intake_logs` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `scheduled_at` DATETIME(6),
    `taken_at` DATETIME(6),
    `status` VARCHAR(30) NOT NULL,
    `note` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    `patient_med_id` BIGINT NOT NULL,
    `recorded_by_user_id` BIGINT,
    `schedule_id` BIGINT,
    `schedule_time_id` BIGINT,
    CONSTRAINT `fk_intake_l_patients_c8b9c5a9` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_intake_l_patient__bf358c3a` FOREIGN KEY (`patient_med_id`) REFERENCES `patient_meds` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_intake_l_users_0d221710` FOREIGN KEY (`recorded_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_intake_l_med_sche_e6efdcf2` FOREIGN KEY (`schedule_id`) REFERENCES `med_schedules` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_intake_l_med_sche_0d2a2dc9` FOREIGN KEY (`schedule_time_id`) REFERENCES `med_schedule_times` (`id`) ON DELETE SET NULL,
    KEY `idx_intake_logs_patient_53eb1f` (`patient_id`, `scheduled_at`),
    KEY `idx_intake_logs_patient_b2137a` (`patient_med_id`, `scheduled_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `patient_profiles` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `birth_year` INT,
    `sex` VARCHAR(20),
    `height_cm` DECIMAL(6,2),
    `weight_kg` DECIMAL(6,2),
    `bmi` DECIMAL(6,2),
    `conditions` LONGTEXT,
    `allergies` LONGTEXT,
    `notes` LONGTEXT,
    `meds_json` LONGTEXT,
    `is_smoker` BOOL,
    `is_hospitalized` BOOL,
    `discharge_date` DATE,
    `avg_sleep_hours_per_day` DECIMAL(3,1),
    `avg_cig_packs_per_week` DECIMAL(4,1),
    `avg_alcohol_bottles_per_week` DECIMAL(4,1),
    `avg_exercise_minutes_per_day` INT,
    `is_deleted` BOOL NOT NULL DEFAULT 0,
    `deleted_at` DATETIME(6),
    `deleted_by_role` VARCHAR(20),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `deleted_by_user_id` BIGINT,
    `patient_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_patient__users_c34c1565` FOREIGN KEY (`deleted_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_patient__patients_e4b7d852` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `patient_profile_history` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `actor_role` VARCHAR(20),
    `action` VARCHAR(20),
    `snapshot_json` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `actor_user_id` BIGINT,
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_patient__users_27c2f44a` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_patient__patients_31f97c9f` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `refresh_tokens` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `token_hash` VARCHAR(255) NOT NULL,
    `expires_at` DATETIME(6) NOT NULL,
    `revoked_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_refresh__users_1c3fe0a4` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_refresh_tok_user_id_9490e0` (`user_id`, `expires_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `reminders` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `type` VARCHAR(30) NOT NULL,
    `channel` VARCHAR(30),
    `remind_at` DATETIME(6),
    `status` VARCHAR(30),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    `schedule_id` BIGINT,
    `schedule_time_id` BIGINT,
    CONSTRAINT `fk_reminder_patients_34feade1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_reminder_med_sche_cf5245f4` FOREIGN KEY (`schedule_id`) REFERENCES `med_schedules` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_reminder_med_sche_e7268a54` FOREIGN KEY (`schedule_time_id`) REFERENCES `med_schedule_times` (`id`) ON DELETE SET NULL,
    KEY `idx_reminders_patient_b51bb2` (`patient_id`, `remind_at`),
    KEY `idx_reminders_status_a71afa` (`status`, `remind_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `notifications` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `type` VARCHAR(50) NOT NULL,
    `title` VARCHAR(255),
    `body` LONGTEXT,
    `payload_json` LONGTEXT,
    `sent_at` DATETIME(6),
    `read_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT,
    `reminder_id` BIGINT,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_notifica_patients_60b5cb95` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_notifica_reminder_d29f4431` FOREIGN KEY (`reminder_id`) REFERENCES `reminders` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_notifica_users_ca29871f` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_notificatio_user_id_8d780e` (`user_id`, `created_at`),
    KEY `idx_notificatio_user_id_87be33` (`user_id`, `read_at`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_devices` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `platform` VARCHAR(30),
    `push_token` VARCHAR(500) NOT NULL,
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_user_dev_users_452e228e` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_user_device_user_id_80b679` (`user_id`, `is_active`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_roles` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `assigned_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `role_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_user_roles_user_id_63f1a8` (`user_id`, `role_id`),
    CONSTRAINT `fk_user_rol_roles_65d4d60a` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_user_rol_users_55397de2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "Q5wAOkBNPz+siBozqY1P2X7+P/BFVDs="
)
