import os
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app)

from ..database import query_db, execute_db
from ..helpers  import login_required, human_readable_size, storage_percent, get_file_icon

trash_bp = Blueprint('trash', __name__)


def _log(user_id, action, target_type, target_id, details=None):
    execute_db(
        "INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address) VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, action, target_type, target_id, details, request.remote_addr)
    )


# ── Recycle bin view ──────────────────────────────────────────────────────────
@trash_bp.route('/trash')
@login_required
def trash():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    deleted_files = query_db(
        "SELECT * FROM files WHERE owner_id=%s AND is_deleted=TRUE ORDER BY deleted_at DESC",
        (uid,)
    )
    deleted_folders = query_db(
        "SELECT * FROM folders WHERE owner_id=%s AND is_deleted=TRUE ORDER BY deleted_at DESC",
        (uid,)
    )
    deleted_files = [dict(f) for f in (deleted_files or [])]
    for f in deleted_files:
        f['icon']       = get_file_icon(f['original_name'])
        f['size_human'] = human_readable_size(f['size_bytes'])
    unread = query_db("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True)
    return render_template('trash/index.html',
                           user=user,
                           deleted_files=deleted_files or [],
                           deleted_folders=deleted_folders or [],
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


# ── Restore file ──────────────────────────────────────────────────────────────
@trash_bp.route('/trash/restore/file/<int:file_id>', methods=['POST'])
@login_required
def restore_file(file_id):
    uid = session['user_id']
    file = query_db("SELECT * FROM files WHERE id=%s AND owner_id=%s AND is_deleted=TRUE",
                    (file_id, uid), one=True)
    if not file:
        flash('File not found in trash.', 'danger')
        return redirect(url_for('trash.trash'))

    execute_db(
        "UPDATE files SET is_deleted=FALSE, deleted_at=NULL WHERE id=%s", (file_id,)
    )
    _log(uid, 'restore_file', 'file', file_id, file['original_name'])
    flash(f'"{file["original_name"]}" restored.', 'success')
    return redirect(url_for('trash.trash'))


# ── Restore folder ────────────────────────────────────────────────────────────
@trash_bp.route('/trash/restore/folder/<int:folder_id>', methods=['POST'])
@login_required
def restore_folder(folder_id):
    uid = session['user_id']
    folder = query_db("SELECT * FROM folders WHERE id=%s AND owner_id=%s AND is_deleted=TRUE",
                      (folder_id, uid), one=True)
    if not folder:
        flash('Folder not found in trash.', 'danger')
        return redirect(url_for('trash.trash'))

    _restore_folder_recursive(folder_id)
    _log(uid, 'restore_folder', 'folder', folder_id, folder['name'])
    flash(f'Folder "{folder["name"]}" restored.', 'success')
    return redirect(url_for('trash.trash'))


def _restore_folder_recursive(folder_id):
    execute_db("UPDATE folders SET is_deleted=FALSE, deleted_at=NULL WHERE id=%s", (folder_id,))
    execute_db("UPDATE files SET is_deleted=FALSE, deleted_at=NULL WHERE folder_id=%s", (folder_id,))
    children = query_db("SELECT id FROM folders WHERE parent_id=%s AND is_deleted=TRUE", (folder_id,))
    for c in (children or []):
        _restore_folder_recursive(c['id'])


# ── Permanent delete file ─────────────────────────────────────────────────────
@trash_bp.route('/trash/delete/file/<int:file_id>', methods=['POST'])
@login_required
def perm_delete_file(file_id):
    uid = session['user_id']
    file = query_db("SELECT * FROM files WHERE id=%s AND owner_id=%s AND is_deleted=TRUE",
                    (file_id, uid), one=True)
    if not file:
        flash('File not found in trash.', 'danger')
        return redirect(url_for('trash.trash'))

    # Remove from disk
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], file['stored_name'])
    if os.path.exists(path):
        os.remove(path)

    # Free up storage
    execute_db("UPDATE users SET storage_used_bytes = storage_used_bytes - %s WHERE id=%s",
               (file['size_bytes'], uid))
    execute_db("DELETE FROM files WHERE id=%s", (file_id,))
    _log(uid, 'perm_delete_file', 'file', file_id, file['original_name'])
    flash(f'"{file["original_name"]}" permanently deleted.', 'info')
    return redirect(url_for('trash.trash'))


# ── Permanent delete folder ───────────────────────────────────────────────────
@trash_bp.route('/trash/delete/folder/<int:folder_id>', methods=['POST'])
@login_required
def perm_delete_folder(folder_id):
    uid = session['user_id']
    folder = query_db("SELECT * FROM folders WHERE id=%s AND owner_id=%s AND is_deleted=TRUE",
                      (folder_id, uid), one=True)
    if not folder:
        flash('Folder not found in trash.', 'danger')
        return redirect(url_for('trash.trash'))

    _perm_delete_folder_recursive(folder_id, uid)
    execute_db("DELETE FROM folders WHERE id=%s", (folder_id,))
    _log(uid, 'perm_delete_folder', 'folder', folder_id, folder['name'])
    flash(f'Folder "{folder["name"]}" permanently deleted.', 'info')
    return redirect(url_for('trash.trash'))


def _perm_delete_folder_recursive(folder_id, uid):
    files = query_db("SELECT * FROM files WHERE folder_id=%s", (folder_id,))
    for file in (files or []):
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], file['stored_name'])
        if os.path.exists(path):
            os.remove(path)
        execute_db("UPDATE users SET storage_used_bytes = storage_used_bytes - %s WHERE id=%s",
                   (file['size_bytes'], uid))
    execute_db("DELETE FROM files WHERE folder_id=%s", (folder_id,))
    children = query_db("SELECT id FROM folders WHERE parent_id=%s", (folder_id,))
    for c in (children or []):
        _perm_delete_folder_recursive(c['id'], uid)
    execute_db("DELETE FROM folders WHERE id=%s", (folder_id,))


# ── Empty entire bin ──────────────────────────────────────────────────────────
@trash_bp.route('/trash/empty', methods=['POST'])
@login_required
def empty_trash():
    uid = session['user_id']

    # Delete all trashed files from disk
    trashed = query_db("SELECT * FROM files WHERE owner_id=%s AND is_deleted=TRUE", (uid,))
    total_freed = 0
    for file in (trashed or []):
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], file['stored_name'])
        if os.path.exists(path):
            os.remove(path)
        total_freed += file['size_bytes']

    execute_db("DELETE FROM files WHERE owner_id=%s AND is_deleted=TRUE", (uid,))
    execute_db("DELETE FROM folders WHERE owner_id=%s AND is_deleted=TRUE", (uid,))
    execute_db("UPDATE users SET storage_used_bytes = GREATEST(storage_used_bytes - %s, 0) WHERE id=%s",
               (total_freed, uid))

    _log(uid, 'empty_trash', 'user', uid)
    flash('Recycle Bin emptied.', 'info')
    return redirect(url_for('trash.trash'))
