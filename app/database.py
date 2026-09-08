import psycopg2
import psycopg2.extras
from flask import g, current_app


def get_db():
    """Return the database connection for the current request context."""
    if 'db' not in g:
        g.db = psycopg2.connect(
            current_app.config['DATABASE_URL'],
            cursor_factory=psycopg2.extras.RealDictCursor  # rows as dicts
        )
        g.db.autocommit = False
    return g.db


def close_db(e=None):
    """Close DB connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(sql, args=(), one=False, commit=False):
    """
    Helper: run a parameterised query and return results.
    Uses %s placeholders (psycopg2 style) — safe against SQL injection.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, args)
    if commit:
        db.commit()
    if cur.description is None:
        cur.close()
        return None
    rv = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return rv


def execute_db(sql, args=(), returning=False):
    """
    Helper: run INSERT/UPDATE/DELETE with optional RETURNING clause.
    Returns the first row if returning=True, else None.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, args)
    db.commit()
    if returning and cur.description:
        row = cur.fetchone()
        cur.close()
        return row
    cur.close()
    return None


def init_app(app):
    app.teardown_appcontext(close_db)
