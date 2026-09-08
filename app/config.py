import os
from dotenv import load_dotenv

load_dotenv()


def _parse_db_url(url):
    """
    Railway gives DATABASE_URL as postgres:// — psycopg2 needs postgresql://.
    Also handles sslmode for Railway's managed Postgres.
    """
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
    SESSION_COOKIE_HTTPONLY = True       # JS cannot read session cookie
    SESSION_COOKIE_SAMESITE = 'Lax'     # CSRF protection
    SESSION_COOKIE_SECURE   = os.environ.get('FLASK_ENV') == 'production'  # HTTPS only in prod
    PERMANENT_SESSION_LIFETIME = 3600   # 1 hour

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL = _parse_db_url(
        os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/securevault')
    )

    # ── File uploads ──────────────────────────────────────────────────────────
    # On Railway, use /tmp for uploads (ephemeral) or set UPLOAD_FOLDER env var
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    )
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 104857600))  # 100 MB
    ALLOWED_EXTENSIONS = {
        'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx',
        'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', 'mp4', 'mp3',
        'csv', 'json', 'xml', 'svg', 'webp'
    }

    # ── Storage plans (bytes) ─────────────────────────────────────────────────
    STORAGE_PLANS = {
        'free':       1   * 1024 * 1024 * 1024,   # 1 GB
        'basic':      10  * 1024 * 1024 * 1024,   # 10 GB
        'pro':        50  * 1024 * 1024 * 1024,   # 50 GB
        'enterprise': 200 * 1024 * 1024 * 1024,   # 200 GB
    }

    # ── Brute-force lockout ───────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES    = 15

    # ── Environment ───────────────────────────────────────────────────────────
    FLASK_ENV   = os.environ.get('FLASK_ENV', 'development')
    DEBUG       = FLASK_ENV != 'production'
    TESTING     = False
