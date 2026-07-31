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
│   ├── WorkerApiService - Worker API management & health tracking
│   ├── ActiveTaskService - Real-time task tracking (singleton)
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

1. **ClockinService.trigger_all_users()** - Parallel execution with controlled concurrency
   - Uses semaphore to limit concurrent tasks (configurable via `PARALLEL_TASKS`)
   - Creates API queue to pre-allocate Worker APIs and avoid race conditions
   - Executes all user tasks in parallel using `asyncio.gather()`
   - Implements multi-round retry for failed users (up to 3 rounds by default)

2. **WorkerApiService.get_next_api()** - Round-robin API selection
   - Selects next available Worker API using round-robin with lock
   - Skips unhealthy APIs (low success rate or recent failures)
   - Returns `None` if no APIs are available

3. **ClockinService.call_clockin_api()** - Calls external clockin-worker API
   - Fetches comments from PoetryService
   - Fetches images from PoetryService
   - Registers active task in ActiveTaskService for real-time tracking
   - Makes HTTP POST to Worker API URL
   - Implements intelligent retry mechanism with error-specific delays:
     - Timeout errors: standard `CLOCKIN_RETRY_DELAY` (default 3s)
     - Rate limit (429): longer `CLOCKIN_RATE_LIMIT_DELAY` (default 10s)
     - Connection errors: short 1s delay
     - Other errors: half of retry delay
   - Tracks Worker API health (marks success/failure)
   - Cleans up active task on completion

4. **ClockinService.save_clockin_result()** - Persists to database
   - Creates ClockinResult record with `details_json` containing per-type results (`{home, sports, daily}`)
   - Updates DailySummary aggregate

5. **UserService.update_clockin_info()** - Updates user's last_clockin and count

### Worker API Management System

The system supports multiple Worker APIs for load balancing and redundancy:

- **Round-robin selection**: APIs are selected in rotation using thread-safe lock
- **Health tracking**: Each API tracks `total_requests`, `total_success`, `total_failure`, `failure_count`
- **Availability field**: Backend sets `available` boolean based on success rate and consecutive failures — **do not re-derive health from frontend rate calculations**
- **Auto-skipping**: Unavailable APIs (`available=false`) are automatically skipped
- **Admin interface**: Add/remove/manage APIs via sidebar → "Worker API" page
- **Statistics**: View success rates and request counts for each API

**Configuration**:
- Health threshold: APIs with < 50% success rate or 3+ consecutive failures are marked unavailable
- Recovery: Failed APIs recover after 5 minutes of no failures

**Important**: Always maintain at least 2 healthy Worker APIs for redundancy.

### Scheduler

Two scheduled jobs run via APScheduler:
- **Clockin job**: Configured via `SCHEDULE_CRON` (default: UTC 16:10 / Beijing 0:10)
- **Cleanup job**: Runs daily at 3:00 AM UTC, deletes records older than `RETENTION_DAYS`

### Active Task Tracking

The `ActiveTaskService` (singleton pattern) tracks all currently executing clockin tasks:

- **Real-time monitoring**: View active tasks on "概览" page with live pulse indicator and top bar badge
- **Task lifecycle**: Tasks are registered when started, cleaned up when completed/failed
- **Per-task details**: Includes user info, Worker API used, start time, elapsed time
- **API endpoint**: `GET /api/clockin/active-tasks` returns current active tasks

This prevents duplicate processing and provides visibility into system state.

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

### ClockinResult Data Structure

The `ClockinResult.to_dict()` returns:
- `details` — parsed from `details_json`, contains per-type results:
  ```json
  {
    "home": {"success": true, ...},
    "sports": {"success": true, ...},
    "daily": {"success": false, ...}
  }
  ```
- `sports_comment`, `daily_comment` — direct string fields
- `sports_comment_api`, `daily_comment_api` — API provider codes (e.g. `poetry_all`, `hitokoto_all`)

**Important**: Frontend must use `r.details` (not `r.results`) to access per-type clockin status.

### WorkerApi Data Structure

The `WorkerApi.to_dict()` returns:
- `available` (boolean) — whether the API is healthy; **use this field for health display**
- `total_requests`, `total_success`, `total_failure` — lifetime counters
- `failure_count` — consecutive failure count
- `enabled` — whether the API is enabled by admin

**Important**: Do not re-derive health from `total_success / total_requests` — use the `available` field.

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

## Frontend Architecture

### Tech Stack

- **CSS Framework**: Tailwind CSS (CDN) + DaisyUI 4.x component library
- **Theme**: DaisyUI `light` theme with custom color overrides
- **JavaScript**: Vanilla JS, no framework — single `app.js` file
- **No build step**: All dependencies loaded via CDN

### Design System

| Token | Value | Usage |
|-------|-------|-------|
| `primary` | `#4A90E2` | Brand color, buttons, links |
| `success` | `#52C41A` | Enabled, success indicators |
| `error` | `#FF4D4F` | Failure, delete actions |
| `base-100` | `#FFFFFF` | Card surfaces |
| `base-200` | `#F8F9FA` | Page canvas, input backgrounds |
| `base-300` | `#F0F1F3` | Borders, dividers |
| `neutral` | `#333333` | Primary text |
| Muted text | `#999999` | Secondary text |
| Shadows | `0 1px 3px rgba(0,0,0,0.04)` | Card elevation |

### UI Layout (SPA with Sidebar Navigation)

The admin panel is a single-page application with 5 views:

```
┌──────────────────────────────────────────────┐
│  侧边栏 (220px)  │  顶部栏 (标题 + 活动任务) │
│                   │                           │
│  ⚡ 打卡系统       │  主内容区（按路由切换）    │
│                   │                           │
│  📊 概览           │                           │
│  👥 用户管理       │                           │
│  📋 打卡记录       │                           │
│  🔗 Worker API    │                           │
│  ⚙ 系统设置       │                           │
│                   │                           │
│  🚪 退出登录       │  底部状态栏               │
└───────────────────┴───────────────────────────┘
```

- **Hash routing**: `#/dashboard`, `#/users`, `#/records`, `#/apis`, `#/settings`
- **Sidebar**: Collapsible on desktop (icon-only mode), slide-over on mobile
- **Drawers**: Right-side slide-in panels for user/API forms (not center modals)
- **DaisyUI components**: `card`, `table`, `badge`, `toggle`, `collapse`, `progress`, `select`, `input`

### Frontend Files

| File | Purpose |
|------|---------|
| `app/ui/pages/index.html` | Main SPA page (sidebar + 5 sections + drawer panels) |
| `app/ui/pages/login.html` | Login page |
| `app/ui/pages/404.html` | Nginx decoy page |
| `app/ui/assets/app.js` | All SPA logic (routing, data loading, rendering) |
| `app/ui/assets/styles.css` | Custom styles supplementing Tailwind/DaisyUI |
| `app/ui/assets/login.css` | Login page styles |
| `app/ui/assets/login.js` | Login form logic |
| `app/ui/html.js` | JS module exporting HTML pages (not used by Python backend) |

### Key Frontend Patterns

- **API calls**: All go through `apiRequest()` which attaches Bearer token and handles 401
- **Data rendering**: `renderUserTable()`, `renderRecords()`, `renderWorkerApis()` generate HTML via template literals
- **3 clockin type indicators**: Each record and user row shows H(ome)/S(port)/D(aily) status
  - Data source: `r.details.home?.success`, `r.details.sports?.success`, `r.details.daily?.success`
- **Active task polling**: `loadActiveTasks()` runs every 3 seconds via `setInterval`
- **Status bar**: Updates every 30 seconds with next scheduled run and Worker health count
- **Backend injection**: Python replaces `</head>` to inject `window.ADMIN_PATH` script

### Security Feature: ADMIN_PATH

The `ADMIN_PATH` environment variable provides security through obscurity:
- Default: `admin` (access at `/admin`)
- Recommended: Change to custom path like `my-secret-admin`
- Only requests to this path serve the admin UI
- Other paths return a generic error or nginx welcome page

To change: Update `ADMIN_PATH` in `.env` and restart the application.

## Common Tasks

When modifying clockin behavior:
1. Check `ClockinService.call_clockin_api()` for external API call
2. Check `PoetryService` for comment/image fetching logic
3. Update `ClockinResult` model if storing new data

### Comment and Image Content

**Comment Sources** (configured per user):
- `default`: System default text
- `custom`: User-provided custom text
- `api`: External API (今日诗词, 一言, 远梦API, KLapi)

**Image Providers** (configured per user):
- `bing`: Bing Daily Images (default)
- `bing_uhd`: Bing UHD高清壁纸
- `komll`: Komll API
- `loliapi`: LoliAPI ACG
- `cimuapi`: 次元API (supports category filtering)

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

**Deployment**:
```bash
cd clockin-worker
npx wrangler deploy
```

**Multiple Workers**: Deploy multiple workers with different names for load balancing. Add each worker's URL and token via sidebar → "Worker API" page.

## Troubleshooting

### Database Issues

**Database lock error (SQLite is locked)**:
```bash
rm database/*.db-journal
```

**Reset database (WARNING: wipes all data)**:
```bash
python scripts/init_db.py
```

### Port Issues

**Port 8000 already in use**:
```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Virtual Environment Issues

**PowerShell execution policy error (Windows)**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Dependencies not found after venv creation**:
```bash
# Ensure pip is upgraded
pip install --upgrade pip
pip install -r requirements.txt
```

### Clockin Issues

**All clockins failing with "没有可用的 Worker API"**:
- Check that at least one Worker API is enabled in sidebar → "Worker API" page
- Verify Worker API URLs are accessible: `curl https://your-worker.workers.dev`
- Check Worker API tokens match between Python Admin and Cloudflare Worker

**High failure rate on specific Worker API**:
- Check API availability in sidebar → "Worker API" page
- Consider disabling unavailable APIs temporarily
- Deploy additional Worker APIs for redundancy

**Rate limiting errors (429)**:
- Increase `CLOCKIN_RATE_LIMIT_DELAY` in `.env` (default 10s)
- Reduce `PARALLEL_TASKS` to lower concurrency
- Add more Worker APIs to distribute load

### Task Tracking Issues

**Stale tasks showing in 概览页**:
- Tasks auto-cleanup after completion
- If tasks persist, restart the application
- Check logs for errors in `ActiveTaskService`

### Frontend Issues

**JavaScript functions undefined (e.g. `navigateTo is not defined`)**:
- Check `app.js` for syntax errors: `node -c app/ui/assets/app.js`
- Template literal nesting issues can break the entire file
- Verify version parameter matches: `app.js?v=X.X` in `index.html`

**Worker API always shows "不可用"**:
- Frontend uses `api.available` field from backend (not rate calculation)
- Check `WorkerApiService` health logic for threshold settings

## Environment Variables Reference

Key variables in `.env` (see `.env.example` for complete list):

| Variable | Purpose | Default |
|----------|---------|---------|
| `CLOCKIN_API_URL` | Fallback Worker API URL (deprecated, use UI) | - |
| `CLOCKIN_API_TOKEN` | Fallback API token (deprecated, use UI) | - |
| `CLOCKIN_RETRY_COUNT` | Max retries per user | 3 |
| `CLOCKIN_RETRY_DELAY` | Delay between retries (seconds) | 3 |
| `CLOCKIN_RATE_LIMIT_DELAY` | Delay on 429 errors (seconds) | 10 |
| `CLOCKIN_TIMEOUT` | Request timeout (seconds) | 60 |
| `PARALLEL_TASKS` | Max concurrent clockin tasks | 4 |
| `BATCH_SIZE` | Users processed per batch | 3 |
| `SCHEDULE_CRON` | Cron schedule for auto-clockin | `0 10 0 * * *` |
| `RETENTION_DAYS` | Days to keep clockin records | 7 |
| `ADMIN_PATH` | Admin panel path (security feature) | `admin` |
