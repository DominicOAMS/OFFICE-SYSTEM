from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from . import program_menu_repo, users_repo
from .nav import flatten_slugs
from .security import DEFAULT_PASSWORD, PASSWORD_REQUIREMENTS, is_valid_password

main_bp = Blueprint("main", __name__)

OPEN_ENDPOINTS = {"main.login", "main.logout", "main.change_password"}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_name"):
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapped


@main_bp.before_request
def enforce_password_change():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if session.get("user_id") and session.get("must_change_password"):
        return redirect(url_for("main.change_password"))
    return None


@main_bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = users_repo.find_active_by_email(email) if email else None
        if user and password and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"] or user["email"]
            session["user_type"] = user["position"] or ""
            session["user_email"] = user["email"]
            session["user_branch"] = user["branch"] or ""
            session["must_change_password"] = bool(user["mustChangePassword"])
            return redirect(url_for("main.dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@main_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not session.get("user_id"):
        return redirect(url_for("main.login"))

    forced = bool(session.get("must_change_password"))
    error = ""
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not is_valid_password(new_password):
            error = PASSWORD_REQUIREMENTS
        elif new_password != confirm_password:
            error = "New password and confirmation do not match."
        else:
            users_repo.set_password(
                session["user_id"], new_password, updated_by=session["user_id"], must_change_password=False
            )
            session["must_change_password"] = False
            flash("Password updated successfully.", "success")
            return redirect(url_for("main.dashboard"))

    template = "change_password_forced.html" if forced else "change_password.html"
    return render_template(template, error=error, password_requirements=PASSWORD_REQUIREMENTS)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@main_bp.route("/page/parameters_business_partners")
@login_required
def business_partners():
    return render_template("business_partners.html")


@main_bp.route("/page/parameters_users")
@login_required
def user_accounts():
    users = users_repo.list_active_users()
    positions = users_repo.list_distinct_positions()
    branches = users_repo.list_distinct_branches()
    menu_groups = program_menu_repo.list_menu_groups()
    return render_template(
        "user_accounts.html", users=users, positions=positions, branches=branches, menu_groups=menu_groups
    )


@main_bp.route("/page/parameters_users/add", methods=["POST"])
@login_required
def user_accounts_add():
    data = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "password": DEFAULT_PASSWORD,
        "position": request.form.get("position", "").strip(),
        "collector": 1 if request.form.get("collector") else 0,
        "privileges": ",".join(request.form.getlist("privileges")),
        "branch": request.form.get("branch", "").strip(),
    }
    if not data["name"] or not data["email"]:
        flash("Name and email are required.", "error")
        return redirect(url_for("main.user_accounts"))

    users_repo.create_user(data, created_by=session.get("user_id"))
    flash(
        f'User account created with default password "{DEFAULT_PASSWORD}". They must change it on first login.',
        "success",
    )
    return redirect(url_for("main.user_accounts"))


@main_bp.route("/page/parameters_users/<int:user_id>/edit", methods=["POST"])
@login_required
def user_accounts_edit(user_id):
    data = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
        "position": request.form.get("position", "").strip(),
        "collector": 1 if request.form.get("collector") else 0,
        "privileges": ",".join(request.form.getlist("privileges")),
        "branch": request.form.get("branch", "").strip(),
    }
    if not data["name"] or not data["email"]:
        flash("Name and email are required.", "error")
        return redirect(url_for("main.user_accounts"))

    users_repo.update_user(user_id, data, updated_by=session.get("user_id"))
    flash("User account updated.", "success")
    return redirect(url_for("main.user_accounts"))


@main_bp.route("/page/parameters_users/<int:user_id>/delete", methods=["POST"])
@login_required
def user_accounts_delete(user_id):
    users_repo.soft_delete_user(user_id, updated_by=session.get("user_id"))
    flash("User account deleted.", "success")
    return redirect(url_for("main.user_accounts"))


@main_bp.route("/page/parameters_users/<int:user_id>/reset-password", methods=["POST"])
@login_required
def user_accounts_reset_password(user_id):
    user = users_repo.get_user(user_id)
    if not user:
        abort(404)
    temp_password = users_repo.reset_password(user_id, updated_by=session.get("user_id"))
    flash(
        f"Temporary password for {user['name']} ({user['email']}): {temp_password} "
        "— share this with the user; they must change it on next login.",
        "success",
    )
    return redirect(url_for("main.user_accounts"))


@main_bp.route("/page/<slug>")
@login_required
def page(slug):
    item = flatten_slugs().get(slug)
    if not item:
        abort(404)
    return render_template("placeholder.html", page_title=item["label"], page_icon=item["icon"])
