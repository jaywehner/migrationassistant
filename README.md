# Migration Collaboration Platform

A web-based, multi-user collaboration application for planning and tracking server/infrastructure migrations. Teams create Migration Plans, invite collaborators by email, organize work into Process Tabs, and track individual Tasks through a defined status workflow with notes, attachments, and assignment.

## Features

- **User Authentication** — Email/password registration, email verification, TOTP MFA, password reset, account lockout
- **Global Admin System** — First registered user becomes the protected first global admin; admins can add/delete/update users and reset passwords
- **Admin Area** — System settings, user management (add/edit/delete, access levels: Admin, User, Read-only)
- **Global Read-Only Users** — Read-only users can view data but cannot create or modify anything
- **Migration Plans** — Create plans, invite collaborators by email with role-based access
- **Process Tabs** — Named, reorderable tabs within each plan (drag-and-drop via SortableJS)
- **Task Management** — 7-status state machine (New → Open → WIP → Waiting → Closed)
- **RBAC** — Owner, Admin, Contributor, Viewer roles enforced server-side
- **Notes** — Immutable, Markdown-rendered notes per task
- **Attachments** — File upload with extension validation, size limits, secure storage
- **Audit Log** — Complete history of all state changes, assignments, and actions
- **Dark/Light Mode** — Persistent per-user theme preference
- **App-Level Encryption** — Sensitive fields (email, MFA secrets) encrypted with Fernet

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Frontend | Bootstrap 5 + HTMX + SortableJS |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (async via asyncpg) |
| Encryption | Fernet (AES) for sensitive columns |
| Auth | Argon2id hashing, TOTP MFA (pyotp) |
| Templates | Jinja2 (server-rendered) |
| Email | Generic SMTP relay |

## Installation & Setup

No manual configuration of `.env` files is required. A web-based setup wizard will guide you through connecting to PostgreSQL and creating the first global admin account.

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
3. The wizard will automatically run database migrations and prompt you to create the First Global Admin account.
4. Once completed, the wizard disables itself permanently (or until `.setup_complete` is removed).

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
| **Admin** | Create/edit tabs & tasks, assign tasks, invite users |
| **Contributor** | Create/edit tasks assigned to them, add notes/attachments |
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

## Pinokio Launcher

This project includes a Pinokio 1-click launcher for easy installation and startup. See `E:\pinokio\api\GOAMigrationAssistant` for the launcher scripts.

## License

MIT
