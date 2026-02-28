# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a monorepo containing two projects:

1. **`ZK-auto-clock-in-python/`** - Python Admin (FastAPI backend)
2. **`clockin-worker/`** - Cloudflare Worker (clockin executor)

Most work will be in the Python Admin directory.

## Common Commands (Python Admin)

All commands below require being in the `ZK-auto-clock-in-python/` directory:

```bash
cd ZK-auto-clock-in-python
```

### Development Setup

```bash
# Quick setup (recommended)
bash setup_venv.sh    # or setup_venv.bat on Windows
bash start.sh         # or start.bat on Windows

# Manual setup
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python scripts/init_db.py
```

### Running the Application

```bash
# Development with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Database Operations

```bash
# Initialize/reset database
python scripts/init_db.py

# Backup database
python scripts/backup_db.py

# Check database integrity
python scripts/check_db.py

# Check clockin results
python scripts/check_result.py

# Fix clockin count
python scripts/fix_clockin_count.py
```

### Testing

```bash
# Run tests
pytest tests/

# Run API tests
python scripts/test_api.py
python scripts/test_apis.py
```

## Architecture Overview (Python Admin)

### Application Structure

```
FastAPI Application (app/main.py)
├── Lifecycle Management (lifespan)
│   ├── Database Initialization
│   └── Scheduler Startup
├── API Routes (app/api/)
│   ├── Authentication (login/logout)
│   ├── User Management
│   ├── Clockin Operations
│   ├── Configuration
│   └── Maintenance
├── Services Layer (app/services/)
│   ├── ClockinService - Core clockin logic
│   ├── UserService - User CRUD operations
│   ├── PoetryService - Comment/image content
│   └── TaskService - Task state management
└── Core (app/core/)
    ├── Database - SQLAlchemy async setup
    ├── Security - JWT, password hashing
    └── Scheduler - APScheduler configuration
```

### Key Design Patterns

**1. Async/Await Throughout**
- All database operations use SQLAlchemy async (`AsyncSession`, `aiosqlite`)
- HTTP calls use `httpx.AsyncClient`
- Services are static async methods

**2. Service Layer Pattern**
- Business logic lives in `app/services/`
- API routes are thin wrappers that call services
- Services handle database transactions and external API calls

**3. Dependency Injection**
- Database session: `Depends(get_db)`
- Authentication: `Depends(verify_session)`
- Use `get_db` for database access, never create sessions directly in routes

**4. Pydantic Validation**
- Request/Response models in `app/models/schemas.py`
- Database models in `app/models/database.py`
- Note: `UserResponse.password` is intentionally included (needed for clockin-worker API)

### Authentication Flow

1. Login validates username/password against admin credentials (from `.env`)
2. Creates JWT token (24h expiry) AND database Session record
3. API routes require `verify_session` dependency which validates:
   - JWT token is valid
   - Session exists in database and not expired

### Clockin Flow

When triggering clockin for users:

1. **ClockinService.trigger_all_users()** - Iterates through enabled users
2. **ClockinService.call_clockin_api()** - Calls external clockin-worker API
   - Fetches comments from PoetryService
   - Fetches images from PoetryService
   - Makes HTTP POST to `CLOCKIN_API_URL/clockin`
   - Retries on 5xx errors (max 2 retries)
3. **ClockinService.save_clockin_result()** - Persists to database
   - Creates ClockinResult record
   - Updates DailySummary aggregate
4. **UserService.update_clockin_info()** - Updates user's last_clockin and count

### Scheduler

Two scheduled jobs run via APScheduler:
- **Clockin job**: Configured via `SCHEDULE_CRON` (default: UTC 16:10 / Beijing 0:10)
- **Cleanup job**: Runs daily at 3:00 AM UTC, deletes records older than `RETENTION_DAYS`

### External Dependencies

- **clockin-worker API**: External service that actually performs the clockin on 精夏平台
  - URL: `CLOCKIN_API_URL` from `.env`
  - Auth: Bearer token in `Authorization` header
  - Request: `{username, password, clockin_type, options: {...}}`
  - Response: `{success, results: {home, sports, daily}, ...}`

## Important Conventions

### Database Models
- All models inherit from `Base` (declarative base)
- Use `generate_uuid()` for primary keys (string UUIDs)
- Include `to_dict()` method for JSON serialization
- Index commonly queried fields (enabled, date, username)

### Error Handling
- Services return `{'success': bool, 'error': str}` dicts
- API routes raise `HTTPException` for client errors
- Global exception handler in `main.py` catches unexpected errors

### Time Handling
- Database stores UTC timestamps
- User-facing dates use `YYYY-MM-DD` string format
- Cron expressions use UTC (Beijing is UTC+8)

### Configuration
- All settings in `app/config.py` using pydantic-settings
- Values read from `.env` file
- Access via `settings.setting_name` globally

### File Locations

| Purpose | Location |
|---------|----------|
| API Routes | `ZK-auto-clock-in-python/app/api/*.py` |
| Business Logic | `ZK-auto-clock-in-python/app/services/*.py` |
| DB Models | `ZK-auto-clock-in-python/app/models/database.py` |
| Pydantic Schemas | `ZK-auto-clock-in-python/app/models/schemas.py` |
| Static Files | `ZK-auto-clock-in-python/app/ui/` |
| Utility Scripts | `ZK-auto-clock-in-python/scripts/*.py` |
| Database | `ZK-auto-clock-in-python/database/zk_admin.db` |
| Logs | `ZK-auto-clock-in-python/logs/*.log` |
| Environment | `ZK-auto-clock-in-python/.env` |

## Frontend Integration

- UI is vanilla HTML/JS in `app/ui/pages/`
- Static assets served from `/assets` route
- No API prefix for page routes (`/dashboard`, `/admin`)
- API routes use `/api/*` prefix
- Token stored in localStorage, sent in `Authorization: Bearer` header

## Common Tasks

When modifying clockin behavior:
1. Check `ClockinService.call_clockin_api()` for external API call
2. Check `PoetryService` for comment/image fetching logic
3. Update `ClockinResult` model if storing new data

When adding new API endpoints:
1. Create Pydantic schemas in `models/schemas.py`
2. Add service method in `services/*.py`
3. Create route in `api/*.py` with `verify_session` dependency
4. Register router in `app/main.py`

When modifying database:
1. Update model in `models/database.py`
2. Run `python scripts/init_db.py` to recreate tables
3. Note: This will wipe existing data

## Clockin Worker (Brief)

The `clockin-worker/` directory contains a Cloudflare Worker that:
- Receives clockin requests from Python Admin
- Performs actual HTTP requests to 精夏平台
- Returns results back to Python Admin

Key files:
- `wrangler.toml` - Cloudflare Worker configuration
- `src/index.js` - Main worker entry point
- `src/clockin.js` - Clockin logic
