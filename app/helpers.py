import os
import uuid
import math
from functools import wraps
from flask import session, redirect, url_for, flash, abort


# ── Auth decorators ─────────────────────────────────────────────────────────

def login_required(f):
    """Redirect to login if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Abort 403 if user is not an admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── File utilities ───────────────────────────────────────────────────────────

def secure_filename_uuid(filename):
    """
    Return a UUID-based filename while preserving extension.
    Prevents path traversal and name collisions.
    """
    ext = ''
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[1].lower()
    return str(uuid.uuid4()) + ext


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def human_readable_size(size_bytes):
    """Convert bytes to human-readable string."""
    if size_bytes == 0:
        return '0 B'
    size_name = ('B', 'KB', 'MB', 'GB', 'TB')
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f'{s} {size_name[i]}'


def storage_percent(used, total):
    """Return integer percentage of storage used (capped at 100)."""
    if total == 0:
        return 100
    return min(int((used / total) * 100), 100)


def get_file_icon(filename):
    """Return a Bootstrap Icons class based on file extension."""
    if not filename or '.' not in filename:
        return 'bi-file-earmark'
    ext = filename.rsplit('.', 1)[1].lower()
    icons = {
        'pdf': 'bi-file-earmark-pdf text-danger',
        'doc': 'bi-file-earmark-word text-primary',
        'docx': 'bi-file-earmark-word text-primary',
        'xls': 'bi-file-earmark-excel text-success',
        'xlsx': 'bi-file-earmark-excel text-success',
        'ppt': 'bi-file-earmark-ppt text-warning',
        'pptx': 'bi-file-earmark-ppt text-warning',
        'jpg': 'bi-file-earmark-image text-info',
        'jpeg': 'bi-file-earmark-image text-info',
        'png': 'bi-file-earmark-image text-info',
        'gif': 'bi-file-earmark-image text-info',
        'svg': 'bi-file-earmark-image text-info',
        'webp': 'bi-file-earmark-image text-info',
        'mp4': 'bi-file-earmark-play text-purple',
        'mp3': 'bi-file-earmark-music text-purple',
        'zip': 'bi-file-earmark-zip text-secondary',
        'rar': 'bi-file-earmark-zip text-secondary',
        'txt': 'bi-file-earmark-text',
        'csv': 'bi-file-earmark-spreadsheet text-success',
        'json': 'bi-file-earmark-code text-warning',
        'xml': 'bi-file-earmark-code text-warning',
    }
    return icons.get(ext, 'bi-file-earmark')
