PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;
PRAGMA cache_size = -2048;
PRAGMA temp_store = MEMORY;

CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    balance_cents INTEGER NOT NULL CHECK (balance_cents >= 0)
);
CREATE TABLE transfers (
    id INTEGER PRIMARY KEY,
    sender_id INTEGER NOT NULL REFERENCES accounts(id),
    receiver_id INTEGER NOT NULL REFERENCES accounts(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
);
INSERT INTO accounts VALUES (1, 'Alice', 10000), (2, 'Bob', 5000), (3, 'Carol', 2500);
CREATE INDEX transfers_sender ON transfers(sender_id);

BEGIN IMMEDIATE;
UPDATE accounts SET balance_cents = balance_cents - 1250 WHERE id = 1;
UPDATE accounts SET balance_cents = balance_cents + 1250 WHERE id = 2;
INSERT INTO transfers VALUES (1, 1, 2, 1250);
COMMIT;

BEGIN IMMEDIATE;
UPDATE accounts SET balance_cents = balance_cents - 500 WHERE id = 2;
UPDATE accounts SET balance_cents = balance_cents + 500 WHERE id = 3;
INSERT INTO transfers VALUES (2, 2, 3, 500);
COMMIT;

BEGIN;
UPDATE accounts SET balance_cents = 0 WHERE id = 1;
ROLLBACK;

INSERT INTO accounts VALUES (4, 'Temporary', 0);
DELETE FROM accounts WHERE id = 4;
