# Migration Collaboration Platform

A web-based, multi-user collaboration application for planning and tracking server/infrastructure migrations. Teams create Migration Plans, invite collaborators by email, organize work into Process Tabs, and track individual Tasks through a defined status workflow with notes, attachments, and assignment.

## Features

- **User Authentication** — Email/password registration, email verification, TOTP MFA, password reset, account lockout
- **Global Admin System** — First registered user becomes the protected first global admin; admins can add/delete/update users and reset passwords
- **Admin Area** — System settings, user management (add/edit/delete, access levels: Admin, User, Read-only), and SMTP configuration with a live test-email button
- **Global Read-Only Users** — Read-only users can view data but cannot create or modify anything
- **Migration Plans** — Create plans, invite collaborators by email with role-based access
- **Process Tabs** — Named, reorderable tabs within each plan (drag-and-drop via SortableJS)
- **Task Management** — 7-status state machine (New → Open → WIP → Waiting → Closed) with full-page editing
- **Task Steps** — Numbered, drag-and-drop reorderable sub-steps. Steps are editable with a rich-text editor that supports bold, italic, strikethrough, bullet/numbered/alphabetical lists, and links
- **Task Reordering** — Drag-and-drop task reordering within each tab
- **RBAC** — Owner, Admin, Contributor, Viewer roles enforced server-side
- **Notes** — Markdown-rendered notes per task
- **Attachments** — File upload with extension validation, size limits, secure storage; preview images and PDFs in a new window
- **Audit Log** — Complete history of all state changes, assignments, and actions
- **Dark/Light Mode** — Persistent per-user theme preference
- **App-Level Encryption** — Sensitive fields (email, MFA secrets) encrypted with Fernet
- **Email Validation** — Address format validation on registration, invitations, admin user creation, and password reset

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Frontend | Bootstrap 5 + HTMX + SortableJS |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (async via asyncpg) |
| Migrations | Alembic |
| Encryption | Fernet (AES) for sensitive columns |
| Auth | Argon2id hashing, TOTP MFA (pyotp) |
| Templates | Jinja2 (server-rendered) |
| Email | Generic SMTP relay (aiosmtplib) with TLS option and test button |
| Sanitization | bleach for rich-text step content |

## Local Installation & Setup

No manual configuration of `.env` files is required initially. A web-based setup wizard will guide you through connecting to PostgreSQL and creating the first global admin account.

```bash
# 1. Clone the repo
git clone <repository-url>
cd GOAMigrationAssistant

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the application
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

1. Open your browser to `http://localhost:8000`
2. Follow the setup wizard to configure your PostgreSQL connection
3. The wizard will automatically run database migrations and prompt you to create the First Global Admin account
4. Once completed, the wizard disables itself permanently (remove `.setup_complete` to re-run it)

### Start development server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker

### Using Docker Compose (recommended)

The included `docker-compose.yml` starts the FastAPI application and a PostgreSQL database. You must create a `.env` file first.

```bash
# 1. Create a .env file (or copy .env.example)
# At minimum set:
#   POSTGRES_PASSWORD=your-secure-db-password
#   DATABASE_URL=postgresql+asyncpg://appuser:your-secure-db-password@db:5432/migration_platform
#   SECRET_KEY=your-random-secret-key
#   ENCRYPTION_KEY=your-32-byte-base64-fernet-key
#
# You may also pre-configure SMTP:
#   SMTP_HOST=smtp.example.com
#   SMTP_PORT=587
#   SMTP_USER=user@example.com
#   SMTP_PASSWORD=your-password
#   SMTP_USE_TLS=true
#   SMTP_FROM_EMAIL=noreply@example.com
#   SMTP_FROM_NAME=Migration Platform

docker compose up --build
```

Then open `http://localhost:8000` and complete the setup wizard.

To run with the optional local MailHog and ClamAV services for development/security testing:

```bash
docker compose --profile dev --profile security up --build
```

### Using Docker directly

If you already have a PostgreSQL server available, you can build and run the image manually.

```bash
# Build the image
docker build -t migration-assistant .

# Run it
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/migration_platform" \
  -e SECRET_KEY="your-random-secret-key" \
  -e ENCRYPTION_KEY="your-32-byte-base64-fernet-key" \
  -e POSTGRES_PASSWORD="your-db-password" \
  -v migration_uploads:/app/uploads \
  --name migration-assistant \
  migration-assistant
```

The first time the app starts it will run migrations automatically through the setup wizard. You can also run migrations manually before starting if the database is already configured:

```bash
docker run --rm -e DATABASE_URL="postgresql+asyncpg://..." migration-assistant alembic upgrade head
```

### Useful Docker commands

```bash
# View logs
docker compose logs -f app

# Stop
docker compose down

# Stop and remove data volumes (WARNING: deletes database data)
docker compose down -v
```

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Project Structure

```
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # Pydantic settings
│   ├── database.py          # Async PostgreSQL engine
│   ├── encryption.py        # Fernet field encryption
│   ├── templating.py        # Jinja2 templates
│   ├── models/              # SQLAlchemy models
│   ├── routers/             # FastAPI route handlers
│   ├── services/            # Business logic
│   ├── middleware/          # Auth, CSRF, rate limiting
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS, JS, images
├── tests/                   # Pytest test suite
├── alembic/                 # Database migrations
├── docker-compose.yml       # Docker services
├── Dockerfile               # App container
└── requirements.txt         # Python dependencies
```

## Task Status State Machine

```
New → Open, Work In Progress, Closed – Not Needed
Open → Work In Progress, Waiting on Client/Vendor, Closed – Complete/Not Needed
Work In Progress → Waiting on Client/Vendor, Closed – Complete/Not Needed
Waiting on Client → Open, Work In Progress, Closed – Not Needed
Waiting on Vendor → Open, Work In Progress, Closed – Not Needed
Closed – Complete → Open (Admin/Owner only)
Closed – Not Needed → Open (Admin/Owner only)
```

## Roles & Permissions

| Role | Permissions |
|---|---|
| **Owner** | Full control: invite/remove users, delete plan, edit anything |
| **Admin** | Create/edit tabs & tasks, assign tasks, invite users, reorder tasks |
| **Contributor** | Create/edit tasks assigned to them, add notes/attachments, reorder tasks and steps |
| **Viewer** | Read-only access |

## Security

- Argon2id password hashing
- CSRF protection (double-submit cookie pattern)
- Rate limiting on auth endpoints
- Account lockout after 5 failed logins
- App-level field encryption (Fernet) for PII
- Extension allowlist for file uploads
- HttpOnly, SameSite=Strict session cookies
- Server-side RBAC enforcement on all endpoints
- Rich-text step content is sanitized with bleach before storage

## Pinokio Launcher

This project includes a Pinokio 1-click launcher for easy installation and startup. See `E:\pinokio\api\GOAMigrationAssistant` for the launcher scripts.

## License

MIT
