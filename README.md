# finance-api

A role-based finance dashboard backend built with Flask. Supports financial record management, dashboard analytics, and strict access control across three user roles.

---

## Stack

| Layer        | Choice                          |
|--------------|---------------------------------|
| Framework    | Flask 3                         |
| Auth         | JWT via Flask-JWT-Extended       |
| ORM          | Flask-SQLAlchemy                |
| Database     | SQLite (default) / PostgreSQL   |
| Validation   | Manual, in `app/utils/validators.py` |

> To swap to PostgreSQL, set `DATABASE_URL` in your `.env`. The ORM layer handles the rest.

---

## Project Structure

```
finance-api/
├── app/
│   ├── __init__.py          # App factory, DB init, admin seed
│   ├── models/
│   │   ├── user.py          # User model + Role enum
│   │   └── transaction.py   # Transaction model + Type enum
│   ├── routes/
│   │   ├── auth.py          # /api/auth  — register, login, me
│   │   ├── users.py         # /api/users — admin CRUD + role management
│   │   ├── transactions.py  # /api/transactions — CRUD + filtering
│   │   └── dashboard.py     # /api/dashboard — analytics endpoints
│   ├── middleware/
│   │   └── auth.py          # require_auth, require_role, require_min_role
│   └── utils/
│       ├── validators.py    # Input validation functions
│       └── helpers.py       # success(), error(), paginate_query()
├── config.py                # Config class (env-aware)
├── run.py                   # Entry point
├── requirements.txt
└── .env.example
```

---

## Setup

```bash
git clone <repo>
cd finance-api

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env           # set your secrets

python run.py
```

The database is created automatically on first run. A default admin account is seeded:

| Field    | Value               |
|----------|---------------------|
| Email    | admin@finance.dev   |
| Password | admin123            |

> Change this before any real deployment.

---

## Roles

| Role     | Capabilities                                                                 |
|----------|------------------------------------------------------------------------------|
| `viewer`   | Read own transactions, view own dashboard summary and recent activity      |
| `analyst`  | Read all transactions, full dashboard access, create/update/delete own records |
| `admin`    | Everything — plus user management and updating any transaction             |

---

## API Reference

All protected endpoints require:
```
Authorization: Bearer <token>
```

### Auth — `/api/auth`

| Method | Path        | Auth | Description              |
|--------|-------------|------|--------------------------|
| POST   | `/register` | —    | Register (gets Viewer role) |
| POST   | `/login`    | —    | Login, returns JWT token |
| GET    | `/me`       | Any  | Current user info        |

**Register / Login body:**
```json
{ "name": "Ishaan", "email": "ishaan@gmail.com", "password": "hamilton44" }
```

**Response shape (all endpoints):**
```json
{
  "success": true,
  "message": "...",
  "data": { ... }
}
```

---

### Users — `/api/users` *(Admin only)*

| Method | Path              | Description                     |
|--------|-------------------|---------------------------------|
| GET    | `/`               | List users (filter: role, is_active, page) |
| POST   | `/`               | Create user with any role       |
| GET    | `/:id`            | Get user by ID                  |
| PATCH  | `/:id`            | Update name, email, active status |
| PATCH  | `/:id/role`       | Change user's role              |
| DELETE | `/:id`            | Soft-deactivate user            |

**Query params for GET /:**
- `role` — filter by `viewer`, `analyst`, `admin`
- `is_active` — `true` or `false`
- `page`, `per_page`

---

### Transactions — `/api/transactions`

| Method | Path   | Min Role | Description                      |
|--------|--------|----------|----------------------------------|
| GET    | `/`    | Viewer   | List transactions (with filters) |
| GET    | `/:id` | Viewer   | Get single transaction           |
| POST   | `/`    | Analyst  | Create transaction               |
| PATCH  | `/:id` | Analyst  | Update transaction               |
| DELETE | `/:id` | Analyst  | Soft-delete transaction          |

> Viewers see only their own records. Analysts and Admins see all.
> Analysts can only modify their own records. Admins can modify any.

**Create / Update body:**
```json
{
  "amount": 1500.00,
  "type": "income",
  "category": "Freelance",
  "date": "2026-03-15",
  "notes": "Optional note"
}
```

**GET / query params:**
- `type` — `income` or `expense`
- `category` — partial match
- `date_from`, `date_to` — `YYYY-MM-DD`
- `created_by` — filter by user ID (Admin only)
- `page`, `per_page`

---

### Dashboard — `/api/dashboard`

| Method | Path              | Min Role | Description                             |
|--------|-------------------|----------|-----------------------------------------|
| GET    | `/summary`        | Viewer   | Total income, expenses, net balance     |
| GET    | `/recent`         | Viewer   | Latest N transactions (`?limit=10`)     |
| GET    | `/by-category`    | Analyst  | Totals grouped by category and type     |
| GET    | `/monthly-trends` | Analyst  | Income vs expenses by month (`?year=2026`) |
| GET    | `/weekly-trends`  | Analyst  | Income vs expenses by week (`?weeks=4`) |

**Summary response:**
```json
{
  "total_income": 7000.0,
  "total_expenses": 1950.0,
  "net_balance": 5050.0,
  "transaction_count": 5
}
```

**Monthly trends response:**
```json
{
  "year": 2026,
  "months": [
    { "month": "2026-01", "income": 5000.0, "expenses": 1200.0, "net": 3800.0 },
    ...
  ]
}
```

---

## Error Responses

```json
{
  "success": false,
  "error": "Validation failed.",
  "details": ["amount must be a positive number.", "date must be in YYYY-MM-DD format."]
}
```

| Code | Meaning                      |
|------|------------------------------|
| 400  | Bad request                  |
| 401  | Invalid / missing credentials |
| 403  | Insufficient permissions     |
| 404  | Resource not found           |
| 409  | Conflict (e.g. duplicate email) |
| 422  | Validation error             |

---

## Assumptions

- **Soft deletes only.** Transactions and users are never hard-deleted. Deactivated users cannot log in. Deleted transactions are excluded from all queries.
- **Self-protection.** Admins cannot deactivate themselves or change their own role — prevents accidental lockout.
- **Viewer data isolation.** Viewers are scoped to their own data across all read endpoints including dashboard.
- **Analyst scope.** Analysts can write, but only manage records they created. Admins have full write access across all records.
- **Registration is open.** Anyone can register and receives Viewer role. Role elevation requires an Admin.
- **Pagination defaults.** All list endpoints default to 20 items per page, capped at 100.

---

## Design Decisions

**Middleware decorators over inline checks.**
`require_role()` and `require_min_role()` are composable decorators. Adding a new protected route is one line. This keeps route files clean and the access rules readable at a glance.

**Centralized response helpers.**
`success()` and `error()` enforce a consistent envelope (`{ success, data, message, error, details }`) across every endpoint — no inconsistency between routes.

**Separated validator module.**
Validation logic lives in `utils/validators.py` and returns lists of error strings. Routes call validators, collect errors, and return them in a single response. No exceptions thrown for validation.

**Single app factory.**
`create_app()` wires everything — blueprints, extensions, and DB seeding — in one place. Easy to test against a fresh instance in isolation.
