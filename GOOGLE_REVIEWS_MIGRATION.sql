-- ============================================================
-- OPTIONAL GOOGLE REVIEWS SUPPORT
-- Safe additive migration for the original project.
-- It only adds a cache field to heritage_sites.
-- ============================================================

USE defaultdb;

SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'heritage_sites'
      AND COLUMN_NAME = 'GooglePlaceID'
);

SET @sql = IF(
    @column_exists = 0,
    'ALTER TABLE heritage_sites ADD COLUMN GooglePlaceID VARCHAR(255) NULL',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE INDEX idx_heritage_google_place
    ON heritage_sites(GooglePlaceID);

SELECT 'Google Reviews support is ready.' AS Status;
