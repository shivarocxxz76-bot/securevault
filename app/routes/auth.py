from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app)
from datetime import datetime, timezone, timedelta
import bcrypt

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, storage_percent

auth_bp = Blueprint('auth', __name__)


def _log_activity(user_id, action, details=None, ip=None):
    execute_db(
        "INSERT INTO activity_logs (user_id, action, details, ip_address) VALUES (%s,%s,%s,%s)",
        (user_id, action, details, ip)
    )


# ── Register ─────────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('files.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        # Basic validation
        if not all([username, email, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'danger')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/register.html')

        # Check uniqueness — parameterised to prevent SQL injection
        existing = query_db(
            "SELECT id FROM users WHERE email=%s OR username=%s",
            (email, username), one=True
        )
        if existing:
            flash('Email or username already in use.', 'danger')
            return render_template('auth/register.html')

        # Hash password with bcrypt (cost factor 12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))

        user = execute_db(
            """INSERT INTO users (username, email, password_hash)
               VALUES (%s, %s, %s) RETURNING id, username, role_id""",
            (username, email, hashed.decode('utf-8')),
            returning=True
        )

        _log_activity(user['id'], 'register', f'New user: {email}',
                      request.remote_addr)
        flash('Account created successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# ── Login ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('files.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        max_attempts = current_app.config['MAX_LOGIN_ATTEMPTS']

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('auth/login.html')

        user = query_db(
            """SELECT u.id, u.username, u.email, u.password_hash, u.is_active,
                      u.failed_login_attempts, u.locked_until,
                      r.name AS role
               FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.email = %s""",
            (email,), one=True
        )

        # User not found — generic message (don't reveal existence)
        if not user:
            flash('Invalid email or password.', 'danger')
            return render_template('auth/login.html')

        # Account deactivated
        if not user['is_active']:
            flash('Your account has been deactivated. Contact support.', 'danger')
            return render_template('auth/login.html')

        # Brute-force lockout check
        if user['locked_until'] and user['locked_until'] > datetime.now(timezone.utc):
            remaining = int((user['locked_until'] - datetime.now(timezone.utc)).total_seconds() // 60) + 1
            flash(f'Account locked. Try again in {remaining} minute(s).', 'danger')
            return render_template('auth/login.html')

        # Verify password
        pw_match = bcrypt.checkpw(password.encode('utf-8'),
                                  user['password_hash'].encode('utf-8'))

        if not pw_match:
            new_attempts = user['failed_login_attempts'] + 1
            locked_until = None
            if new_attempts >= max_attempts:
                lockout_mins = current_app.config['LOCKOUT_MINUTES']
                locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_mins)
                flash(f'Too many failed attempts. Account locked for {lockout_mins} minutes.', 'danger')
            else:
                flash(f'Invalid email or password. {max_attempts - new_attempts} attempt(s) remaining.', 'danger')

            execute_db(
                "UPDATE users SET failed_login_attempts=%s, locked_until=%s WHERE id=%s",
                (new_attempts, locked_until, user['id'])
            )
            return render_template('auth/login.html')

        # Success — reset counters, set session
        execute_db(
            "UPDATE users SET failed_login_attempts=0, locked_until=NULL, last_login=NOW() WHERE id=%s",
            (user['id'],)
        )

        # Record session in DB
        expire = datetime.now(timezone.utc) + timedelta(seconds=current_app.config['PERMANENT_SESSION_LIFETIME'])
        execute_db(
            """INSERT INTO user_sessions (user_id, ip_address, user_agent, expires_at)
               VALUES (%s, %s, %s, %s)""",
            (user['id'], request.remote_addr, request.user_agent.string, expire)
        )

        session.permanent = True
        session['user_id']   = user['id']
        session['username']  = user['username']
        session['role']      = user['role']
        session['email']     = user['email']

        _log_activity(user['id'], 'login', None, request.remote_addr)
        flash(f'Welcome back, {user["username"]}!', 'success')

        if user['role'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('files.dashboard'))

    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    user_id = session.get('user_id')
    _log_activity(user_id, 'logout', None, request.remote_addr)
    # Revoke all active sessions for this user
    execute_db(
        "UPDATE user_sessions SET is_revoked=TRUE WHERE user_id=%s AND is_revoked=FALSE",
        (user_id,)
    )
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ── Profile ───────────────────────────────────────────────────────────────────
@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    def _ctx():
        unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
        return dict(
            user=user,
            unread=unread['cnt'] if unread else 0,
            used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
            used_human=human_readable_size(user['storage_used_bytes']),
            limit_human=human_readable_size(user['storage_limit_bytes']),
        )

    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not bcrypt.checkpw(current_pw.encode('utf-8'), user['password_hash'].encode('utf-8')):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/profile.html', **_ctx())
        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return render_template('auth/profile.html', **_ctx())
        if new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
            return render_template('auth/profile.html', **_ctx())

        hashed = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt(rounds=12))
        execute_db("UPDATE users SET password_hash=%s WHERE id=%s",
                   (hashed.decode('utf-8'), uid))
        _log_activity(uid, 'password_change', None, request.remote_addr)
        flash('Password updated successfully.', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', **_ctx())
