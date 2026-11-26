# Scan Project Structure

Scan the source project to identify tech stack and structure.

## Arguments
- `$1` - ADW ID
- `$2` - Path to source project

## Instructions

Scan the project at `$2` and identify:

### 1. Tech Stack Detection

**Backend Framework:**
- FastAPI, Flask, Express, Django, Next.js API routes, NestJS, or none
- Look for: `main.py`, `app.py`, `server.js`, `index.ts`, `manage.py`

**Database:**
- PostgreSQL, SQLite, MySQL, MongoDB, Supabase, Prisma, JSON files, or none
- Look for: connection strings, ORM configs, schema files

**Frontend Framework:**
- React, Vue, Svelte, Next.js, vanilla JS
- Look for: `package.json` dependencies, file extensions

**State Management:**
- Redux, Context API, Zustand, MobX, Recoil, React Query, SWR
- Look for: store configs, provider wrappers, hooks usage

**Package Manager:**
- npm, yarn, pnpm, pip, poetry
- Look for: lock files (package-lock.json, yarn.lock, pnpm-lock.yaml)

### 2. Project Structure Analysis

- Directory layout (src/, app/, pages/, components/, api/)
- Entry points (main files for backend and frontend)
- Config files (.env, tsconfig.json, vite.config.ts)
- Total lines of code estimation

### 3. Styling Detection (CRITICAL)

Look for multiple styling approaches:
- **CSS Modules**: `import styles from '*.module.css'`
- **Tailwind**: `className="flex items-center ..."`, `tailwind.config.js`
- **Styled-components**: `styled.div`, `import styled from`
- **Emotion**: `css` prop, `@emotion/react`
- **SASS/SCSS**: `.scss` files, `sass` in dependencies
- **Inline styles**: `style={{ }}` patterns
- **Global CSS**: plain `.css` imports

Count how many approaches are used. Flag if 3+ methods detected.

### 4. Initial Red Flags

Detect these issues:
- Multiple conflicting styling approaches (3+)
- Forked/modified files in `node_modules` or vendored copies
- Very large codebase (>50k LOC frontend, >30k LOC backend)
- No clear entry point or build system

## Output

Create `discovery/structure_report.json`:

```json
{
  "backend": {
    "framework": "express | fastapi | next-api | django | flask | none",
    "entry_point": "path/to/main or null",
    "detected_patterns": ["rest", "graphql"],
    "loc_estimate": 5000
  },
  "database": {
    "type": "postgres | sqlite | mongodb | json_file | supabase | none",
    "connection_method": "prisma | raw_sql | mongoose | supabase-js | sqlalchemy",
    "schema_location": "path or null"
  },
  "frontend": {
    "framework": "react | vue | svelte | next",
    "entry_point": "path/to/main",
    "state_management": ["redux", "context"],
    "loc_estimate": 12000
  },
  "styling": {
    "methods_detected": ["tailwind", "css_modules", "inline"],
    "primary_method": "tailwind",
    "has_chaos": false,
    "chaos_files": []
  },
  "structure": {
    "has_separation": true,
    "directories": ["src", "api", "components"],
    "config_files": [".env", "tsconfig.json"],
    "total_loc": 17000,
    "package_manager": "npm"
  },
  "red_flags": {
    "multiple_styling": false,
    "forked_modules": false,
    "oversized": false,
    "no_entry_point": false
  }
}
```

## Validation

- File `discovery/structure_report.json` exists and is valid JSON
- All required top-level keys are present: `backend`, `database`, `frontend`, `styling`, `structure`, `red_flags`

$ARGUMENTS
