import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, abort)

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, storage_percent

storage_bp = Blueprint('storage', __name__)


# ── Storage overview ──────────────────────────────────────────────────────────
@storage_bp.route('/storage')
@login_required
def overview():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    plans = query_db("SELECT * FROM plans WHERE is_active=TRUE ORDER BY storage_bytes")
    payments = query_db(
        """SELECT p.*, pl.name AS plan_name
           FROM payments p JOIN plans pl ON pl.id=p.plan_id
           WHERE p.user_id=%s ORDER BY p.created_at DESC""",
        (uid,)
    )
    unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
    return render_template('storage/overview.html',
                           user=user, plans=plans or [], payments=payments or [],
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


# ── Checkout page ─────────────────────────────────────────────────────────────
@storage_bp.route('/storage/checkout/<int:plan_id>', methods=['GET', 'POST'])
@login_required
def checkout(plan_id):
    uid  = session['user_id']
    plan = query_db("SELECT * FROM plans WHERE id=%s AND is_active=TRUE", (plan_id,), one=True)
    if not plan:
        abort(404)
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    if request.method == 'POST':
        # Demo payment — generate fake transaction ref
        card_number = request.form.get('card_number', '').replace(' ', '')
        if len(card_number) < 13:
            flash('Please enter a valid card number.', 'danger')
            return render_template('storage/checkout.html', plan=plan, user=user,
                                   unread=0, used_pct=0, used_human='', limit_human='')

        transaction_ref = 'TXN-' + str(uuid.uuid4()).upper()[:12]

        # Record payment as completed (demo)
        payment = execute_db(
            """INSERT INTO payments (user_id, plan_id, amount_usd, status, transaction_ref)
               VALUES (%s,%s,%s,'completed',%s) RETURNING id""",
            (uid, plan_id, plan['price_usd'], transaction_ref),
            returning=True
        )

        # Upgrade user storage
        execute_db(
            "UPDATE users SET storage_limit_bytes=%s, current_plan=%s WHERE id=%s",
            (plan['storage_bytes'], plan['name'], uid)
        )

        # Notify user
        execute_db(
            "INSERT INTO notifications (user_id, type, message) VALUES (%s,'payment',%s)",
            (uid, f'Payment successful! You are now on the {plan["name"].title()} plan. Ref: {transaction_ref}')
        )

        execute_db(
            "INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address) VALUES (%s,'payment','plan',%s,%s,%s)",
            (uid, plan_id, f'Upgraded to {plan["name"]}', request.remote_addr)
        )

        flash(f'Payment successful! You are now on the {plan["name"].title()} plan.', 'success')
        return redirect(url_for('storage.overview'))

    unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
    return render_template('storage/checkout.html',
                           plan=plan, user=user,
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))
