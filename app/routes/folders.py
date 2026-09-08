from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, abort)

from ..database import query_db, execute_db
from ..helpers  import login_required

folders_bp = Blueprint('folders', __name__)


def _log(user_id, action, target_id=None, details=None):
    execute_db(
        "INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address) VALUES (%s,%s,'folder',%s,%s,%s)",
        (user_id, action, target_id, details, request.remote_addr)
    )


# ── Create folder ─────────────────────────────────────────────────────────────
@folders_bp.route('/folder/create', methods=['POST'])
@login_required
def create_folder():
    uid       = session['user_id']
    name      = request.form.get('name', '').strip()
    parent_id = request.form.get('parent_id') or None

    if not name:
        flash('Folder name is required.', 'danger')
        return redirect(request.referrer or url_for('files.dashboard'))
    if len(name) > 255:
        flash('Folder name too long.', 'danger')
        return redirect(request.referrer or url_for('files.dashboard'))

    # Duplicate check in same location
    existing = query_db(
        "SELECT id FROM folders WHERE owner_id=%s AND parent_id IS NOT DISTINCT FROM %s AND name=%s AND is_deleted=FALSE",
        (uid, parent_id, name), one=True
    )
    if existing:
        flash(f'A folder named "{name}" already exists here.', 'warning')
        return redirect(request.referrer or url_for('files.dashboard'))

    folder = execute_db(
        "INSERT INTO folders (owner_id, parent_id, name) VALUES (%s,%s,%s) RETURNING id",
        (uid, parent_id, name), returning=True
    )
    _log(uid, 'create_folder', folder['id'], name)
    flash(f'Folder "{name}" created.', 'success')
    return redirect(request.referrer or url_for('files.dashboard'))


# ── Rename folder ─────────────────────────────────────────────────────────────
@folders_bp.route('/folder/rename/<int:folder_id>', methods=['POST'])
@login_required
def rename_folder(folder_id):
    uid      = session['user_id']
    new_name = request.form.get('new_name', '').strip()

    folder = query_db(
        "SELECT * FROM folders WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
        (folder_id, uid), one=True
    )
    if not folder or not new_name:
        abort(404)

    # Duplicate check in same parent
    dup = query_db(
        "SELECT id FROM folders WHERE owner_id=%s AND parent_id IS NOT DISTINCT FROM %s AND name=%s AND is_deleted=FALSE AND id!=%s",
        (uid, folder['parent_id'], new_name, folder_id), one=True
    )
    if dup:
        flash(f'A folder named "{new_name}" already exists here.', 'warning')
        return redirect(request.referrer or url_for('files.dashboard'))

    execute_db("UPDATE folders SET name=%s WHERE id=%s", (new_name, folder_id))
    _log(uid, 'rename_folder', folder_id, f'{folder["name"]} -> {new_name}')
    flash('Folder renamed.', 'success')
    return redirect(request.referrer or url_for('files.dashboard'))


# ── Delete folder (move to trash) ─────────────────────────────────────────────
@folders_bp.route('/folder/delete/<int:folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    uid = session['user_id']
    folder = query_db(
        "SELECT * FROM folders WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
        (folder_id, uid), one=True
    )
    if not folder:
        abort(404)

    # Soft-delete folder and all its contents recursively
    _soft_delete_recursive(folder_id, uid)
    _log(uid, 'delete_folder', folder_id, folder['name'])
    flash(f'Folder "{folder["name"]}" moved to Recycle Bin.', 'info')
    return redirect(request.referrer or url_for('files.dashboard'))


def _soft_delete_recursive(folder_id, uid):
    """Recursively soft-delete a folder and all nested folders/files."""
    execute_db(
        "UPDATE folders SET is_deleted=TRUE, deleted_at=NOW() WHERE id=%s",
        (folder_id,)
    )
    execute_db(
        "UPDATE files SET is_deleted=TRUE, deleted_at=NOW() WHERE folder_id=%s AND is_deleted=FALSE",
        (folder_id,)
    )
    children = query_db(
        "SELECT id FROM folders WHERE parent_id=%s AND is_deleted=FALSE", (folder_id,)
    )
    for child in (children or []):
        _soft_delete_recursive(child['id'], uid)
