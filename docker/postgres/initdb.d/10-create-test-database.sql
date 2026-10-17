-- Runs once, when the database volume is first created.
-- The integration tests create and drop tables, so they get a database of their own; its name
-- must end in "_test" (the test fixtures refuse anything else).
CREATE DATABASE app_test;
