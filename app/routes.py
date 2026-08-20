import json
import os
import uuid
from datetime import date
from decimal import Decimal
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from pymysql.err import DataError, IntegrityError
from werkzeug.security import check_password_hash

from . import (
    customers_repo,
    fuel_approvers_repo,
    fuel_po_repo,
    fuel_prices_repo,
    program_menu_repo,
    suppliers_repo,
    users_repo,
    vehicles_repo,
)
from . import routing
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


FUEL_PRICE_CATEGORIES = ("Diesel", "Unleaded", "Premium")


def _parse_vehicle_form():
    fuel_efficiency = request.form.get("fuelEfficiencyKmPerLiter", "").strip()
    try:
        fuel_efficiency_value = float(fuel_efficiency) if fuel_efficiency else None
    except ValueError:
        fuel_efficiency_value = None
    price_category = request.form.get("fuelPriceCategory", "").strip()
    return {
        "plateNumber": request.form.get("plateNumber", "").strip(),
        "vehicleModel": request.form.get("vehicleModel", "").strip() or None,
        "fuelType": request.form.get("fuelType", "").strip() or None,
        "fuelEfficiencyKmPerLiter": fuel_efficiency_value,
        "fuelPriceCategory": price_category if price_category in FUEL_PRICE_CATEGORIES else None,
        "assignedUserId": int(request.form["assignedUserId"]) if request.form.get("assignedUserId") else None,
        "status": "Inactive" if request.form.get("status") == "Inactive" else "Active",
    }


@main_bp.route("/page/parameters_vehicles")
@login_required
def vehicles():
    records = vehicles_repo.list_active_vehicles()
    fuel_types = sorted({v["fuelType"] for v in records if v["fuelType"]})
    return render_template(
        "vehicles.html", vehicles=records, users=users_repo.list_active_users(), fuel_types=fuel_types
    )


@main_bp.route("/page/parameters_vehicles/add", methods=["POST"])
@login_required
def vehicles_add():
    data = _parse_vehicle_form()
    if not data["plateNumber"]:
        flash("Plate number is required.", "error")
        return redirect(url_for("main.vehicles"))

    try:
        vehicles_repo.create_vehicle(data, created_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Plate number "{data["plateNumber"]}" is already in use.', "error")
        return redirect(url_for("main.vehicles"))

    flash(f'Vehicle "{data["plateNumber"]}" added.', "success")
    return redirect(url_for("main.vehicles"))


@main_bp.route("/page/parameters_vehicles/<int:vehicle_id>/edit", methods=["POST"])
@login_required
def vehicles_edit(vehicle_id):
    data = _parse_vehicle_form()
    if not data["plateNumber"]:
        flash("Plate number is required.", "error")
        return redirect(url_for("main.vehicles"))

    try:
        vehicles_repo.update_vehicle(vehicle_id, data, updated_by=session.get("user_id"))
    except IntegrityError:
        flash(f'Plate number "{data["plateNumber"]}" is already in use.', "error")
        return redirect(url_for("main.vehicles"))

    flash(f'Vehicle "{data["plateNumber"]}" updated.', "success")
    return redirect(url_for("main.vehicles"))


@main_bp.route("/page/parameters_vehicles/<int:vehicle_id>/delete", methods=["POST"])
@login_required
def vehicles_delete(vehicle_id):
    vehicles_repo.soft_delete_vehicle(vehicle_id, updated_by=session.get("user_id"))
    flash("Vehicle deleted.", "success")
    return redirect(url_for("main.vehicles"))


@main_bp.route("/page/parameters_fuel_approvers")
@login_required
def fuel_approvers():
    return render_template(
        "fuel_approvers.html",
        approvers=fuel_approvers_repo.list_approvers(),
        final_approvers=fuel_approvers_repo.list_final_approvers(),
        users=users_repo.list_active_users(),
    )


@main_bp.route("/page/parameters_fuel_approvers/add", methods=["POST"])
@login_required
def fuel_approvers_add():
    user_id = request.form.get("userId", "").strip()
    role = request.form.get("role", "").strip()
    if role not in ("Approver", "Final Approver") or not user_id.isdigit():
        flash("Choose a user and a role.", "error")
        return redirect(url_for("main.fuel_approvers"))

    fuel_approvers_repo.add_approver(int(user_id), role, created_by=session.get("user_id"))
    flash(f"{role} added.", "success")
    return redirect(url_for("main.fuel_approvers"))


@main_bp.route("/page/parameters_fuel_approvers/<int:approver_id>/remove", methods=["POST"])
@login_required
def fuel_approvers_remove(approver_id):
    fuel_approvers_repo.remove_approver(approver_id, updated_by=session.get("user_id"))
    flash("Removed.", "success")
    return redirect(url_for("main.fuel_approvers"))


@main_bp.route("/page/parameters_fuel_prices")
@login_required
def fuel_prices():
    return render_template("fuel_prices.html", prices=fuel_prices_repo.list_prices())


@main_bp.route("/page/parameters_fuel_prices/update-price", methods=["POST"])
@login_required
def fuel_prices_update_price():
    fuel_category = request.form.get("fuelCategory", "").strip()
    if fuel_category not in FUEL_PRICE_CATEGORIES:
        flash("Unknown fuel category.", "error")
        return redirect(url_for("main.fuel_prices"))

    price = _parse_money(request.form.get("pricePerLiter"))
    if not price:
        flash("Enter a valid price per liter.", "error")
        return redirect(url_for("main.fuel_prices"))

    fuel_prices_repo.update_price(fuel_category, price, updated_by=session.get("user_id"))
    flash(f"{fuel_category} price updated.", "success")
    return redirect(url_for("main.fuel_prices"))


ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _save_attachment(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ATTACHMENT_EXTENSIONS:
        raise ValueError("Attachment must be a photo (jpg/png/webp) or a PDF.")
    filename = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
    return filename


def _parse_money(value):
    value = (value or "").strip().replace(",", "")
    try:
        parsed = float(value)
    except ValueError:
        return None
    return f"{parsed:.2f}" if parsed > 0 else None


def _parse_coordinate(value):
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _clip(value, limit=255):
    """Everything bound into a VARCHAR(255) goes through here. Nominatim display_name
    labels run 60-120 characters each, so a 3-stop itinerary already blows past 255 - and
    under MySQL's default STRICT_TRANS_TABLES that is a DataError thrown mid-INSERT, not a
    silent truncation. Multi-date requests make it routine."""
    value = value or ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _parse_trip_date(value):
    """A trip's date as a datetime.date. Anything that isn't a real ISO yyyy-mm-dd is
    rejected outright rather than coerced, so a typo can never land as NULL."""
    try:
        return date.fromisoformat((value or "").strip())
    except (ValueError, TypeError):
        return None


def _sum_or_none(values):
    """SUM semantics: missing values are skipped, all-missing rolls up to None not 0."""
    present = [v for v in values if v is not None]
    return round(sum(present), 2) if present else None


def _sum_money_or_none(values):
    """_parse_money hands back 2dp strings; summed as Decimal so the PO total is exactly
    the sum of the per-date amounts shown on screen, to the cent, with no float drift."""
    present = [Decimal(v) for v in values if v is not None]
    return f"{sum(present):.2f}" if present else None


def _clean_destinations(parsed):
    """The validation half of destination parsing, shared with _parse_trips (which already
    holds a decoded list). Drops any stop missing a real label + lat + lng - a stop with no
    coordinates can't be routed, so keeping it would only corrupt the estimate."""
    if not isinstance(parsed, list):
        return []
    destinations = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        lat = _parse_coordinate(str(item.get("lat", "")))
        lng = _parse_coordinate(str(item.get("lng", "")))
        label = _clip((item.get("label") or "").strip())
        if lat is None or lng is None or not label:
            continue
        destinations.append({"label": label, "lat": lat, "lng": lng})
    return destinations


def _parse_destinations(raw_json):
    """Decode + validate a flat destinations payload. Still the estimate endpoint's entry
    point, unchanged in signature."""
    try:
        parsed = json.loads(raw_json or "[]")
    except ValueError:
        return []
    return _clean_destinations(parsed)


def _summarize_stops(destinations):
    """One date's itinerary - the same " → " shape the single-trip flow always used."""
    return _clip(" → ".join(d["label"] for d in destinations)) or None


def _summarize_trips(trips):
    """tbl_fuel_pos.destination stays the one-line searchable summary of the whole PO - the
    list column reads it and _filter_clauses LIKEs it. A single-date PO keeps exactly the
    old "A → B → C" text so nothing about how existing rows look changes; only multi-date
    POs take the date-prefixed "Aug 21: A → B | Aug 22: C" form.

    %b %d rather than %-d: %-d is glibc-only and raises on Windows, which is this platform.
    """
    if not trips:
        return None
    if len(trips) == 1:
        return trips[0]["destination"]
    return _clip(
        " | ".join(f'{t["date"].strftime("%b %d")}: {t["destination"] or "—"}' for t in trips)
    )


MAX_TRIPS_PER_PO = 30
MAX_STOPS_PER_TRIP = 20


def _parse_trips(raw_json):
    """The nested dated-trips payload from the Add form.

    A whole trip is DROPPED (not silently patched) when it's missing any of the three
    things that make it a trip - a real date, at least one mappable destination, and an
    amount above zero. Dropping rather than patching means a malformed payload surfaces as
    "add at least one date" instead of quietly creating a PO whose total doesn't match what
    the requester saw on screen.

    Capped because an unbounded payload is one insert (and one potential routing call) per
    element; the UI can't produce anything near these caps.
    """
    try:
        parsed = json.loads(raw_json or "[]")
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []

    trips = []
    for item in parsed[:MAX_TRIPS_PER_PO]:
        if not isinstance(item, dict):
            continue
        trip_date = _parse_trip_date(item.get("date"))
        destinations = _clean_destinations(item.get("destinations"))[:MAX_STOPS_PER_TRIP]
        # str() wrappers are required, not stylistic: _parse_money does (value or "").strip()
        # which raises AttributeError on a raw JSON float.
        amount = _parse_money(str(item.get("amountRequested", "")))
        if trip_date is None or not destinations or amount is None:
            continue
        trips.append(
            {
                "date": trip_date,
                "startLocation": _clip((item.get("startLocation") or "").strip()) or None,
                "startLat": _parse_coordinate(str(item.get("startLat", ""))),
                "startLng": _parse_coordinate(str(item.get("startLng", ""))),
                "destinations": destinations,
                "destination": _summarize_stops(destinations),
                "estimatedDistanceKm": _parse_coordinate(str(item.get("estimatedDistanceKm", ""))),
                "estimatedAmount": _parse_money(str(item.get("estimatedAmount", ""))),
                "amountRequested": amount,
            }
        )
    return trips


def _parse_fuel_po_form():
    other_user_id = request.form.get("otherUserId", "").strip()
    requested_for_user_id = (
        int(other_user_id)
        if request.form.get("requestFor") == "other" and other_user_id.isdigit()
        else session.get("user_id")
    )
    vehicle_id = request.form.get("vehicleId", "").strip()
    approver_user_id = request.form.get("approverUserId", "").strip()
    odometer = request.form.get("odometer", "").strip()
    fuel_efficiency = request.form.get("fuelEfficiencyKmPerLiter", "").strip()
    trips = _parse_trips(request.form.get("tripsJson"))
    first_trip = trips[0] if trips else None
    return {
        "requestedForUserId": requested_for_user_id,
        "requestedByUserId": session.get("user_id"),
        "vehicleId": int(vehicle_id) if vehicle_id.isdigit() else None,
        "fuelType": request.form.get("fuelType", "").strip() or None,
        "fuelEfficiencyKmPerLiter": _parse_coordinate(fuel_efficiency),
        "purpose": request.form.get("purpose", "").strip() or None,
        "odometer": int(odometer) if odometer.isdigit() else None,
        "approverUserId": int(approver_user_id) if approver_user_id.isdigit() else None,
        "trips": trips,
        # PO-level rollups. Kept denormalized so the list page, the View modal's data-*
        # attributes and _filter_clauses' destination LIKE all keep reading one row per PO
        # with no changes.
        "startLocation": first_trip["startLocation"] if first_trip else None,
        "startLat": first_trip["startLat"] if first_trip else None,
        "startLng": first_trip["startLng"] if first_trip else None,
        "destination": _summarize_trips(trips),
        "destinationLat": None,
        "destinationLng": None,
        "estimatedDistanceKm": _sum_or_none(t["estimatedDistanceKm"] for t in trips),
        "estimatedAmount": _sum_money_or_none(t["estimatedAmount"] for t in trips),
        "amountRequested": _sum_money_or_none(t["amountRequested"] for t in trips),
    }


FUEL_PO_PER_PAGE = 30


def _trip_for_view(trip):
    """Display-ready primitives for the View modal's per-date breakdown. Built here rather
    than handed raw to |tojson because DB rows carry decimal.Decimal and datetime.date,
    whose JSON encoding is a Flask-version detail (dates would come out as RFC-822
    'Thu, 21 Aug 2026 00:00:00 GMT', which is not what anyone wants on screen)."""
    return {
        "date": trip["tripDate"].strftime("%b %d, %Y") if trip["tripDate"] else None,
        "startLocation": trip["startLocation"],
        "destination": trip["destination"],
        "stops": [d["destination"] for d in trip["destinations"]],
        "distanceKm": float(trip["estimatedDistanceKm"]) if trip["estimatedDistanceKm"] is not None else None,
        "amount": float(trip["amountRequested"]) if trip["amountRequested"] is not None else None,
    }


@main_bp.route("/page/purchase_order_fuel")
@login_required
def fuel_po():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total = fuel_po_repo.count_fuel_pos(search or None, status or None)
    page_count = max(1, -(-total // FUEL_PO_PER_PAGE))  # ceil
    page = min(page, page_count)

    records = fuel_po_repo.list_fuel_pos(
        search=search or None,
        status=status or None,
        limit=FUEL_PO_PER_PAGE,
        offset=(page - 1) * FUEL_PO_PER_PAGE,
    )
    trips_by_po = {
        po_id: [_trip_for_view(t) for t in trips]
        for po_id, trips in fuel_po_repo.list_trips_for_fuel_pos([r["id"] for r in records]).items()
    }
    return render_template(
        "fuel_po.html",
        fuel_pos=records,
        trips_by_po=trips_by_po,
        vehicles=vehicles_repo.list_active_vehicles(),
        users=users_repo.list_active_users(),
        approvers=fuel_approvers_repo.list_approvers(),
        final_approver_ids={a["userId"] for a in fuel_approvers_repo.list_final_approvers()},
        search=search,
        status=status,
        page=page,
        page_count=page_count,
        total=total,
        per_page=FUEL_PO_PER_PAGE,
    )


@main_bp.route("/page/purchase_order_fuel/estimate", methods=["POST"])
@login_required
def fuel_po_estimate():
    """Estimate ONE date's trip. The Add form calls this once per date, only for the date
    being edited - a bulk server-side loop would multiply routing calls against a limited
    daily quota and could serialize several 15s timeouts into one request.

    tripKey is an opaque client token echoed straight back, so a slow response can't be
    applied to the wrong date's card if the requester edits two dates quickly.
    """
    trip_key = request.form.get("tripKey", "")[:32]
    vehicle_id = request.form.get("vehicleId", "").strip()
    start_lat = _parse_coordinate(request.form.get("startLat", "").strip())
    start_lng = _parse_coordinate(request.form.get("startLng", "").strip())
    efficiency = _parse_coordinate(request.form.get("fuelEfficiencyKmPerLiter", "").strip())
    destinations = _parse_destinations(request.form.get("destinationsJson"))

    vehicle = vehicles_repo.get_vehicle(int(vehicle_id)) if vehicle_id.isdigit() else None
    if not vehicle:
        return {"tripKey": trip_key, "error": "Select a vehicle first."}, 400
    if start_lat is None or start_lng is None:
        return {"tripKey": trip_key, "error": "Pick a starting location first."}, 400
    if not destinations:
        return {"tripKey": trip_key, "error": "Add at least one destination first."}, 400
    if not efficiency or efficiency <= 0:
        return {
            "tripKey": trip_key,
            "error": "Enter your vehicle's fuel efficiency (km/L) to see an estimate.",
        }, 200
    if not vehicle["fuelPriceCategory"]:
        return {
            "tripKey": trip_key,
            "error": "This vehicle doesn't have a fuel price category set yet — set one in Parameters > Vehicles.",
        }, 200

    price_row = fuel_prices_repo.get_price(vehicle["fuelPriceCategory"])
    if not price_row or not price_row["pricePerLiter"]:
        return {
            "tripKey": trip_key,
            "error": f'No price set for {vehicle["fuelPriceCategory"]} yet — set one in Parameters > Fuel Prices.',
        }, 200

    waypoints = [(start_lat, start_lng)] + [(d["lat"], d["lng"]) for d in destinations]
    distance_km = routing.get_route_distance_km(waypoints)
    if distance_km is None:
        return {
            "tripKey": trip_key,
            "error": "Couldn't calculate a route between those locations — enter the amount manually.",
        }, 200

    liters = round(distance_km / efficiency, 2)
    price_per_liter = float(price_row["pricePerLiter"])
    estimated_amount = round(liters * price_per_liter, 2)

    return {
        "tripKey": trip_key,
        "distanceKm": distance_km,
        "liters": liters,
        "pricePerLiter": price_per_liter,
        "estimatedAmount": estimated_amount,
    }


@main_bp.route("/page/purchase_order_fuel/add", methods=["POST"])
@login_required
def fuel_po_add():
    data = _parse_fuel_po_form()
    if not data["vehicleId"] or not data["approverUserId"]:
        flash("Vehicle and Approver are required.", "error")
        return redirect(url_for("main.fuel_po"))
    # _parse_trips guarantees every surviving trip has a date, >=1 destination and an
    # amount, so a non-empty list always rolls up to a non-None total - no separate
    # amountRequested check needed.
    if not data["trips"]:
        flash(
            "Add at least one date — every date needs a starting location, at least one "
            "destination, and an amount.",
            "error",
        )
        return redirect(url_for("main.fuel_po"))

    try:
        data["odometerAttachmentPath"] = _save_attachment(request.files.get("odometerAttachment"))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("main.fuel_po"))

    try:
        fuel_po_repo.create_fuel_po(data, created_by=session.get("user_id"))
    except (IntegrityError, DataError):
        flash(
            "Could not submit — one of the selected records no longer exists, or a "
            "location name was too long to save.",
            "error",
        )
        return redirect(url_for("main.fuel_po"))

    trip_count = len(data["trips"])
    flash(
        f"Fuel PO submitted for approval ({trip_count} date{'s' if trip_count != 1 else ''}).",
        "success",
    )
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/delete", methods=["POST"])
@login_required
def fuel_po_delete(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po:
        abort(404)
    if po["requestedByUserId"] != session.get("user_id"):
        abort(403)
    fuel_po_repo.soft_delete_fuel_po(po_id, updated_by=session.get("user_id"))
    flash("Fuel PO deleted.", "success")
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/approve", methods=["POST"])
@login_required
def fuel_po_approve(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po:
        abort(404)
    if po["status"] != "Pending Approval" or po["approverUserId"] != session.get("user_id"):
        abort(403)
    fuel_po_repo.approve_stage1(
        po_id, approved_by=session.get("user_id"), remarks=request.form.get("remarks", "").strip() or None
    )
    flash("Fuel PO approved and routed to the Final Approver.", "success")
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/reject", methods=["POST"])
@login_required
def fuel_po_reject(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po:
        abort(404)
    if po["status"] != "Pending Approval" or po["approverUserId"] != session.get("user_id"):
        abort(403)
    fuel_po_repo.reject_stage1(
        po_id, rejected_by=session.get("user_id"), remarks=request.form.get("remarks", "").strip() or None
    )
    flash("Fuel PO rejected.", "success")
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/final-approve", methods=["POST"])
@login_required
def fuel_po_final_approve(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po:
        abort(404)
    if po["status"] != "Pending Final Approval" or not fuel_approvers_repo.is_final_approver(session.get("user_id")):
        abort(403)
    fuel_po_repo.approve_stage2(
        po_id, approved_by=session.get("user_id"), remarks=request.form.get("remarks", "").strip() or None
    )
    flash("Fuel PO given final approval.", "success")
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/final-reject", methods=["POST"])
@login_required
def fuel_po_final_reject(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po:
        abort(404)
    if po["status"] != "Pending Final Approval" or not fuel_approvers_repo.is_final_approver(session.get("user_id")):
        abort(403)
    fuel_po_repo.reject_stage2(
        po_id, rejected_by=session.get("user_id"), remarks=request.form.get("remarks", "").strip() or None
    )
    flash("Fuel PO rejected.", "success")
    return redirect(url_for("main.fuel_po"))


@main_bp.route("/page/purchase_order_fuel/<int:po_id>/attachment")
@login_required
def fuel_po_attachment(po_id):
    po = fuel_po_repo.get_fuel_po(po_id)
    if not po or not po["odometerAttachmentPath"]:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], po["odometerAttachmentPath"])


@main_bp.route("/page/<slug>")
@login_required
def page(slug):
    item = flatten_slugs().get(slug)
    if not item:
        abort(404)
    return render_template("placeholder.html", page_title=item["label"], page_icon=item["icon"])
