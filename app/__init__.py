from flask import Flask, render_template, send_from_directory
from .config import Config
from . import database
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init DB teardown
    database.init_app(app)

    # Register blueprints
    from .routes.auth      import auth_bp
    from .routes.files     import files_bp
    from .routes.folders   import folders_bp
    from .routes.sharing   import sharing_bp
    from .routes.storage   import storage_bp
    from .routes.trash     import trash_bp
    from .routes.notif     import notif_bp
    from .routes.admin     import admin_bp
    from .routes.support   import support_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(folders_bp)
    app.register_blueprint(sharing_bp)
    app.register_blueprint(storage_bp)
    app.register_blueprint(trash_bp)
    app.register_blueprint(notif_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(support_bp)

    # ── PWA routes ────────────────────────────────────
    @app.route('/sw.js')
    def service_worker():
        """Serve SW from root so it has full scope."""
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'sw.js',
            mimetype='application/javascript'
        )

    @app.route('/manifest.json')
    def manifest():
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'manifest.json',
            mimetype='application/manifest+json'
        )

    @app.route('/offline')
    def offline():
        return render_template('pwa/offline.html')

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template('errors/413.html'), 413

    return app
