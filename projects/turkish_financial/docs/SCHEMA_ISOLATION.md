# Database Schema Isolation

The Turkish Financial Data Scraper project now uses its own isolated database schema to keep all project tables separate from other applications using the same database.

## What Changed

### Schema Configuration

- **Default Schema Name**: `turkish_financial`
- **Configurable**: Set via `DB_SCHEMA` environment variable
- **Automatic Creation**: Schema is created automatically on first run

### Implementation Details

1. **Schema Creation**: The schema is created automatically when `DatabaseManager` is initialized
2. **Search Path**: All database connections set `search_path` to use the project schema first, then `public`
3. **Table Isolation**: All tables are created in the project's schema:
   - `kap_reports`
   - `bist_companies`
   - `bist_index_members`
   - `tradingview_sectors_tr`
   - `tradingview_industry_tr`
   - `historical_price_emtia`
   - `cryptocurrency_symbols`
   - `kap_report_sentiment`

## Configuration

Add to your `.env` file:

```env
DB_SCHEMA=turkish_financial
```

Or use a different schema name:

```env
DB_SCHEMA=my_custom_schema
```

## Benefits

1. **Isolation**: Project tables don't conflict with other applications
2. **Organization**: All related tables are grouped in one schema
3. **Security**: Can grant schema-specific permissions
4. **Cleanup**: Easy to drop entire schema if needed
5. **Multi-tenancy**: Can run multiple instances with different schemas

## Migration

If you have existing data in the `public` schema:

1. **Option 1**: Keep using `public` schema (set `DB_SCHEMA=public`)
2. **Option 2**: Migrate data to new schema:
   ```sql
   -- Connect to your database
   psql -h nuq-postgres -U postgres -d backtofuture
   
   -- Create schema
   CREATE SCHEMA turkish_financial;
   
   -- Move tables (example for one table)
   ALTER TABLE kap_reports SET SCHEMA turkish_financial;
   -- Repeat for all tables
   ```

## Verification

To verify the schema is being used:

```sql
-- Connect to database
psql -h nuq-postgres -U postgres -d backtofuture

-- List schemas
\dn

-- List tables in schema
\dt turkish_financial.*

-- Check current search_path
SHOW search_path;
```

## Technical Details

- **Connection Pooling**: Each connection from the pool has `search_path` set automatically
- **Table References**: All table creation uses `schema.table` format
- **Foreign Keys**: Foreign key references use schema-qualified table names
- **Indexes**: All indexes are created in the project schema

## Troubleshooting

### Schema Not Found Error

If you get "schema does not exist" errors:
1. Ensure `DB_SCHEMA` is set in `.env`
2. Run the application once to auto-create the schema
3. Or manually create: `CREATE SCHEMA turkish_financial;`

### Permission Errors

If you get permission errors:
```sql
GRANT ALL ON SCHEMA turkish_financial TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA turkish_financial TO your_user;
```

### Tables in Wrong Schema

If tables were created in `public` schema:
1. Set `DB_SCHEMA=public` in `.env` to continue using them
2. Or migrate tables to new schema (see Migration section above)
