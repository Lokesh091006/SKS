import random
import re
import requests
import os

from flask import Flask, render_template, redirect, session, url_for, request, jsonify
from database import db
from models.product import Product
from models.user import User
from models.address import Address
from models.order import Order

from sqlalchemy import or_



   
   


# ================== APP CONFIG ==================
app = Flask(__name__)



BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'shop.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "sks_super_secret_key_123"

db.init_app(app)

# ================== FAST2SMS CONFIG ==================
FAST2SMS_API_KEY = "U41D0zVLyOfXbVbR1yI95pqxKvcqrgNIo38ZNJ7e01O7wVn6tjAm8p4nSnNa"

# ================== DB INIT + SAMPLE DATA ==================
with app.app_context():
    
    db.create_all()

    if Product.query.count() == 0:
        sample_products = [
            Product(name="Men T-Shirt", price=799, category="men", image="images/men1.jpg"),
            Product(name="Men Jeans", price=1299, category="men", image="images/men2.jpg"),
            Product(name="Men Jacket", price=1799, category="men", image="images/men3.jpg"),
            Product(name="Women Dress", price=1499, category="women", image="images/women1.jpg"),
            Product(name="Running Shoes", price=1999, category="shoes", image="images/shoes1.jpg"),
            Product(name="Men Hoodie", price=1999, category="men", image="images/men4.jpg"),

        ]
        db.session.add_all(sample_products)
        db.session.commit()

# ================== UTILS ==================
def send_sms_otp(mobile, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "route": "otp",
        "variables_values": otp,
        "numbers": mobile
    }
    headers = {
        "authorization": FAST2SMS_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=payload, headers=headers, timeout=5)

    print("FAST2SMS RESPONSE:", response.text)
    return response.json()

# ================== ROUTES ==================

# ---------- HOME ----------
@app.route("/")
def home():
    products = Product.query.all()
    return render_template("home.html", products=products)

# ---------- PROFILE ----------
@app.route("/login")
def login():
    return render_template("login.html")




@app.route("/firebase-login", methods=["POST"])
def firebase_login():
    mobile = request.json["mobile"]

    user = User.query.filter_by(mobile=mobile).first()

    if not user:
        user = User(mobile=mobile, username="Guest")
        db.session.add(user)
        db.session.commit()

    session["user_id"] = user.id
    return {"status": "ok"}




@app.route("/profile")
def profile():
    if "username" not in session:
        session["show_login"] = True
        return redirect(url_for("home"))
    return render_template("profile.html")




# ---------- SEND OTP ----------
@app.route("/send-otp", methods=["POST"])
def send_otp():
    mobile = request.form.get("mobile")
    if not mobile or not re.fullmatch(r"\d{10}", mobile):
        return "Invalid mobile number"
    otp = str(random.randint(100000, 999999))
    session["login_otp"] = otp
    session["login_mobile"] = mobile
    send_sms_otp(mobile, otp)
    print("DEBUG OTP:", otp)
    return redirect(url_for("verify_otp"))

# ---------- VERIFY OTP ----------
@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        entered = request.form.get("otp")
        saved = session.get("login_otp")
        mobile = session.get("login_mobile")

        if not saved or not mobile:
            return redirect("/")

        if entered != saved:
            return "❌ Wrong OTP"

        # OTP correct
        session.pop("login_otp")
        user = User.query.filter_by(mobile=mobile).first()

        if not user:
            # new user → go set username
            return redirect(url_for("set_username"))

        # existing user
        session["username"] = user.username
        session["user_id"] = user.id
        session.pop("show_login", None)
        next_page = session.pop("next", url_for("home"))
        return redirect(next_page)

    return render_template("verify_otp.html")

# ---------- SET USERNAME ----------
@app.route("/set-username", methods=["GET", "POST"])
def set_username():
    mobile = session.get("login_mobile")
    if not mobile:
        return redirect("/")

    if request.method == "POST":
        username = request.form["username"].strip()
        if not username:
            return render_template("set_username.html", error="Username required")
        user = User(mobile=mobile, username=username)
        db.session.add(user)
        db.session.commit()
        session["username"] = username
        session["user_id"] = user.id
        session.pop("login_mobile", None)
        return redirect(url_for("home"))

    return render_template("set_username.html")

# ---------- EDIT PROFILE ----------
@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if "username" not in session:
        session["show_login"] = True
        return redirect(url_for("home"))
    if request.method == "POST":
        session["username"] = request.form.get("username")
        session["email"] = request.form.get("email")
        session["mobile"] = request.form.get("mobile")
        return redirect(url_for("profile"))
    return render_template("edit_profile.html")

# ---------- WISHLIST ----------
@app.route("/wishlist")
def wishlist():
    wishlist_ids = session.get("wishlist", [])
    wishlist_products = [p for p in Product.query.all() if p.id in wishlist_ids]
    return render_template("wishlist.html", products=wishlist_products)

@app.route("/add-to-wishlist/<int:product_id>")
def add_to_wishlist(product_id):
    if "wishlist" not in session:
        session["wishlist"] = []
    if product_id not in session["wishlist"]:
        session["wishlist"].append(product_id)
        session.modified = True
    return redirect(request.referrer or url_for("home"))

@app.route("/wishlist/remove/<int:product_id>")
def remove_from_wishlist(product_id):
    if "wishlist" in session and product_id in session["wishlist"]:
        session["wishlist"].remove(product_id)
        session.modified = True
    return redirect(url_for("wishlist"))

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/order/<int:id>")
def order_detail(id):
    if "user_id" not in session:
        return redirect("/login")

    order = Order.query.get_or_404(id)
    return render_template("order_detail.html", order=order)



@app.route("/my-orders")
def my_orders():
    if "user_id" not in session:
        return redirect("/login")

    orders = Order.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Order.created_at.desc()).all()

    print("ORDERS:", orders)   # debug

    return render_template("my_orders.html", orders=orders)



# ---------- CATEGORY ----------
@app.route("/category/<name>")
def category(name):

    q = request.args.get("q")
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color")
    type_ = request.args.get("type")
    sort = request.args.get("sort")

    query = Product.query.filter_by(category=name)

    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))

    if type_:
        query = query.filter_by(type=type_)

    if color:
        query = query.filter_by(color=color)

    if min_price:
        query = query.filter(Product.price >= int(min_price))

    if max_price:
        query = query.filter(Product.price <= int(max_price))

    if sort == "low":
        query = query.order_by(Product.price.asc())
    elif sort == "high":
        query = query.order_by(Product.price.desc())
    elif sort == "az":
        query = query.order_by(Product.name.asc())

    products = query.all()

    return render_template("shop.html", products=products)


# ---------- SEARCH ----------
# ---------- SEARCH ----------


@app.route("/search")
def search():

    q = request.args.get("q", "").strip()
    category = request.args.get("category")
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")
    color = request.args.get("color")
    type_ = request.args.get("type")
    sort = request.args.get("sort")

    products = Product.query

    # 🔍 TEXT SEARCH — smart word matching
    if q:
        words = q.lower().split()

        for w in words:
            base = w.rstrip("s")   # hoodie / hoodies both match
            like = f"%{base}%"

            products = products.filter(or_(
                Product.name.ilike(like),
                Product.category.ilike(like),
                Product.type.ilike(like)
            ))

    # 🧵 category filter
    if category:
        products = products.filter(Product.category.ilike(f"%{category}%"))


    # 🎨 color
    if color:
        products = products.filter(Product.color.ilike(color))

    # 👕 type
    if type_:
        products = products.filter(Product.type.ilike(type_))

    # 💰 price
    if min_price and min_price.isdigit():
        products = products.filter(Product.price >= int(min_price))

    if max_price and max_price.isdigit():
        products = products.filter(Product.price <= int(max_price))

    # ↕ sort
    if sort == "low":
        products = products.order_by(Product.price.asc())
    elif sort == "high":
        products = products.order_by(Product.price.desc())

    results = products.all()

    return render_template(
        "search.html",
        products=results,
        query=q
    )



@app.route("/live-search")
def live_search():

    q = request.args.get("q", "").strip()

    if not q:
        return jsonify([])

    words = q.lower().split()

    products = Product.query

    for w in words:
        base = w.rstrip("s")
        products = products.filter(
            Product.name.ilike(f"%{base}%")
        )

    products = products.limit(6).all()

    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "image": p.image
        }
        for p in products
    ])






@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    cart_items = []
    total = 0
    for pid, qty in cart.items():
        product = Product.query.get(int(pid))
        subtotal = product.price * qty
        total += subtotal
        cart_items.append({"product": product, "qty": qty, "subtotal": subtotal})

    discount = 0
    if total > 3000:
        discount = 600
    elif total > 2000:
        discount = 300
    elif total > 1000:
        discount = 100
    final_amount = total - discount
    session["total_after_coupon"] = final_amount
    return render_template("cart.html", cart_items=cart_items, total=total, discount=discount, final_amount=final_amount)

@app.route("/add/<int:product_id>")
def add_to_cart(product_id):
    cart = session.get("cart", {})
    pid = str(product_id)
    cart[pid] = cart.get(pid, 0) + 1
    session["cart"] = cart
    return redirect(url_for("cart"))




@app.route("/increase/<int:product_id>")
def increase(product_id):
    cart = session.get("cart", {})
    cart[str(product_id)] += 1
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/decrease/<int:product_id>")
def decrease(product_id):
    cart = session.get("cart", {})
    pid = str(product_id)
    if cart[pid] > 1:
        cart[pid] -= 1
    else:
        del cart[pid]
    session["cart"] = cart
    return redirect(url_for("cart"))

# ---------- ADDRESS ----------
@app.route("/address", methods=["GET", "POST"])
def address():
    if "user_id" not in session:
        session["show_login"] = True
        return redirect(url_for("cart"))

    user_id = session["user_id"]
    if request.method == "POST":
        addr = Address.query.get(request.form["address_id"])
        session["address"] = addr.id
        return redirect(url_for("payment"))

    addresses = Address.query.filter_by(user_id=user_id).all()
    return render_template("address.html", addresses=addresses)

@app.route("/add-address", methods=["GET", "POST"])
def add_address():
    if "user_id" not in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        addr = Address(
            user_id=session["user_id"],
            name=request.form["name"],
            mobile=request.form["mobile"],
            house=request.form["house"],
            street=request.form["street"],
            city=request.form["city"],
            state=request.form["state"],
            pincode=request.form["pincode"]
        )
        db.session.add(addr)
        db.session.commit()
        return redirect(url_for("address"))

    return render_template("add_address.html")

@app.route("/delete-address/<int:id>")
def delete_address(id):
    if "user_id" not in session:
        return redirect(url_for("home"))

    addr = Address.query.get(id)
    if addr:
        db.session.delete(addr)
        db.session.commit()
    return redirect(url_for("address"))

# ---------- PAYMENT ----------
@app.route("/payment", methods=["GET", "POST"])
def payment():
    total_after_coupon = session.get("total_after_coupon") or 0

    if request.method == "POST":
        method = request.form.get("method")
        session["payment_method"] = method   # ✅ IMPORTANT

        if method == "cod":
            session["final_amount"] = total_after_coupon + 30
            return redirect(url_for("payment_success"))

        elif method in ["phonepe", "paytm", "supermoney", "pop"]:
            session["final_amount"] = round(total_after_coupon * 0.95, 2)
            return redirect(url_for("upi_details"))

        elif method == "card":
            session["final_amount"] = total_after_coupon
            return redirect(url_for("payment_success"))

    return render_template("payment.html", total_after_coupon=total_after_coupon)

# ---------- UPI ----------
@app.route("/upi-details", methods=["GET", "POST"])
def upi_details():
    if request.method == "POST":
        upi = request.form["upi"]
        if not re.match(r"^\d{10}@(axl|ybl)$", upi):
            return "Invalid UPI ID"
        session["upi_id"] = upi
        return redirect(url_for("upi_processing"))
    return render_template("upi_details.html")

@app.route("/upi-processing")
def upi_processing():
    return render_template("upi_processing.html", upi_id=session.get("upi_id"), amount=session.get("final_amount"))

@app.route("/payment-success")
def payment_success():
    if "user_id" not in session:
        return redirect("/login")

    cart = session.get("cart", {})
    address_id = session.get("address")
    payment_method = session.get("payment_method")

    created_orders = []   # ✅ template ki pampadaniki

    for pid, qty in cart.items():
        for _ in range(qty):   # qty handle chestundi
            order = Order(
                order_id="ORD" + str(random.randint(100000, 999999)),
                user_id=session["user_id"],
                product_id=int(pid),
                address_id=address_id,
                payment_method=payment_method,
                status="PLACED"
            )
            db.session.add(order)
            created_orders.append(order)   # ✅ collect

    db.session.commit()

    # cart clear cheyyi
    session.pop("cart", None)
    session.pop("payment_method", None)

    # ✅ success page ki orders pampu
    return render_template("success.html", orders=created_orders)

@app.route("/shop")
def shop():

    q = request.args.get("q")
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color")
    type_ = request.args.get("type")
    category = request.args.get("category")
    sort = request.args.get("sort")

    query = Product.query

    if q:

        words = q.lower().split()

        for w in words:

             like = f"%{w.rstrip('s')}%"
             query = query.filter(or_(
             Product.name.ilike(like),
             Product.category.ilike(like),
             Product.type.ilike(like)
        ))

    if category:

        query = query.filter(Product.category.ilike(f"%{category}%"))

      

    if type_:
        query = query.filter_by(type=type_)

    if color:
        query = query.filter_by(color=color)

    if min_price:
        query = query.filter(Product.price >= int(min_price))

    if max_price:
        query = query.filter(Product.price <= int(max_price))

    # sorting
    if sort == "low":
        query = query.order_by(Product.price.asc())
    elif sort == "high":
        query = query.order_by(Product.price.desc())
    elif sort == "az":
        query = query.order_by(Product.name.asc())

    products = query.all()

    return render_template("shop.html", products=products)



@app.route("/confirm-order", methods=["POST"])
def confirm_order():
    if "user_id" not in session:
        return redirect("/login")

    cart = session.get("cart", {})
    address_id = session.get("address")
    payment_method = request.form.get("method", "COD")

    for pid, qty in cart.items():
        for _ in range(qty):
            order = Order(
                order_id="ORD" + str(random.randint(100000, 999999)),
                user_id=session["user_id"],
                product_id=int(pid),
                address_id=address_id,
                payment_method=payment_method,
                status="PLACED"
            )
            db.session.add(order)

    db.session.commit()
    return redirect("/payment-success")

# ---------- PRODUCT PAGE ----------
@app.route("/product/<int:pid>")
def product_page(pid):
    product = Product.query.get_or_404(pid)
    return render_template("product.html", product=product)

@app.route("/quick-pay/<int:pid>")
def quick_pay(pid):
    method = request.args.get("method")
    if "username" not in session:
        session["show_login"] = True
        session["next"] = f"/quick-pay/{pid}?method={method}"
        return redirect(url_for("product_page", pid=pid))
    session["quick_product"] = pid
    session["payment_method"] = method
    return redirect(url_for("payment"))

@app.route("/checkout")
def checkout():
    if "username" not in session:
        session["next"] = url_for("checkout")
        session["show_login"] = True
        return redirect(url_for("home"))
    return render_template("checkout.html")



# ---------- STATIC PAGES ----------
@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/refund")
def refund():
    return render_template("refund.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
