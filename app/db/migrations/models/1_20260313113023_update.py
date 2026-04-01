from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `guides` DROP FOREIGN KEY `fk_guides_document_f3c5c365`;
        ALTER TABLE `guides` RENAME COLUMN `source_document_id` TO `regenerated_from_id`;
        ALTER TABLE `guides` RENAME COLUMN `content` TO `failure_message`;
        ALTER TABLE `guides` ADD `created_by_user_id` BIGINT;
        ALTER TABLE `guides` ADD `caregiver_summary` JSON;
        ALTER TABLE `guides` ADD `failure_code` VARCHAR(100);
        ALTER TABLE `guides` ADD `content_text` LONGTEXT;
        ALTER TABLE `guides` ADD `version` INT NOT NULL DEFAULT 1;
        ALTER TABLE `guides` ADD `content_json` JSON;
        ALTER TABLE `guides` ADD `document_id` BIGINT NOT NULL;
        ALTER TABLE `guides` ADD `disclaimer` VARCHAR(255) NOT NULL DEFAULT '본 가이드는 의료 자문이 아닌 참고용 정보입니다.';
        ALTER TABLE `guides` ALTER COLUMN `status` SET DEFAULT 'GENERATING';
        ALTER TABLE `guides` MODIFY COLUMN `status` VARCHAR(20) NOT NULL COMMENT 'GENERATING: GENERATING\nDONE: DONE\nFAILED: FAILED' DEFAULT 'GENERATING';
        ALTER TABLE `guides` MODIFY COLUMN `status` VARCHAR(20) NOT NULL COMMENT 'GENERATING: GENERATING\nDONE: DONE\nFAILED: FAILED' DEFAULT 'GENERATING';
        DROP TABLE IF EXISTS `guide_summaries`;
        ALTER TABLE `guides` ADD CONSTRAINT `fk_guides_document_3d4c6b8e` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE;
        ALTER TABLE `guides` ADD CONSTRAINT `fk_guides_users_6ca7f4ec` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL;
        ALTER TABLE `guides` ADD CONSTRAINT `fk_guides_guides_179a92eb` FOREIGN KEY (`regenerated_from_id`) REFERENCES `guides` (`id`) ON DELETE SET NULL;
        ALTER TABLE `guides` ADD INDEX `idx_guides_patient_730c29` (`patient_id`, `version`);
        ALTER TABLE `guides` ADD INDEX `idx_guides_documen_5a69b2` (`document_id`, `created_at`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `guides` DROP INDEX `idx_guides_documen_5a69b2`;
        ALTER TABLE `guides` DROP INDEX `idx_guides_patient_730c29`;
        ALTER TABLE `guides` DROP FOREIGN KEY `fk_guides_guides_179a92eb`;
        ALTER TABLE `guides` DROP FOREIGN KEY `fk_guides_users_6ca7f4ec`;
        ALTER TABLE `guides` DROP FOREIGN KEY `fk_guides_document_3d4c6b8e`;
        ALTER TABLE `guides` RENAME COLUMN `regenerated_from_id` TO `source_document_id`;
        ALTER TABLE `guides` RENAME COLUMN `failure_message` TO `content`;
        ALTER TABLE `guides` DROP COLUMN `created_by_user_id`;
        ALTER TABLE `guides` DROP COLUMN `caregiver_summary`;
        ALTER TABLE `guides` DROP COLUMN `failure_code`;
        ALTER TABLE `guides` DROP COLUMN `content_text`;
        ALTER TABLE `guides` DROP COLUMN `version`;
        ALTER TABLE `guides` DROP COLUMN `content_json`;
        ALTER TABLE `guides` DROP COLUMN `document_id`;
        ALTER TABLE `guides` DROP COLUMN `disclaimer`;
        ALTER TABLE `guides` MODIFY COLUMN `status` VARCHAR(30) NOT NULL;
        ALTER TABLE `guides` ALTER COLUMN `status` DROP DEFAULT;
        ALTER TABLE `guides` MODIFY COLUMN `status` VARCHAR(30) NOT NULL;
        ALTER TABLE `guides` ADD CONSTRAINT `fk_guides_document_f3c5c365` FOREIGN KEY (`source_document_id`) REFERENCES `documents` (`id`) ON DELETE SET NULL;"""


MODELS_STATE = (
    "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"
)
