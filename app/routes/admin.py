from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, abort, jsonify)

from ..database import query_db, execute_db
from ..helpers  import admin_required, human_readable_size, storage_percent

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _log(user_id, action, target_type=None, target_id=None, details=None):
    execute_db(
        "INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address)"
        " VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, action, target_type, target_id, details, request.remote_addr)
    )


# ── Admin Dashboard ───────────────────────────────────────────────────────────
@admin_bp.route('/')
@admin_required
def dashboard():
    stats = {
        'total_users':   query_db("SELECT COUNT(*) AS c FROM users WHERE role_id != 1", one=True)['c'],
        'active_users':  query_db("SELECT COUNT(*) AS c FROM users WHERE is_active=TRUE AND role_id != 1", one=True)['c'],
        'total_files':   query_db("SELECT COUNT(*) AS c FROM files WHERE is_deleted=FALSE", one=True)['c'],
        'total_folders': query_db("SELECT COUNT(*) AS c FROM folders WHERE is_deleted=FALSE", one=True)['c'],
        'open_tickets':  query_db("SELECT COUNT(*) AS c FROM support_tickets WHERE status='open'", one=True)['c'],
        'total_storage': query_db("SELECT COALESCE(SUM(storage_used_bytes),0) AS c FROM users WHERE role_id != 1", one=True)['c'],
        'total_revenue': query_db("SELECT COALESCE(SUM(amount_usd),0.00) AS c FROM payments WHERE status='completed'", one=True)['c'],
    }

    # Monthly upload data for chart (last 12 months)
    monthly_data = []
    monthly_labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    for month in range(1, 13):
        row = query_db(
            "SELECT COUNT(*) AS c FROM files WHERE EXTRACT(MONTH FROM created_at)=%s AND EXTRACT(YEAR FROM created_at)=EXTRACT(YEAR FROM NOW())",
            (month,), one=True
        )
        monthly_data.append(row['c'] if row else 0)

    # Uploads today
    today_uploads = query_db(
        "SELECT COUNT(*) AS c FROM files WHERE is_deleted=FALSE AND DATE(created_at) = CURRENT_DATE",
        one=True
    )

    recent_logs = query_db(
        """SELECT al.*, u.username FROM activity_logs al
           LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.created_at DESC LIMIT 20"""
    ) or []

    recent_users = query_db(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT 5"
    ) or []

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)

    import json
    return render_template('admin/dashboard.html',
                           stats=stats,
                           recent_logs=recent_logs,
                           recent_users=recent_users,
                           admin_user=admin_user,
                           storage_human=human_readable_size(int(stats['total_storage'])),
                           monthly_data=json.dumps(monthly_data),
                           monthly_labels=json.dumps(monthly_labels),
                           today_uploads=today_uploads['c'] if today_uploads else 0)


# ── User management ───────────────────────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
def users():
    search = request.args.get('q', '').strip()
    if search:
        raw = query_db(
            """SELECT u.*, r.name AS role FROM users u JOIN roles r ON r.id=u.role_id
               WHERE (u.username ILIKE %s OR u.email ILIKE %s) AND u.role_id != 1
               ORDER BY u.created_at DESC""",
            (f'%{search}%', f'%{search}%')
        ) or []
    else:
        raw = query_db(
            "SELECT u.*, r.name AS role FROM users u JOIN roles r ON r.id=u.role_id WHERE u.role_id != 1 ORDER BY u.created_at DESC"
        ) or []

    all_users = [dict(u) for u in raw]
    for u in all_users:
        u['used_human']  = human_readable_size(u['storage_used_bytes'])
        u['limit_human'] = human_readable_size(u['storage_limit_bytes'])
        u['used_pct']    = storage_percent(u['storage_used_bytes'], u['storage_limit_bytes'])

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/users.html',
                           all_users=all_users, admin_user=admin_user, search=search)


@admin_bp.route('/users/toggle/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.users'))
    user = query_db("SELECT id, is_active, username FROM users WHERE id=%s", (user_id,), one=True)
    if not user:
        abort(404)
    new_state = not user['is_active']
    execute_db("UPDATE users SET is_active=%s WHERE id=%s", (new_state, user_id))
    action = 'activated' if new_state else 'deactivated'
    _log(session['user_id'], f'admin_user_{action}', 'user', user_id, user['username'])
    flash(f'User {user["username"]} has been {action}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/change-role/<int:user_id>', methods=['POST'])
@admin_required
def change_role(user_id):
    role_name = request.form.get('role', 'user')
    if role_name not in ('admin', 'user'):
        flash('Invalid role.', 'danger')
        return redirect(url_for('admin.users'))
    role = query_db("SELECT id FROM roles WHERE name=%s", (role_name,), one=True)
    if not role:
        flash('Role not found.', 'danger')
        return redirect(url_for('admin.users'))
    execute_db("UPDATE users SET role_id=%s WHERE id=%s", (role['id'], user_id))
    _log(session['user_id'], 'admin_change_role', 'user', user_id, role_name)
    flash('User role updated.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('admin.users'))
    user = query_db("SELECT username FROM users WHERE id=%s", (user_id,), one=True)
    if not user:
        abort(404)
    execute_db("DELETE FROM users WHERE id=%s", (user_id,))
    _log(session['user_id'], 'admin_delete_user', 'user', user_id, user['username'])
    flash(f'User {user["username"]} deleted.', 'success')
    return redirect(url_for('admin.users'))


# ── File monitoring ───────────────────────────────────────────────────────────
@admin_bp.route('/files')
@admin_required
def files():
    search = request.args.get('q', '').strip()
    if search:
        raw = query_db(
            """SELECT f.*, u.username AS owner FROM files f JOIN users u ON u.id=f.owner_id
               WHERE f.original_name ILIKE %s AND f.is_deleted=FALSE
               ORDER BY f.created_at DESC""",
            (f'%{search}%',)
        ) or []
    else:
        raw = query_db(
            """SELECT f.*, u.username AS owner FROM files f JOIN users u ON u.id=f.owner_id
               WHERE f.is_deleted=FALSE ORDER BY f.created_at DESC LIMIT 200"""
        ) or []

    all_files = [dict(f) for f in raw]
    for f in all_files:
        f['size_human'] = human_readable_size(f['size_bytes'])

    # Per-user stats for the table at bottom
    user_stats_raw = query_db(
        """SELECT u.id, u.username, u.email, u.is_active, u.storage_used_bytes, u.storage_limit_bytes, u.current_plan,
                  COUNT(f.id) AS file_count,
                  SUM(CASE WHEN DATE(f.created_at)=CURRENT_DATE THEN 1 ELSE 0 END) AS today_uploads
           FROM users u
           LEFT JOIN files f ON f.owner_id=u.id AND f.is_deleted=FALSE
           WHERE u.role_id != 1
           GROUP BY u.id, u.username, u.email, u.is_active, u.storage_used_bytes, u.storage_limit_bytes, u.current_plan
           ORDER BY u.storage_used_bytes DESC"""
    ) or []
    user_stats = [dict(u) for u in user_stats_raw]
    for u in user_stats:
        u['used_human']  = human_readable_size(u['storage_used_bytes'])
        u['limit_human'] = human_readable_size(u['storage_limit_bytes'])
        u['used_pct']    = storage_percent(u['storage_used_bytes'], u['storage_limit_bytes'])

    # Summary stats
    total_storage = query_db("SELECT COALESCE(SUM(storage_used_bytes),0) AS c FROM users", one=True)
    total_limit   = query_db("SELECT COALESCE(SUM(storage_limit_bytes),0) AS c FROM users WHERE role_id!=1", one=True)
    today_count   = query_db("SELECT COUNT(*) AS c FROM files WHERE is_deleted=FALSE AND DATE(created_at)=CURRENT_DATE", one=True)
    uploaders     = query_db("SELECT COUNT(DISTINCT owner_id) AS c FROM files WHERE is_deleted=FALSE", one=True)

    storage_used_bytes = int(total_storage['c']) if total_storage else 0
    storage_limit_bytes= int(total_limit['c'])   if total_limit else 1
    storage_pct = min(int(storage_used_bytes / storage_limit_bytes * 100), 100) if storage_limit_bytes else 0

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/files.html',
                           all_files=all_files,
                           user_stats=user_stats,
                           admin_user=admin_user,
                           search=search,
                           storage_used_bytes=storage_used_bytes,
                           storage_limit_bytes=storage_limit_bytes,
                           storage_used_human=human_readable_size(storage_used_bytes),
                           storage_limit_human=human_readable_size(storage_limit_bytes),
                           storage_pct=storage_pct,
                           today_uploads=today_count['c'] if today_count else 0,
                           total_uploaders=uploaders['c'] if uploaders else 0)


# ── Plans management ──────────────────────────────────────────────────────────
@admin_bp.route('/plans')
@admin_required
def plans():
    raw_plans = query_db("SELECT * FROM plans ORDER BY storage_bytes") or []
    payments  = query_db(
        """SELECT p.*, u.username, pl.name AS plan_name
           FROM payments p
           JOIN users u  ON u.id  = p.user_id
           JOIN plans pl ON pl.id = p.plan_id
           ORDER BY p.created_at DESC LIMIT 50"""
    ) or []

    all_plans = [dict(p) for p in raw_plans]
    for pl in all_plans:
        pl['storage_human'] = human_readable_size(pl['storage_bytes'])

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/plans.html',
                           all_plans=all_plans, payments=payments, admin_user=admin_user)


@admin_bp.route('/plans/toggle/<int:plan_id>', methods=['POST'])
@admin_required
def toggle_plan(plan_id):
    plan = query_db("SELECT id, is_active, name FROM plans WHERE id=%s", (plan_id,), one=True)
    if not plan:
        abort(404)
    execute_db("UPDATE plans SET is_active=%s WHERE id=%s", (not plan['is_active'], plan_id))
    state = 'activated' if not plan['is_active'] else 'deactivated'
    flash(f'Plan "{plan["name"]}" {state}.', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/plans/edit/<int:plan_id>', methods=['GET', 'POST'])
@admin_required
def edit_plan(plan_id):
    """Edit plan name, price, storage and description."""
    plan = query_db("SELECT * FROM plans WHERE id=%s", (plan_id,), one=True)
    if not plan:
        abort(404)

    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        price_str   = request.form.get('price_usd', '0').strip()
        storage_gb  = request.form.get('storage_gb', '1').strip()
        description = request.form.get('description', '').strip()

        # Validate
        if not name:
            flash('Plan name is required.', 'danger')
            return redirect(url_for('admin.edit_plan', plan_id=plan_id))
        try:
            price_usd    = float(price_str)
            storage_bytes = int(float(storage_gb) * 1024 * 1024 * 1024)
        except ValueError:
            flash('Invalid price or storage value.', 'danger')
            return redirect(url_for('admin.edit_plan', plan_id=plan_id))

        execute_db(
            """UPDATE plans SET name=%s, price_usd=%s, storage_bytes=%s, description=%s
               WHERE id=%s""",
            (name, price_usd, storage_bytes, description, plan_id)
        )
        _log(session['user_id'], 'admin_edit_plan', 'plan', plan_id, name)
        flash(f'Plan "{name}" updated successfully.', 'success')
        return redirect(url_for('admin.plans'))

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    # Convert bytes back to GB for display
    storage_gb = round(plan['storage_bytes'] / (1024 * 1024 * 1024), 2)
    return render_template('admin/edit_plan.html',
                           plan=plan, storage_gb=storage_gb, admin_user=admin_user)


@admin_bp.route('/plans/add', methods=['GET', 'POST'])
@admin_required
def add_plan():
    """Create a brand-new plan."""
    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        price_str   = request.form.get('price_usd', '0').strip()
        storage_gb  = request.form.get('storage_gb', '1').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Plan name is required.', 'danger')
            return redirect(url_for('admin.add_plan'))
        try:
            price_usd     = float(price_str)
            storage_bytes = int(float(storage_gb) * 1024 * 1024 * 1024)
        except ValueError:
            flash('Invalid price or storage value.', 'danger')
            return redirect(url_for('admin.add_plan'))

        # Check duplicate name
        existing = query_db("SELECT id FROM plans WHERE name=%s", (name,), one=True)
        if existing:
            flash(f'A plan named "{name}" already exists.', 'danger')
            return redirect(url_for('admin.add_plan'))

        execute_db(
            "INSERT INTO plans (name, storage_bytes, price_usd, description) VALUES (%s,%s,%s,%s)",
            (name, storage_bytes, price_usd, description)
        )
        _log(session['user_id'], 'admin_add_plan', 'plan', None, name)
        flash(f'Plan "{name}" created.', 'success')
        return redirect(url_for('admin.plans'))

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/edit_plan.html',
                           plan=None, storage_gb=1, admin_user=admin_user)


# ── Activity logs ─────────────────────────────────────────────────────────────
@admin_bp.route('/logs')
@admin_required
def logs():
    page          = max(int(request.args.get('page', 1)), 1)
    per_page      = 50
    offset        = (page - 1) * per_page
    action_filter = request.args.get('action', '').strip()

    if action_filter:
        rows = query_db(
            """SELECT al.*, u.username FROM activity_logs al
               LEFT JOIN users u ON u.id = al.user_id
               WHERE al.action ILIKE %s
               ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
            (f'%{action_filter}%', per_page, offset)
        ) or []
        total = query_db(
            "SELECT COUNT(*) AS c FROM activity_logs WHERE action ILIKE %s",
            (f'%{action_filter}%',), one=True
        )['c']
    else:
        rows = query_db(
            """SELECT al.*, u.username FROM activity_logs al
               LEFT JOIN users u ON u.id = al.user_id
               ORDER BY al.created_at DESC LIMIT %s OFFSET %s""",
            (per_page, offset)
        ) or []
        total = query_db("SELECT COUNT(*) AS c FROM activity_logs", one=True)['c']

    total_pages = max((total + per_page - 1) // per_page, 1)
    admin_user  = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/logs.html',
                           logs=rows, admin_user=admin_user,
                           page=page, total_pages=total_pages,
                           action_filter=action_filter)


# ── Support tickets (admin) ───────────────────────────────────────────────────
@admin_bp.route('/tickets')
@admin_required
def tickets():
    status_filter = request.args.get('status', '').strip()
    if status_filter in ('open', 'in_progress', 'closed'):
        tickets_list = query_db(
            """SELECT t.*, u.username FROM support_tickets t
               JOIN users u ON u.id = t.user_id
               WHERE t.status=%s ORDER BY t.created_at DESC""",
            (status_filter,)
        ) or []
    else:
        tickets_list = query_db(
            """SELECT t.*, u.username FROM support_tickets t
               JOIN users u ON u.id = t.user_id
               ORDER BY t.created_at DESC"""
        ) or []

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/tickets.html',
                           tickets=tickets_list, admin_user=admin_user,
                           status_filter=status_filter)


@admin_bp.route('/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@admin_required
def ticket_detail(ticket_id):
    ticket = query_db(
        """SELECT t.*, u.username, u.email FROM support_tickets t
           JOIN users u ON u.id = t.user_id WHERE t.id=%s""",
        (ticket_id,), one=True
    )
    if not ticket:
        abort(404)

    if request.method == 'POST':
        reply  = request.form.get('reply', '').strip()
        status = request.form.get('status', ticket['status'])
        if status not in ('open', 'in_progress', 'closed'):
            status = ticket['status']

        execute_db(
            """UPDATE support_tickets
               SET admin_reply=%s, status=%s, replied_by=%s, replied_at=NOW()
               WHERE id=%s""",
            (reply or ticket['admin_reply'], status, session['user_id'], ticket_id)
        )
        # Notify user
        execute_db(
            "INSERT INTO notifications (user_id, type, message, link) VALUES (%s,'system',%s,%s)",
            (ticket['user_id'],
             f'Your support ticket "{ticket["subject"]}" has been updated.',
             url_for('support.view_ticket', ticket_id=ticket_id))
        )
        _log(session['user_id'], 'admin_ticket_reply', 'ticket', ticket_id)
        flash('Ticket updated and user notified.', 'success')
        return redirect(url_for('admin.ticket_detail', ticket_id=ticket_id))

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/ticket_detail.html',
                           ticket=ticket, admin_user=admin_user)


# ── Global search ─────────────────────────────────────────────────────────────
@admin_bp.route('/search')
@admin_required
def search():
    q = request.args.get('q', '').strip()
    results = {'users': [], 'files': [], 'tickets': []}

    if q:
        results['users'] = query_db(
            "SELECT id, username, email, is_active FROM users WHERE username ILIKE %s OR email ILIKE %s LIMIT 10",
            (f'%{q}%', f'%{q}%')
        ) or []

        raw_files = query_db(
            """SELECT f.id, f.original_name, u.username AS owner, f.size_bytes
               FROM files f JOIN users u ON u.id = f.owner_id
               WHERE f.original_name ILIKE %s AND f.is_deleted=FALSE LIMIT 10""",
            (f'%{q}%',)
        ) or []
        results['files'] = [dict(f) for f in raw_files]
        for f in results['files']:
            f['size_human'] = human_readable_size(f['size_bytes'])

        results['tickets'] = query_db(
            "SELECT id, subject, status FROM support_tickets WHERE subject ILIKE %s LIMIT 10",
            (f'%{q}%',)
        ) or []

    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/search.html',
                           results=results, q=q, admin_user=admin_user)


# ── Security monitoring ───────────────────────────────────────────────────────
@admin_bp.route('/security')
@admin_required
def security():
    """Security overview — failed logins, locked accounts, recent suspicious activity."""
    admin_user = query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)

    # Locked or failed login accounts
    suspicious = query_db(
        """SELECT id, username, email, failed_login_attempts, locked_until, last_login, is_active
           FROM users WHERE failed_login_attempts > 0 OR locked_until IS NOT NULL
           ORDER BY failed_login_attempts DESC"""
    ) or []

    # Recent login events (success + fail)
    login_logs = query_db(
        """SELECT al.*, u.username FROM activity_logs al
           LEFT JOIN users u ON u.id = al.user_id
           WHERE al.action IN ('login','logout','register','password_change')
           ORDER BY al.created_at DESC LIMIT 30"""
    ) or []

    # Failed login count (last 24h)
    failed_24h = query_db(
        """SELECT COUNT(*) AS c FROM activity_logs
           WHERE action='login_failed' AND created_at > NOW() - INTERVAL '24 hours'""",
        one=True
    )

    # Active sessions count
    active_sessions = query_db(
        "SELECT COUNT(*) AS c FROM user_sessions WHERE is_revoked=FALSE AND expires_at > NOW()",
        one=True
    )

    # Total users locked
    locked_count = query_db(
        "SELECT COUNT(*) AS c FROM users WHERE locked_until > NOW()",
        one=True
    )

    stats = {
        'failed_24h':      failed_24h['c'] if failed_24h else 0,
        'active_sessions': active_sessions['c'] if active_sessions else 0,
        'locked_accounts': locked_count['c'] if locked_count else 0,
        'suspicious_users': len(suspicious),
    }

    return render_template('admin/security.html',
                           admin_user=admin_user,
                           suspicious=suspicious,
                           login_logs=login_logs,
                           stats=stats)
