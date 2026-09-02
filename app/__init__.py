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
        # request.view_args only carries a "slug" key for the generic /page/<slug>
        # placeholder route - every module that's since graduated to its own specific
        # route (e.g. /page/payables_vouchers) has no <slug> URL variable at all, so
        # this was silently going None for every real built module. That meant a
        # module's sidebar group never rendered as open/highlighted on its own pages -
        # visually indistinguishable from a click having "closed" the group. Every nav
        # slug's canonical path is /page/<slug> regardless of which route ultimately
        # serves it (Werkzeug just prefers the more specific route at request time), so
        # recovering it from the path itself works for every module, not just
        # not-yet-built placeholders.
        active_slug = request.view_args.get("slug") if request.view_args else None
        if active_slug is None and request.path.startswith("/page/"):
            active_slug = request.path[len("/page/"):].split("/")[0] or None
        return {"nav_items": NAV_ITEMS, "active_slug": active_slug}

    return app
