from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash

from . import customers_repo, program_menu_repo, suppliers_repo, users_repo
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


def _parse_customer_form():
    payment_term_days = request.form.get("paymentTermDays", "").strip()
    return {
        "code": request.form.get("code", "").strip(),
        "name": request.form.get("name", "").strip(),
        "address": request.form.get("address", "").strip() or None,
        "tin": request.form.get("tin", "").strip() or None,
        "paymentTermDays": int(payment_term_days) if payment_term_days.isdigit() else 0,
        "salesRep": request.form.get("salesRep", "").strip() or None,
        "customerType": request.form.get("customerType", "").strip() or None,
    }


@main_bp.route("/page/parameters_customers")
@login_required
def customers():
    records = customers_repo.list_active_customers()
    customer_types = customers_repo.list_distinct_customer_types()
    sales_reps = customers_repo.list_distinct_sales_reps()
    next_id_number = customers_repo.next_customer_id_number()
    return render_template(
        "customers.html",
        customers=records,
        customer_types=customer_types,
        sales_reps=sales_reps,
        next_id_number=next_id_number,
    )


@main_bp.route("/page/parameters_customers/add", methods=["POST"])
@login_required
def customers_add():
    data = _parse_customer_form()
    if not data["code"] or not data["name"]:
        flash("Customer code and name are required.", "error")
        return redirect(url_for("main.customers"))

    try:
        customers_repo.create_customer(data, created_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Customer code "{data["code"]}" is already in use.', "error")
        return redirect(url_for("main.customers"))

    flash("Customer created.", "success")
    return redirect(url_for("main.customers"))


@main_bp.route("/page/parameters_customers/<int:customer_id>/edit", methods=["POST"])
@login_required
def customers_edit(customer_id):
    data = _parse_customer_form()
    if not data["code"] or not data["name"]:
        flash("Customer code and name are required.", "error")
        return redirect(url_for("main.customers"))

    try:
        customers_repo.update_customer(customer_id, data, updated_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Customer code "{data["code"]}" is already in use.', "error")
        return redirect(url_for("main.customers"))

    flash("Customer updated.", "success")
    return redirect(url_for("main.customers"))


@main_bp.route("/page/parameters_customers/<int:customer_id>/delete", methods=["POST"])
@login_required
def customers_delete(customer_id):
    customers_repo.soft_delete_customer(customer_id, updated_by=session.get("user_id"))
    flash("Customer deleted.", "success")
    return redirect(url_for("main.customers"))


def _parse_product_form():
    price = request.form.get("price", "").strip()
    effective_date = request.form.get("effectiveDate", "").strip()
    return {
        "priceCode": request.form.get("priceCode", "").strip() or None,
        "catalog": request.form.get("catalog", "").strip(),
        "customerDescription": request.form.get("customerDescription", "").strip() or None,
        "category": request.form.get("category", "").strip() or None,
        "unit": request.form.get("unit", "").strip() or None,
        "price": price or None,
        "effectiveDate": effective_date or None,
    }


@main_bp.route("/page/parameters_customers/<int:customer_id>/products")
@login_required
def customer_products(customer_id):
    customer = customers_repo.get_customer(customer_id)
    if not customer:
        abort(404)
    products = customers_repo.list_products_for_customer(customer_id)
    units = customers_repo.list_allowed_units()
    price_codes = customers_repo.list_price_codes_for_customer(customer_id)
    inventory_items = customers_repo.list_active_inventory_items()
    return render_template(
        "customer_products.html",
        customer=customer,
        products=products,
        units=units,
        price_codes=price_codes,
        inventory_items=inventory_items,
    )


@main_bp.route("/page/parameters_customers/<int:customer_id>/products/add", methods=["POST"])
@login_required
def customer_products_add(customer_id):
    data = _parse_product_form()
    redirect_args = {"customer_id": customer_id}
    if data["priceCode"]:
        redirect_args["priceCode"] = data["priceCode"]

    if not data["catalog"] or not data["price"] or not data["customerDescription"] or not data["unit"]:
        flash("Catalog, description, unit, and price are required.", "error")
        return redirect(url_for("main.customer_products", **redirect_args))
    is_new_product = request.form.get("mode", "add") != "reprice"
    if is_new_product and customers_repo.catalog_priced_under_code(customer_id, data["catalog"], data["priceCode"]):
        flash(
            f'"{data["catalog"]}" already has a price under this price code — '
            'use "Add new price" on that row instead.',
            "error",
        )
        return redirect(url_for("main.customer_products", **redirect_args))
    if customers_repo.product_price_exists(customer_id, data):
        flash("This exact price is already on file.", "error")
        return redirect(url_for("main.customer_products", **redirect_args))

    customers_repo.create_product(customer_id, data, created_by=session.get("user_id"))
    flash("Product price added.", "success")
    return redirect(url_for("main.customer_products", **redirect_args))


@main_bp.route("/page/parameters_customers/<int:customer_id>/products/history")
@login_required
def customer_product_history(customer_id):
    """Price history for one catalog line, rendered into the history modal."""
    if not customers_repo.get_customer(customer_id):
        abort(404)
    rows = customers_repo.list_price_history(
        customer_id,
        request.args.get("catalog") or None,
        request.args.get("priceCode") or None,
        request.args.get("unit") or None,
    )
    return render_template("_price_history.html", rows=rows)


@main_bp.route("/page/parameters_customers/<int:customer_id>/products/<int:product_id>/delete", methods=["POST"])
@login_required
def customer_products_delete(customer_id, product_id):
    customers_repo.soft_delete_product(product_id, updated_by=session.get("user_id"))
    flash("Product deleted.", "success")
    return redirect(url_for("main.customer_products", customer_id=customer_id))


def _parse_supplier_form():
    return {
        "code": request.form.get("code", "").strip(),
        "name": request.form.get("name", "").strip(),
        "category": request.form.get("category", "").strip() or None,
        "status": "Inactive" if request.form.get("status") == "Inactive" else "Active",
        "address": request.form.get("address", "").strip() or None,
        "telephoneNumber": request.form.get("telephoneNumber", "").strip() or None,
        "faxNumber": request.form.get("faxNumber", "").strip() or None,
        "email": request.form.get("email", "").strip() or None,
        "paymentTerm": request.form.get("paymentTerm", "").strip() or None,
        "tin": request.form.get("tin", "").strip() or None,
        "priceType": request.form.get("priceType", "").strip() or "Regular",
    }


@main_bp.route("/page/parameters_suppliers")
@login_required
def suppliers():
    records = suppliers_repo.list_active_suppliers()
    categories = suppliers_repo.list_distinct_categories()
    price_types = suppliers_repo.list_distinct_price_types()
    payment_terms = suppliers_repo.list_distinct_payment_terms()
    return render_template(
        "suppliers.html",
        suppliers=records,
        categories=categories,
        price_types=price_types,
        payment_terms=payment_terms,
    )


@main_bp.route("/page/parameters_suppliers/add", methods=["POST"])
@login_required
def suppliers_add():
    data = _parse_supplier_form()
    if not data["code"] or not data["name"]:
        flash("Supplier code and name are required.", "error")
        return redirect(url_for("main.suppliers"))

    try:
        suppliers_repo.create_supplier(data, created_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Supplier code "{data["code"]}" is already in use.', "error")
        return redirect(url_for("main.suppliers"))

    flash(f'Supplier "{data["name"]}" created.', "success")
    return redirect(url_for("main.suppliers"))


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/edit", methods=["POST"])
@login_required
def suppliers_edit(supplier_id):
    data = _parse_supplier_form()
    if not data["code"] or not data["name"]:
        flash("Supplier code and name are required.", "error")
        return redirect(url_for("main.suppliers"))

    try:
        suppliers_repo.update_supplier(supplier_id, data, updated_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Supplier code "{data["code"]}" is already in use.', "error")
        return redirect(url_for("main.suppliers"))

    flash(f'Supplier "{data["name"]}" updated.', "success")
    return redirect(url_for("main.suppliers"))


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def suppliers_delete(supplier_id):
    suppliers_repo.soft_delete_supplier(supplier_id, updated_by=session.get("user_id"))
    flash("Supplier deleted.", "success")
    return redirect(url_for("main.suppliers"))


def _parse_supplier_product_form():
    price = request.form.get("price", "").strip()
    effective_date = request.form.get("effectiveDate", "").strip()
    return {
        "catalog": request.form.get("catalog", "").strip(),
        "description": request.form.get("description", "").strip() or None,
        "category": request.form.get("category", "").strip() or None,
        "unit": request.form.get("unit", "").strip() or None,
        "price": price or None,
        "priceCode": request.form.get("priceCode", "").strip() or None,
        "effectiveDate": effective_date or None,
    }


SUPPLIER_PRODUCTS_PER_PAGE = 50


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/products")
@login_required
def supplier_products(supplier_id):
    supplier = suppliers_repo.get_supplier(supplier_id)
    if not supplier:
        abort(404)

    search = request.args.get("q", "").strip()
    # A price code must be chosen before a product can be added, so the list is
    # scoped to it too. "not supplied at all" differs from "supplied as blank".
    has_price_code = "priceCode" in request.args
    price_code = request.args.get("priceCode", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total = suppliers_repo.count_products_for_supplier(
        supplier_id, search or None, price_code, has_price_code
    )
    page_count = max(1, -(-total // SUPPLIER_PRODUCTS_PER_PAGE))  # ceil
    page = min(page, page_count)

    products = suppliers_repo.list_products_for_supplier(
        supplier_id,
        search=search or None,
        limit=SUPPLIER_PRODUCTS_PER_PAGE,
        offset=(page - 1) * SUPPLIER_PRODUCTS_PER_PAGE,
        price_code=price_code,
        has_price_code=has_price_code,
    )

    # Catalogs already priced under this code are excluded from the picker so the
    # same product can't be added twice against one price code.
    priced_catalogs = (
        suppliers_repo.list_priced_catalogs(supplier_id, price_code) if has_price_code else []
    )

    return render_template(
        "supplier_products.html",
        supplier=supplier,
        products=products,
        units=suppliers_repo.list_allowed_units(),
        price_codes=suppliers_repo.list_price_codes_for_supplier(supplier_id),
        catalog_suggestions=suppliers_repo.list_catalog_suggestions(supplier_id),
        priced_catalogs=priced_catalogs,
        search=search,
        price_code=price_code,
        has_price_code=has_price_code,
        page=page,
        page_count=page_count,
        total=total,
        per_page=SUPPLIER_PRODUCTS_PER_PAGE,
    )


def _back_to_products(supplier_id, data=None):
    """Return to the price list with the price code still selected, so the user
    stays in the context they were adding under."""
    return redirect(
        url_for(
            "main.supplier_products",
            supplier_id=supplier_id,
            priceCode=(data or {}).get("priceCode") or request.form.get("priceCode", ""),
        )
    )


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/products/add", methods=["POST"])
@login_required
def supplier_products_add(supplier_id):
    data = _parse_supplier_product_form()
    if not data["catalog"] or not data["price"]:
        flash("Catalog and price are required.", "error")
        return _back_to_products(supplier_id, data)
    if suppliers_repo.product_price_exists(supplier_id, data):
        flash(
            "That exact price (same catalog, price code, unit, price and effective date) is already on file.",
            "error",
        )
        return _back_to_products(supplier_id, data)

    suppliers_repo.create_product(supplier_id, data, created_by=session.get("user_id"))
    flash(f'Product "{data["catalog"]}" added.', "success")
    return _back_to_products(supplier_id, data)


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/products/<int:product_id>/edit", methods=["POST"])
@login_required
def supplier_products_edit(supplier_id, product_id):
    product = suppliers_repo.get_product(product_id)
    if not product or product["supplierId"] != supplier_id:
        abort(404)

    data = _parse_supplier_product_form()
    if not data["catalog"] or not data["price"]:
        flash("Catalog and price are required.", "error")
        return _back_to_products(supplier_id, data)
    if suppliers_repo.product_price_exists(supplier_id, data, exclude_id=product_id):
        flash(
            "Another row already has that exact catalog, price code, unit, price and effective date.",
            "error",
        )
        return _back_to_products(supplier_id, data)

    suppliers_repo.update_product(product_id, data, updated_by=session.get("user_id"))
    flash(f'Product "{data["catalog"]}" updated.', "success")
    return _back_to_products(supplier_id, data)


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/products/<int:product_id>/delete", methods=["POST"])
@login_required
def supplier_products_delete(supplier_id, product_id):
    suppliers_repo.soft_delete_product(product_id, updated_by=session.get("user_id"))
    flash("Price removed.", "success")
    return redirect(url_for("main.supplier_products", supplier_id=supplier_id))


@main_bp.route("/page/parameters_suppliers/<int:supplier_id>/products/history")
@login_required
def supplier_product_history(supplier_id):
    """Price history for one catalog line, rendered into the history modal."""
    if not suppliers_repo.get_supplier(supplier_id):
        abort(404)
    rows = suppliers_repo.list_price_history(
        supplier_id,
        request.args.get("catalog") or None,
        request.args.get("priceCode") or None,
        request.args.get("unit") or None,
    )
    return render_template("_price_history.html", rows=rows)


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
