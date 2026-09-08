# SecureVault — Web-Based Secure File Storage and Access Management System

BSc IT Final Year Project

## Tech Stack
- **Frontend**: HTML, CSS, Bootstrap 5, JavaScript
- **Backend**: Python 3.11+, Flask 3.0
- **Database**: PostgreSQL 14+
- **Web Server**: Nginx + Gunicorn
- **Security**: bcrypt password hashing, server-side sessions, parameterised queries

---

## Setup Instructions

### 1. Create the PostgreSQL database
```sql
CREATE DATABASE securevault;
```

### 2. Run the schema
```bash
psql -U postgres -d securevault -f schema.sql
```

### 3. Configure environment
```bash
copy .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL
```

### 4. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 5. Run development server
```bash
python run.py
```
Visit: **http://localhost:5000**

---

## Production (Nginx + Gunicorn)

```bash
# Start Gunicorn
gunicorn -w 4 -b 127.0.0.1:8000 "app:create_app()"

# Copy Nginx config
copy nginx\securevault.conf C:\nginx\conf\securevault.conf
# Add: include securevault.conf; in nginx.conf http block
nginx -s reload
```

---

## Module Summary

| # | Module | Key Features |
|---|--------|--------------|
| 1 | User Authentication | Register, login, bcrypt, brute-force lockout, sessions, roles |
| 2 | File Management | Upload (drag-drop), download, delete, rename, storage tracking |
| 3 | Folder Management | Create, rename, delete (recursive), nested subfolders |
| 4 | File & Folder Sharing | Share by email, set permissions, revoke access |
| 5 | Storage & Demo Payment | Usage meter, 4 plans, fake checkout, payment history |
| 6 | Recycle Bin | Soft delete, restore, permanent delete, empty bin |
| 7 | Notifications & Support | Bell badge, read/delete, support tickets, admin replies |
| 8 | Admin Panel | Dashboard stats, user management, file monitor, logs, search |

---

## Security Features (grading relevant)

- Passwords: **bcrypt** (cost 12) — never stored in plaintext
- SQL: All queries use **parameterised placeholders** (%s) — no string interpolation
- Sessions: **Server-side Flask sessions** with `HttpOnly`, `SameSite=Lax` flags
- Access control: **`login_required`** and **`admin_required`** decorators on every route
- File access: Ownership check on every download — shared-with check as fallback
- Brute force: Failed login counter + account lockout (5 attempts, 15-min lockout)
- File naming: UUID-based stored filenames prevent path traversal
- Upload validation: Extension whitelist + MIME type stored

---

## Default Admin Account

Create via registration, then in psql:
```sql
UPDATE users SET role_id = 1 WHERE email = 'your@email.com';
```
