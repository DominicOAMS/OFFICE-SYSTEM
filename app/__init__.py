import os

from flask import Flask, request


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key-change-me"

    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB, covers the fuel PO odometer attachment
    app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads", "fuel_po")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    from .nav import NAV_ITEMS

    @app.context_processor
    def inject_nav():
        active_slug = request.view_args.get("slug") if request.view_args else None
        return {"nav_items": NAV_ITEMS, "active_slug": active_slug}

    return app
