# Database Migration Strategies

## Overview

Database migrations manage schema changes and data transformations over time. This guide covers migration strategies, versioning, rollback, and best practices.

## Migration Types

### Schema Migrations

**Structure Changes:**
- Add/remove tables
- Add/remove columns
- Change data types
- Add/remove indexes
- Modify constraints

**Example:**
```sql
-- Migration: Add email column to users
ALTER TABLE users ADD COLUMN email VARCHAR(255);

-- Rollback: Remove email column
ALTER TABLE users DROP COLUMN email;
```

### Data Migrations

**Data Transformations:**
- Transform existing data
- Backfill missing values
- Data cleanup
- Bulk updates

**Example:**
```sql
-- Migration: Backfill email from legacy system
UPDATE users 
SET email = (
  SELECT email FROM legacy_users 
  WHERE legacy_users.id = users.legacy_id
)
WHERE email IS NULL;
```

## Migration Tools

### Version Control

**Track Migrations:**
- Sequential versioning (001, 002, 003)
- Timestamp-based (20260115_001)
- Semantic versioning

### Flyway

**Java-based Tool:**
```sql
-- V1__Create_users_table.sql
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

-- V2__Add_email_to_users.sql
ALTER TABLE users ADD COLUMN email VARCHAR(255);
```

### Alembic (Python/SQLAlchemy)

**Python Migration Tool:**
```python
def upgrade():
    op.add_column('users', sa.Column('email', sa.String(255)))

def downgrade():
    op.drop_column('users', 'email')
```

### Liquibase

**Database-Agnostic:**
```xml
<changeSet id="1" author="developer">
    <createTable tableName="users">
        <column name="id" type="int">
            <constraints primaryKey="true"/>
        </column>
        <column name="name" type="varchar(100)"/>
    </createTable>
</changeSet>
```

## Migration Strategies

### Forward-Only

**No Rollback:**
- Simple
- Always move forward
- Risk if issues occur

### Versioned with Rollback

**Reversible Migrations:**
- Each migration has up/down
- Can rollback to previous version
- Safer for production

### Blue-Green Migrations

**Zero-Downtime:**
- Deploy new schema alongside old
- Migrate data gradually
- Switch over when ready
- Keep old schema for rollback

### Expand-Contract Pattern

**Safe Schema Changes:**
1. **Expand:** Add new column, keep old
2. **Migrate:** Populate new column
3. **Contract:** Remove old column

**Example:**
```sql
-- Step 1: Expand (add new column)
ALTER TABLE users ADD COLUMN email_new VARCHAR(255);

-- Step 2: Migrate data
UPDATE users SET email_new = email_old WHERE email_new IS NULL;

-- Step 3: Contract (after verification)
ALTER TABLE users DROP COLUMN email_old;
ALTER TABLE users RENAME COLUMN email_new TO email;
```

## Best Practices

### 1. Idempotent Migrations

**Safe to Re-run:**
```sql
-- Bad: Fails if column exists
ALTER TABLE users ADD COLUMN email VARCHAR(255);

-- Good: Idempotent
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'email'
    ) THEN
        ALTER TABLE users ADD COLUMN email VARCHAR(255);
    END IF;
END $$;
```

### 2. Test Migrations

**Test Environments:**
- Run on dev/staging first
- Test rollback procedures
- Verify data integrity

### 3. Backup Before Migration

**Safety First:**
- Full backup before migration
- Point-in-time recovery option
- Test restore procedure

### 4. Migrate in Batches

**Large Data Migrations:**
```sql
-- Process in chunks
WHILE EXISTS (SELECT 1 FROM users WHERE migrated = false) DO
    UPDATE users 
    SET migrated = true, email = ...
    WHERE id IN (
        SELECT id FROM users 
        WHERE migrated = false 
        LIMIT 1000
    );
END WHILE;
```

### 5. Monitor Performance

**Track Migration:**
- Monitor execution time
- Check resource usage
- Watch for locks

### 6. Document Changes

**Clear Documentation:**
- What changed and why
- Rollback procedures
- Dependencies
- Estimated downtime

## Best Practices Summary

1. **Version control:** Track all migrations
2. **Test thoroughly:** Dev and staging first
3. **Backup first:** Before any migration
4. **Idempotent:** Safe to re-run
5. **Rollback plan:** Test rollback
6. **Batch large migrations:** Process in chunks
7. **Monitor:** Track progress and performance
8. **Document:** Clear change documentation
9. **Zero-downtime:** When possible
10. **Review:** Post-migration review

## Typical steps

Follow this process when planning and executing a database migration:

1. **Assess the change**: Determine if this is a schema migration, data migration, or both; estimate impact
2. **Write the migration**: Create versioned up/down migration scripts using your tool (Alembic, Flyway, etc.)
3. **Write rollback scripts**: Ensure every migration has a tested rollback path
4. **Test on development**: Run the migration against a dev database; verify data integrity
5. **Test on staging**: Run against a staging copy of production data; measure execution time and locks
6. **Take a backup**: Create a full backup of the production database immediately before migration
7. **Execute in production**: Run the migration during a low-traffic window; monitor locks, CPU, and I/O
8. **Verify and document**: Confirm data integrity post-migration; document what changed and any issues

