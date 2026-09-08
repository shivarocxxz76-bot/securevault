import os
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, send_from_directory,
                   current_app, abort, jsonify)
from werkzeug.utils import secure_filename

from ..database import query_db, execute_db
from ..helpers  import (login_required, secure_filename_uuid,
                        allowed_file, human_readable_size,
                        storage_percent, get_file_icon)

files_bp = Blueprint('files', __name__)


def _log(user_id, action, target_type=None, target_id=None, details=None):
    execute_db(
        """INSERT INTO activity_logs (user_id, action, target_type, target_id, details, ip_address)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (user_id, action, target_type, target_id, details, request.remote_addr)
    )


def _update_storage(user_id, delta):
    """Add delta (positive or negative) to user's storage_used_bytes."""
    execute_db(
        "UPDATE users SET storage_used_bytes = storage_used_bytes + %s WHERE id = %s",
        (delta, user_id)
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────
@files_bp.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    # Total file count
    total_files = query_db(
        "SELECT COUNT(*) AS cnt FROM files WHERE owner_id=%s AND is_deleted=FALSE", (uid,), one=True
    )
    # Total folders
    total_folders = query_db(
        "SELECT COUNT(*) AS cnt FROM folders WHERE owner_id=%s AND is_deleted=FALSE", (uid,), one=True
    )
    # Shared with me count
    shared_count = query_db(
        "SELECT COUNT(*) AS cnt FROM file_shares WHERE shared_with=%s", (uid,), one=True
    )
    # Recent files
    recent_files = query_db(
        """SELECT * FROM files WHERE owner_id=%s AND is_deleted=FALSE
           ORDER BY created_at DESC LIMIT 8""", (uid,)
    )
    # Unread notifications
    unread = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True
    )

    recent_files = [dict(f) for f in (recent_files or [])]
    for f in recent_files:
        f['icon']       = get_file_icon(f['original_name'])
        f['size_human'] = human_readable_size(f['size_bytes'])

    return render_template('dashboard/index.html',
                           user=user,
                           recent_files=recent_files or [],
                           total_files=total_files['cnt'] if total_files else 0,
                           total_folders=total_folders['cnt'] if total_folders else 0,
                           shared_count=shared_count['cnt'] if shared_count else 0,
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


# ── Upload ────────────────────────────────────────────────────────────────────
@files_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    uid = session['user_id']
    user = query_db("SELECT storage_used_bytes, storage_limit_bytes FROM users WHERE id=%s",
                    (uid,), one=True)
    folder_id = request.form.get('folder_id') or None

    uploaded_files = request.files.getlist('files')
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        flash('No files selected.', 'warning')
        return redirect(request.referrer or url_for('files.dashboard'))

    # Ensure upload folder exists (important for Render /tmp/uploads)
    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)

    # Use plain int to avoid RealDictRow mutation issues
    storage_used = int(user['storage_used_bytes'])
    storage_limit = int(user['storage_limit_bytes'])

    saved = 0
    for file in uploaded_files:
        if file.filename == '':
            continue
        if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
            flash(f'File type not allowed: {file.filename}', 'warning')
            continue

        file_data = file.read()
        size = len(file_data)

        # Storage limit check
        if storage_used + size > storage_limit:
            flash('Storage limit reached. Please upgrade your plan.', 'danger')
            break

        stored_name = secure_filename_uuid(file.filename)
        save_path   = os.path.join(upload_dir, stored_name)

        try:
            with open(save_path, 'wb') as f:
                f.write(file_data)
        except Exception as e:
            flash(f'Failed to save file: {file.filename}. Error: {str(e)}', 'danger')
            continue

        rec = execute_db(
            """INSERT INTO files (owner_id, folder_id, original_name, stored_name, mime_type, size_bytes)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (uid, folder_id, secure_filename(file.filename), stored_name, file.content_type, size),
            returning=True
        )
        _update_storage(uid, size)
        storage_used += size
        _log(uid, 'upload', 'file', rec['id'], file.filename)
        saved += 1

    if saved:
        flash(f'{saved} file(s) uploaded successfully.', 'success')

    return redirect(request.referrer or url_for('files.dashboard'))


# ── Download ──────────────────────────────────────────────────────────────────
@files_bp.route('/file/download/<int:file_id>')
@login_required
def download(file_id):
    uid = session['user_id']
    file = query_db("SELECT * FROM files WHERE id=%s AND is_deleted=FALSE", (file_id,), one=True)
    if not file:
        abort(404)

    # Access check: owner OR shared with this user
    if file['owner_id'] != uid:
        share = query_db(
            "SELECT id FROM file_shares WHERE file_id=%s AND shared_with=%s",
            (file_id, uid), one=True
        )
        if not share:
            abort(403)

    _log(uid, 'download', 'file', file_id, file['original_name'])
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        file['stored_name'],
        download_name=file['original_name'],
        as_attachment=True
    )


# ── Delete (move to trash) ─────────────────────────────────────────────────────
@files_bp.route('/file/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    uid = session['user_id']
    file = query_db("SELECT * FROM files WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
                    (file_id, uid), one=True)
    if not file:
        abort(404)

    execute_db(
        "UPDATE files SET is_deleted=TRUE, deleted_at=NOW() WHERE id=%s",
        (file_id,)
    )
    _log(uid, 'delete_file', 'file', file_id, file['original_name'])
    flash(f'"{file["original_name"]}" moved to Recycle Bin.', 'info')
    return redirect(request.referrer or url_for('files.dashboard'))


# ── Rename ────────────────────────────────────────────────────────────────────
@files_bp.route('/file/rename/<int:file_id>', methods=['POST'])
@login_required
def rename_file(file_id):
    uid      = session['user_id']
    new_name = request.form.get('new_name', '').strip()
    file = query_db("SELECT * FROM files WHERE id=%s AND owner_id=%s AND is_deleted=FALSE",
                    (file_id, uid), one=True)
    if not file or not new_name:
        abort(404)

    # Preserve original extension
    orig_ext = ''
    if '.' in file['original_name']:
        orig_ext = '.' + file['original_name'].rsplit('.', 1)[1]
    if not new_name.endswith(orig_ext):
        new_name = new_name + orig_ext

    execute_db("UPDATE files SET original_name=%s WHERE id=%s", (new_name, file_id))
    _log(uid, 'rename_file', 'file', file_id, f'{file["original_name"]} -> {new_name}')
    flash('File renamed.', 'success')
    return redirect(request.referrer or url_for('files.dashboard'))


# ── List files in folder (AJAX / page) ───────────────────────────────────────
@files_bp.route('/files/folder/<int:folder_id>')
@login_required
def files_in_folder(folder_id):
    uid = session['user_id']

    # Verify folder ownership (or shared)
    folder = query_db(
        "SELECT * FROM folders WHERE id=%s AND is_deleted=FALSE", (folder_id,), one=True
    )
    if not folder:
        abort(404)

    if folder['owner_id'] != uid:
        share = query_db(
            "SELECT id FROM folder_shares WHERE folder_id=%s AND shared_with=%s",
            (folder_id, uid), one=True
        )
        if not share:
            abort(403)

    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    files = query_db(
        "SELECT * FROM files WHERE folder_id=%s AND is_deleted=FALSE ORDER BY created_at DESC",
        (folder_id,)
    )
    subfolders = query_db(
        "SELECT * FROM folders WHERE parent_id=%s AND is_deleted=FALSE ORDER BY name",
        (folder_id,)
    )

    files = [dict(f) for f in (files or [])]
    for f in files:
        f['icon']       = get_file_icon(f['original_name'])
        f['size_human'] = human_readable_size(f['size_bytes'])

    # Breadcrumb
    breadcrumb = _build_breadcrumb(folder_id)
    unread = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE",
        (uid,), one=True
    )

    return render_template('files/folder_view.html',
                           folder=folder,
                           files=files or [],
                           subfolders=subfolders or [],
                           user=user,
                           breadcrumb=breadcrumb,
                           unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))


def _build_breadcrumb(folder_id):
    """Build a list of (name, id) from root to current folder."""
    crumbs = []
    fid = folder_id
    while fid:
        f = query_db("SELECT id, name, parent_id FROM folders WHERE id=%s", (fid,), one=True)
        if not f:
            break
        crumbs.insert(0, {'id': f['id'], 'name': f['name']})
        fid = f['parent_id']
    return crumbs


# ── Folder tree JSON (for right-panel live tree) ──────────────────────────────
@files_bp.route('/api/folder-tree')
@login_required
def folder_tree():
    """Return nested folder tree as JSON for the dashboard tree panel."""
    uid = session['user_id']
    def get_children(parent_id):
        rows = query_db(
            "SELECT id, name FROM folders WHERE owner_id=%s AND parent_id IS NOT DISTINCT FROM %s AND is_deleted=FALSE ORDER BY name",
            (uid, parent_id)
        ) or []
        return [{'id': r['id'], 'name': r['name'], 'children': get_children(r['id'])} for r in rows]
    return jsonify({'tree': get_children(None)})


# ── All My Files (flat view) ──────────────────────────────────────────────────
@files_bp.route('/my-files')
@login_required
def my_files():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    search = request.args.get('q', '').strip()
    if search:
        all_files = query_db(
            """SELECT f.*, fo.name AS folder_name
               FROM files f LEFT JOIN folders fo ON fo.id = f.folder_id
               WHERE f.owner_id=%s AND f.is_deleted=FALSE AND f.original_name ILIKE %s
               ORDER BY f.created_at DESC""",
            (uid, f'%{search}%')
        )
    else:
        all_files = query_db(
            """SELECT f.*, fo.name AS folder_name
               FROM files f LEFT JOIN folders fo ON fo.id = f.folder_id
               WHERE f.owner_id=%s AND f.is_deleted=FALSE
               ORDER BY f.created_at DESC""",
            (uid,)
        )

    all_files = [dict(f) for f in (all_files or [])]
    for f in all_files:
        f['icon']       = get_file_icon(f['original_name'])
        f['size_human'] = human_readable_size(f['size_bytes'])

    folders = query_db(
        "SELECT * FROM folders WHERE owner_id=%s AND parent_id IS NULL AND is_deleted=FALSE ORDER BY name",
        (uid,)
    )
    unread = query_db(
        "SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=%s AND is_read=FALSE", (uid,), one=True
    )
    return render_template('files/my_files.html',
                           user=user, all_files=all_files, folders=folders or [],
                           search=search, unread=unread['cnt'] if unread else 0,
                           used_pct=storage_percent(user['storage_used_bytes'], user['storage_limit_bytes']),
                           used_human=human_readable_size(user['storage_used_bytes']),
                           limit_human=human_readable_size(user['storage_limit_bytes']))
