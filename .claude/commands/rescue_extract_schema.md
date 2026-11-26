# Extract Schema

Extract database schema from the source project.

## Arguments
- `$1` - ADW ID
- `$2` - Path to source project

## Instructions

Analyze the source project at `$2` to extract its database schema.

### 1. Schema Source Detection

Look for schema definitions in:
- Prisma schema (`prisma/schema.prisma`)
- SQLAlchemy models (`models.py`, `models/`)
- Mongoose schemas (`models/*.js`)
- TypeORM entities (`entities/`)
- Sequelize models
- Raw SQL migrations
- JSON structure files (for NoSQL)
- Supabase type definitions

### 2. Schema Extraction

For each table/collection, extract:

**Table Information:**
- Table name
- Primary key field and type
- All columns with types
- Nullable vs required fields
- Default values

**Relationships:**
- Foreign key references
- One-to-many relationships
- Many-to-many relationships (junction tables)

**Indexes:**
- Unique constraints
- Composite indexes
- Full-text search indexes

### 3. Schema Normalization

Convert to a normalized format compatible with our SQLAlchemy models:
- Map source types to PostgreSQL types
- Identify fields that need `organization_id` for multi-tenancy
- Note any incompatible patterns (e.g., MongoDB-specific features)

## Output

Create `discovery/schema_extracted.sql` with CREATE TABLE statements:

```sql
-- Extracted from source project
-- Original ORM: Prisma
-- Original DB: PostgreSQL

-- Note: Add organization_id FK for multi-tenancy during rescue

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255),
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    content TEXT,
    author_id UUID NOT NULL REFERENCES users(id),
    published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_posts_author ON posts(author_id);
CREATE INDEX idx_posts_published ON posts(published) WHERE published = TRUE;
```

Also create `discovery/schema_analysis.json`:

```json
{
  "source_orm": "prisma",
  "source_db": "postgresql",
  "tables": [
    {
      "name": "users",
      "primary_key": {"field": "id", "type": "UUID"},
      "columns": [
        {"name": "email", "type": "VARCHAR(255)", "nullable": false, "unique": true},
        {"name": "name", "type": "VARCHAR(255)", "nullable": true},
        {"name": "avatar_url", "type": "TEXT", "nullable": true},
        {"name": "created_at", "type": "TIMESTAMP", "default": "NOW()"},
        {"name": "updated_at", "type": "TIMESTAMP", "default": "NOW()"}
      ],
      "relationships": [],
      "indexes": []
    },
    {
      "name": "posts",
      "primary_key": {"field": "id", "type": "UUID"},
      "columns": [
        {"name": "title", "type": "VARCHAR(255)", "nullable": false},
        {"name": "content", "type": "TEXT", "nullable": true},
        {"name": "author_id", "type": "UUID", "nullable": false},
        {"name": "published", "type": "BOOLEAN", "default": false}
      ],
      "relationships": [
        {"type": "many_to_one", "field": "author_id", "references": "users.id"}
      ],
      "indexes": [
        {"name": "idx_posts_author", "columns": ["author_id"]},
        {"name": "idx_posts_published", "columns": ["published"], "where": "published = TRUE"}
      ]
    }
  ],
  "needs_multitenancy": ["users", "posts"],
  "incompatibilities": []
}
```

## Validation

- File `discovery/schema_extracted.sql` exists
- File `discovery/schema_analysis.json` exists and is valid JSON
- All detected tables are documented

$ARGUMENTS
