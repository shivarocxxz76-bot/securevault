from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, abort)

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, get_file_icon, storage_percent

sharing_bp = Blueprint('sharing', __name__)


def _notify(user_id, msg, link=None):
    execute_db(
        "INSERT INTO notifications (user_id, type, message, link) VALUES (%s,'share',%s,%s)",
        (user_id, msg, link)
    )


def _log(user_id, action, target_type, target_id, details=None):
    execute_db(
        "INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address) VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, action, target_type, target_id, details, request.remote_addr)
    )


# ── Share a file ──────────────────────────────────────────────────────────────
@sharing_bp.route('/file/share/<int:file_id>', methods=['POST'])
@login_required
def share_file(file_id):
    uid        = session['user_id']
    share_with = request.form.get('share_with_email', '').strip().lower()
    permission = request.form.get('permission', 'view')

    if permission not in ('view', 'download'):
        permission = 'view'

    file = query_db(
        "SELECT * FROM files WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
        (file_id, uid), one=True
    )
    if not file:
        abort(404)

    target = query_db("SELECT id, username FROM users WHERE email=%s", (share_with,), one=True)
    if not target:
        flash('User not found with that email.', 'danger')
        return redirect(request.referrer or url_for('sharing.shared_by_me'))
    if target['id'] == uid:
        flash('You cannot share a file with yourself.', 'warning')
        return redirect(request.referrer or url_for('sharing.shared_by_me'))

    # Upsert share record
    existing = query_db(
        "SELECT id FROM file_shares WHERE file_id=%s AND shared_with=%s",
        (file_id, target['id']), one=True
    )
    if existing:
        execute_db(
            "UPDATE file_shares SET permission=%s WHERE file_id=%s AND shared_with=%s",
            (permission, file_id, target['id'])
        )
        flash(f'Share permissions updated for {target["username"]}.', 'success')
    else:
        execute_db(
            "INSERT INTO file_shares (file_id, shared_by, shared_with, permission) VALUES (%s,%s,%s,%s)",
            (file_id, uid, target['id'], permission)
        )
        _notify(target['id'],
                f'{session["username"]} shared a file with you: {file["original_name"]}',
                url_for('sharing.shared_with_me'))
        flash(f'File shared with {target["username"]}.', 'success')

    _log(uid, 'share_file', 'file', file_id, f'with {share_with}')
    return redirect(request.referrer or url_for('sharing.shared_by_me'))


# ── Revoke file share ─────────────────────────────────────────────────────────
@sharing_bp.route('/file/share/revoke/<int:share_id>', methods=['POST'])
@login_required
def revoke_file_share(share_id):
    uid = session['user_id']
    share = query_db(
        "SELECT fs.*, f.owner_id FROM file_shares fs JOIN files f ON f.id=fs.file_id WHERE fs.id=%s",
        (share_id,), one=True
    )
    if not share or share['owner_id'] != uid:
        abort(403)
    execute_db("DELETE FROM file_shares WHERE id=%s", (share_id,))
    flash('File share revoked.', 'info')
    return redirect(request.referrer or url_for('sharing.shared_by_me'))


# ── Share a folder ────────────────────────────────────────────────────────────
@sharing_bp.route('/folder/share/<int:folder_id>', methods=['POST'])
@login_required
def share_folder(folder_id):
    uid        = session['user_id']
    share_with = request.form.get('share_with_email', '').strip().lower()
    permission = request.form.get('permission', 'view')
    if permission not in ('view', 'download'):
        permission = 'view'

    folder = query_db(
        "SELECT * FROM folders WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
        (folder_id, uid), one=True
    )
    if not folder:
        abort(404)

    target = query_db("SELECT id, username FROM users WHERE email=%s", (share_with,), one=True)
    if not target:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('sharing.shared_by_me'))
    if target['id'] == uid:
        flash('You cannot share with yourself.', 'warning')
        return redirect(request.referrer or url_for('sharing.shared_by_me'))

    existing = query_db(
        "SELECT id FROM folder_shares WHERE folder_id=%s AND shared_with=%s",
        (folder_id, target['id']), one=True
    )
    if existing:
        execute_db(
            "UPDATE folder_shares SET permission=%s WHERE folder_id=%s AND shared_with=%s",
            (permission, folder_id, target['id'])
        )
        flash('Share permissions updated.', 'success')
    else:
        execute_db(
            "INSERT INTO folder_shares (folder_id, shared_by, shared_with, permission) VALUES (%s,%s,%s,%s)",
            (folder_id, uid, target['id'], permission)
        )
        _notify(target['id'],
                f'{session["username"]} shared folder "{folder["name"]}" with you',
                url_for('sharing.shared_with_me'))
        flash(f'Folder shared with {target["username"]}.', 'success')

    _log(uid, 'share_folder', 'folder', folder_id, f'with {share_with}')
    return redirect(request.referrer or url_for('sharing.shared_by_me'))


# ── Revoke folder share ───────────────────────────────────────────────────────
@sharing_bp.route('/folder/share/revoke/<int:share_id>', methods=['POST'])
@login_required
def revoke_folder_share(share_id):
    uid = session['user_id']
    share = query_db(
        "SELECT fs.*, f.owner_id FROM folder_shares fs JOIN folders f ON f.id=fs.folder_id WHERE fs.id=%s",
        (share_id,), one=True
    )
    if not share or share['owner_id'] != uid:
        abort(403)
    execute_db("DELETE FROM folder_shares WHERE id=%s", (share_id,))
    flash('Folder share revoked.', 'info')
    return redirect(request.referrer or url_for('sharing.shared_by_me'))


# ── Shared by me ──────────────────────────────────────────────────────────────
@sharing_bp.route('/shared/by-me')
@login_required
def shared_by_me():
    uid = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    file_shares = query_db(
        """SELECT fs.*, f.original_name, u.username AS shared_with_name, u.email AS shared_with_email
           FROM file_shares fs
           JOIN files f ON f.id = fs.file_id
           JOIN users u ON u.id = fs.shared_with
           WHERE fs.shared_by = %s AND f.is_deleted=FALSE
           ORDER BY fs.created_at DESC""",
        (uid,)
    )
    folder_shares = query_db(
        """SELECT fs.*, fo.name AS folder_name, u.username AS shared_with_name, u.email AS shared_with_email
           FROM folder_shares fs
           JOIN folders fo ON fo.id = fs.folder_id
           JOIN users u ON u.id = fs.shared_with
           WHERE fs.shared_by = %s AND fo.is_deleted=FALSE
           ORDER BY fs.created_at DESC""",
        (uid,)
    )
    unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
    return render_template('sharing/shared_by_me.html',
                           user=user, file_shares=file_shares or [],
                           folder_shares=folder_shares or [],
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


# ── Shared with me ────────────────────────────────────────────────────────────
@sharing_bp.route('/shared/with-me')
@login_required
def shared_with_me():
    uid = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    files = query_db(
        """SELECT f.*, fs.permission, u.username AS owner_name
           FROM file_shares fs
           JOIN files f ON f.id = fs.file_id
           JOIN users u ON u.id = f.owner_id
           WHERE fs.shared_with = %s AND f.is_deleted=FALSE
           ORDER BY fs.created_at DESC""",
        (uid,)
    )
    folders = query_db(
        """SELECT fo.*, fs.permission, u.username AS owner_name
           FROM folder_shares fs
           JOIN folders fo ON fo.id = fs.folder_id
           JOIN users u ON u.id = fo.owner_id
           WHERE fs.shared_with = %s AND fo.is_deleted=FALSE
           ORDER BY fs.created_at DESC""",
        (uid,)
    )
    files = [dict(f) for f in (files or [])]
    for f in files:
        f['icon']       = get_file_icon(f['original_name'])
        f['size_human'] = human_readable_size(f['size_bytes'])
    unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
    return render_template('sharing/shared_with_me.html',
                           user=user, files=files or [], folders=folders or [],
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))
