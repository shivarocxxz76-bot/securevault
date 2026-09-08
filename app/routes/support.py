from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, abort)

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, storage_percent

support_bp = Blueprint('support', __name__)


@support_bp.route('/support')
@login_required
def support():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    tickets = query_db(
        "SELECT * FROM support_tickets WHERE user_id=%s ORDER BY created_at DESC",
        (uid,)
    )
    unread = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE",
        (uid,), one=True
    )
    return render_template('support/index.html',
                           user=user, tickets=tickets or [],
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


@support_bp.route('/support/new', methods=['POST'])
@login_required
def new_ticket():
    uid     = session['user_id']
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()
    priority = request.form.get('priority', 'normal')

    if not subject or not message:
        flash('Subject and message are required.', 'danger')
        return redirect(url_for('support.support'))
    if priority not in ('low', 'normal', 'high'):
        priority = 'normal'

    execute_db(
        "INSERT INTO support_tickets (user_id, subject, message, priority) VALUES (%s,%s,%s,%s)",
        (uid, subject, message, priority)
    )
    flash('Your support ticket has been submitted.', 'success')
    return redirect(url_for('support.support'))


@support_bp.route('/support/ticket/<int:ticket_id>')
@login_required
def view_ticket(ticket_id):
    uid = session['user_id']
    ticket = query_db(
        "SELECT * FROM support_tickets WHERE id=%s AND user_id=%s",
        (ticket_id, uid), one=True
    )
    if not ticket:
        abort(404)
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    unread = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE",
        (uid,), one=True
    )
    return render_template('support/ticket_detail.html',
                           user=user, ticket=ticket,
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))
