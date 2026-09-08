from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, storage_percent

notif_bp = Blueprint('notif', __name__)


@notif_bp.route('/notifications')
@login_required
def notifications():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    notifs = query_db(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC",
        (uid,)
    )
    unread = sum(1 for n in (notifs or []) if not n['is_read'])
    return render_template('notifications/index.html',
                           user=user, notifs=notifs or [], unread=unread,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


@notif_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    uid = session['user_id']
    execute_db(
        "UPDATE notifications SET is_read=TRUE WHERE id=%s AND user_id=%s",
        (notif_id, uid)
    )
    return redirect(request.referrer or url_for('notif.notifications'))


@notif_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    uid = session['user_id']
    execute_db("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (uid,))
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notif.notifications'))


@notif_bp.route('/notifications/delete/<int:notif_id>', methods=['POST'])
@login_required
def delete_notif(notif_id):
    uid = session['user_id']
    execute_db("DELETE FROM notifications WHERE id=%s AND user_id=%s", (notif_id, uid))
    return redirect(request.referrer or url_for('notif.notifications'))


@notif_bp.route('/notifications/count')
@login_required
def unread_count():
    """AJAX endpoint for live badge update."""
    uid = session['user_id']
    row = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE",
        (uid,), one=True
    )
    return jsonify({'count': row['cnt'] if row else 0})
