from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

main_bp = Blueprint("main", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_name"):
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapped


@main_bp.route("/", methods=["GET"])
def index():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if email and password:
            session["user_name"] = email
            session["user_type"] = "Admin"
            return redirect(url_for("main.dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
