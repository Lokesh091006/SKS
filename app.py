import random,re,time,requests,os
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import razorpay

from flask import Flask, render_template, redirect, session, url_for, request, jsonify
from database import db
from models.product import Product
from models.user import User
from models.address import Address
from models.order import Order
from models.productsize import ProductSize

from sqlalchemy import or_
from functools import wraps
from flask import flash 
from sqlalchemy.orm import joinedload

from dotenv import load_dotenv
load_dotenv()
   


app = Flask(__name__)


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic", "heif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)



client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

database_url = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'shop.db')}")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv("SECRET_KEY", "sks_super_secret_key_123")



def estimate_delivery_days(address):
    city = address.city.lower()
    state = address.state.lower()

    if state == "telangana" or state == "andhra pradesh":
        return "2-3"
    elif state in ["tamil nadu", "karnataka"]:
        return "3-4"
    else:
        return "4-6"

def send_whatsapp_otp(mobile, otp):
    import os, requests

    authkey = os.getenv("MSG91_AUTHKEY")
    if not authkey:
        print("❌ MSG91_AUTHKEY missing")
        return None

    url = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

    payload = {
        "integrated_number": "918897112492",
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": "kalasilks",
                "language": {
                    "code": "en",
                    "policy": "deterministic"
                },
                "namespace": "4141e79d_649d_402a_8391_fbd98e195512",
                "to_and_components": [
                    {
                        "to": ["91" + mobile],
                        "components": {
                            "body_1": {
                                "type": "text",
                                "value": str(otp)
                            },


                            "button_1": {"type": "text",
                                        "sub_type": "url",
                                        "value": str(otp)
                                    }

                            # ✅ REQUIRED because template has URL button
                           
                        }
                    }
                ]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "authkey": authkey
    }

    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print("MSG91 OTP:", r.status_code, r.text)

    return r.text












def send_whatsapp_order_confirmation(mobile, customer_name, order_id, amount, delivery_days, city):
    import os, requests

    authkey = os.getenv("MSG91_AUTHKEY")

    url = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

    payload = {
        "integrated_number": "918897112492",
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": "order_confirm_kalasilks_01",
                "language": {
                    "code": "en",
                    "policy": "deterministic"
                },
                "namespace": "4141e79d_649d_402a_8391_fbd98e195512",
                "to_and_components": [
                    {
                        "to": ["91" + mobile],
                        "components": {
                            "body_1": {"type": "text", "value": customer_name},
                            "body_2": {"type": "text", "value": order_id},
                            "body_3": {"type": "text", "value": str(amount)},
                            "body_4": {"type": "text", "value": delivery_days},
                            "body_5": {"type": "text", "value": city},

                             

                           
                        }
                    }
                ]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "authkey": authkey
    }

    r = requests.post(url, json=payload, headers=headers, timeout=15)
    print("MSG91 ORDER:", r.status_code, r.text)










def send_email_msg91(to_email, subject, html_body):
    import os
    import requests

    authkey = os.getenv("MSG91_AUTHKEY")

    url = "https://control.msg91.com/api/v5/email/send"

    headers = {
        "authkey": authkey,
        "Content-Type": "application/json"
    }

    payload = {
        "to": [
            {
                "email": to_email
            }
        ],
        "from": {
            "name": "Sri Kala Silks",
            "email": "support@kalasilks.com"
        },
        "subject": subject,
        "body": {
            "type": "text/html",
            "data": html_body
        }
    }

    r = requests.post(url, json=payload, headers=headers, timeout=20)
    print("EMAIL STATUS:", r.status_code, r.text)
    return r.text
def send_welcome_email(user):
    import os
    import requests

    authkey = os.getenv("MSG91_AUTHKEY")

    url = "https://control.msg91.com/api/v5/email/send"

    headers = {
        "authkey": authkey,
        "Content-Type": "application/json"
    }

    payload = {
        "to": [
            {
                "email": user.email,
                "name": user.username or "Customer"
            }
        ],
        "from": {
            "name": "Sri Kala Silks",
            "email": "support@kalasilks.com"
        },
        "template_id": "welcome_kalasilks",
        "variables": {
            "name": user.username or "Customer"
        }
    }

    r = requests.post(url, json=payload, headers=headers, timeout=20)
    print("EMAIL STATUS:", r.status_code, r.text)
    return r.text



def send_order_email(user, order_id, amount, address_html, items_html, orders_link):
    import os
    import requests

    authkey = os.getenv("MSG91_AUTHKEY")

    url = "https://control.msg91.com/api/v5/email/send"

    headers = {
        "authkey": authkey,
        "Content-Type": "application/json"
    }

    payload = {
        "to": [
            {
                "email": user.email,
                "name": user.username or "Customer"
            }
        ],
        "from": {
            "name": "Sri Kala Silks",
            "email": "support@kalasilks.com"
        },
        "template_id": "kalasilks_order_confirmation",
        "variables": {
            "name": user.username or "Customer",
            "order_id": order_id,
            "amount": str(amount),
            "address_html": address_html,
            "items_html": items_html,
            "orders_link": orders_link
        }
    }

    r = requests.post(url, json=payload, headers=headers, timeout=20)
    print("ORDER EMAIL STATUS:", r.status_code, r.text)
    return r.text



print("DATABASE_URL USED:", app.config["SQLALCHEMY_DATABASE_URI"])


def get_shiprocket_token():
    url = "https://apiv2.shiprocket.in/v1/external/auth/login"

    email = os.getenv("SHIPROCKET_EMAIL", "").strip()
    password = os.getenv("SHIPROCKET_PASSWORD", "").strip()

    print("DEBUG SHIPROCKET EMAIL RAW:", repr(email))
    print("DEBUG SHIPROCKET PASSWORD LEN:", len(password))

    payload = {
        "email": email,
        "password": password
    }

    try:
        r = requests.post(url, json=payload, timeout=20)
        print("SHIPROCKET AUTH:", r.status_code, r.text)
    except Exception as e:
        print("SHIPROCKET AUTH REQUEST ERROR:", e)
        return None

    if r.status_code not in (200, 201):
        return None

    try:
        data = r.json()
    except Exception as e:
        print("SHIPROCKET AUTH JSON ERROR:", e)
        return None

    return data.get("token")

def build_cart_items_from_session(cart):
    cart_items = []

    for key, item in cart.items():

        if "_" in key:
            pid, size = key.split("_", 1)
        else:
            pid = key
            size = None

        product = Product.query.filter_by(id=int(pid), is_active=True).first()
        if not product:
            continue

        if isinstance(item, dict):
            qty = item.get("qty", 1)
        else:
            qty = item

        cart_items.append({
            "product": product,
            "qty": qty,
            "size": size
        })

    return cart_items

def create_shiprocket_order(main_order_id, user, address, cart_items, payment_method, total_amount):
    token = get_shiprocket_token()
    if not token:
        return {"ok": False, "error": "Shiprocket token generation failed"}

    print("DEBUG PICKUP LOCATION:", repr(os.getenv("SHIPROCKET_PICKUP_LOCATION", "Home").strip()))
    print("DEBUG CUSTOMER EMAIL:", repr(address.email or user.email or "support@kalasilks.com"))
    print("DEBUG CUSTOMER PHONE:", repr(address.mobile or user.mobile or ""))

    url = "https://apiv2.shiprocket.in/v1/external/orders/create/adhoc"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    order_items = []
    for item in cart_items:
        product = item["product"]
        qty = item["qty"]
        size = item.get("size") or ""
        price = float(product.price or 0)

        order_items.append({
            "name": product.name,
            "sku": f"{product.id}-{size}" if size else str(product.id),
            "units": qty,
            "selling_price": price,
            "discount": 0,
            "tax": 0,
            "hsn": ""
        })

    payment_mode = "Prepaid" if payment_method == "razorpay" else "COD"

    payload = {
        "order_id": str(main_order_id),
        "order_date": time.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": os.getenv("SHIPROCKET_PICKUP_LOCATION", "Home").strip(),
        "channel_id": os.getenv("SHIPROCKET_CHANNEL_ID", "").strip(),
        "comment": "Order from KalaSilks website",
        "billing_customer_name": address.name or (user.username or "Customer"),
        "billing_last_name": "",
        "billing_address": (address.house or "").strip(),
        "billing_address_2": (address.street or "").strip(),
        "billing_city": (address.city or "").strip(),
        "billing_pincode": str(address.pincode or "").strip(),
        "billing_state": (address.state or "").strip(),
        "billing_country": "India",
        "billing_email": (address.email or user.email or "support@kalasilks.com").strip(),
        "billing_phone": str(address.mobile or user.mobile or "").strip(),
        "shipping_is_billing": True,
        "order_items": order_items,
        "payment_method": payment_mode,
        "sub_total": float(total_amount),
        "length": float(os.getenv("SHIPROCKET_DEFAULT_LENGTH", 10)),
        "breadth": float(os.getenv("SHIPROCKET_DEFAULT_BREADTH", 10)),
        "height": float(os.getenv("SHIPROCKET_DEFAULT_HEIGHT", 5)),
        "weight": float(os.getenv("SHIPROCKET_DEFAULT_WEIGHT", 0.5))
    }

    print("DEBUG SHIPROCKET PAYLOAD:", payload)

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        print("SHIPROCKET CREATE ORDER:", r.status_code, r.text)
    except Exception as e:
        print("SHIPROCKET CREATE REQUEST ERROR:", e)
        return {"ok": False, "error": str(e)}

    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code not in (200, 201):
        return {"ok": False, "error": data}

    return {"ok": True, "data": data}




db.init_app(app)

def update_product_visibility(product_id):
    sizes = ProductSize.query.filter_by(product_id=product_id).all()
    total_stock = sum((s.stock or 0) for s in sizes)

    product = Product.query.get(product_id)
    if product:
        product.is_active = total_stock > 0

@app.template_filter("imgsrc")
def imgsrc(path):
    if not path:
        return url_for("static", filename="images/placeholder.png")
    if str(path).startswith("http"):
        return path
    return url_for("static", filename=path)

FAST2SMS_API_KEY = "U41D0zVLyOfXbVbR1yI95pqxKvcqrgNIo38ZNJ7e01O7wVn6tjAm8p4nSnNa"

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





from flask import request, render_template

@app.route("/", methods=["GET"])
def home():
    query = request.args.get("q")
    page = "home"

    if query:
        words = query.lower().split()
        products_query = Product.query.filter_by(is_active=True)

        for w in words:
            base = w.rstrip("s")
            products_query = products_query.filter(
                Product.name.ilike(f"%{base}%")
            )

        
        products = products_query.all()

        # 🔥 SMART CATEGORY DETECTION
        if products:
            first_product_name = products[0].name.lower()

            if "men" in first_product_name:
                page = "men"
            elif "women" in first_product_name:
                page = "women"
            elif "kids" in first_product_name:
                page = "kids"
            else:
                page = "home"

    
    else:


        products = Product.query.filter_by(is_active=True).all()

    return render_template(
        "home.html",
        products=products,
        query=query,
        page=page
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile")

        user = User.query.filter_by(mobile=mobile).first()

        if not user:
            user = User(mobile=mobile, role="user")
            db.session.add(user)
            db.session.commit()

            # send welcome email
            if user.email:
                send_welcome_email(user)

        session["user_id"] = user.id
        session["role"] = user.role

        return redirect("/")

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
    if "user_id" not in session:
        session["show_login"] = True
        return redirect(url_for("home"))

    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("home"))

    return render_template("profile.html", user=user)





import time, re, random
from werkzeug.security import generate_password_hash, check_password_hash

OTP_TTL = 300  # 5 minutes

@app.route("/send-otp", methods=["POST"])
def send_otp():
    mobile = request.form.get("mobile", "").strip()

    if not mobile or not re.fullmatch(r"\d{10}", mobile):
        return "Invalid mobile number"

    otp = str(random.randint(100000, 999999))

    # ✅ store hash + expiry (not plain otp)
    session["login_otp_hash"] = generate_password_hash(otp)
    session["login_mobile"] = mobile
    session["login_otp_exp"] = int(time.time()) + OTP_TTL
    session["otp_last_sent"] = int(time.time())

    # ✅ WhatsApp send (for now keep your function name)
    send_whatsapp_otp(mobile, otp)   # <-- replace send_sms_otp with this

    print("DEBUG OTP:", otp)
    return redirect(url_for("verify_otp"))


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        entered = request.form.get("otp", "").strip()

        otp_hash = session.get("login_otp_hash")
        mobile = session.get("login_mobile")
        exp = session.get("login_otp_exp")

        if not otp_hash or not mobile or not exp:
            return redirect("/")

        # ✅ expiry check
        if int(time.time()) > int(exp):
            session.pop("login_otp_hash", None)
            session.pop("login_otp_exp", None)
            return "⌛ OTP expired. Please try again."

        # ✅ hash verify
        if not check_password_hash(otp_hash, entered):
            return "❌ Wrong OTP"

        # ✅ success: clear otp data
        session.pop("login_otp_hash", None)
        session.pop("login_otp_exp", None)
        


        user = User.query.filter_by(mobile=mobile).first()
        if not user:
            return redirect(url_for("set_username"))


        if not user.username or not user.email:


            return redirect(url_for("set_username"))

        session["username"] = user.username
        session["user_id"] = user.id
        session["role"] = user.role

        session.pop("show_login", None)
        next_page = session.pop("next", url_for("home"))
        return redirect(next_page)
    
    
    exp = session.get("login_otp_exp")
    return render_template("verify_otp.html", otp_exp=exp)


RESEND_COOLDOWN = 30  # seconds

@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    mobile = session.get("login_mobile")
       
    exp = session.get("login_otp_exp")

    if not mobile or not exp:
        return redirect(url_for("login"))

    now = int(time.time())

    # ✅ time ayye varaku resend block
    if now < int(exp):
        wait_more = int(exp) - now
        # same verify page ki back pampu (simple message)
        return f"OTP still valid. Wait {wait_more} seconds and try resend."

    # ✅ expired -> new OTP generate
    otp = str(random.randint(100000, 999999))
    session["login_otp_hash"] = generate_password_hash(otp)
    session["login_otp_exp"] = now + OTP_TTL

    send_whatsapp_otp(mobile, otp)
    print("RESEND OTP:", otp)

    return redirect(url_for("verify_otp"))

@app.route("/set-username", methods=["GET", "POST"])
def set_username():
    mobile = session.get("login_mobile")
    if not mobile:
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()

        if not username:
            return render_template("set_username.html", error="Username required")

        if not email:
            return render_template("set_username.html", error="Email required")

        # email already used by another user check
        existing_email_user = User.query.filter_by(email=email).first()
        existing_mobile_user = User.query.filter_by(mobile=mobile).first()

        if existing_email_user and (not existing_mobile_user or existing_email_user.id != existing_mobile_user.id):
            return render_template("set_username.html", error="Email already exists")

        # ✅ mobile already unte update cheyyi
        if existing_mobile_user:
            existing_mobile_user.username = username
            existing_mobile_user.email = email

            # role empty unte set cheyyi
            if not existing_mobile_user.role:
                existing_mobile_user.role = "customer"

            db.session.commit()
            user = existing_mobile_user

        # ✅ mobile lekapothe new user create cheyyi
        else:
            user = User(
                mobile=mobile,
                username=username,
                email=email,
                role="customer"
            )
            db.session.add(user)
            db.session.commit()

        session["username"] = user.username
        session["user_id"] = user.id
        session["role"] = user.role

        session.pop("login_mobile", None)
        print("DEBUG USER EMAIL:", user.email)
        print("DEBUG WELCOME MAIL TRY START") 
        # ✅ welcome email
        try:
            if user.email:
                send_welcome_email(user)
        except Exception as e:
            print("Welcome email failed:", e)

        return redirect(url_for("home"))

    return render_template("set_username.html")


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        session["show_login"] = True
        return redirect(url_for("home"))

    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("home"))

    if request.method == "POST":
        user.username = request.form.get("username")
        user.email = request.form.get("email")
        user.mobile = request.form.get("mobile")
        db.session.commit()

        # session update
        session["username"] = user.username
        session["email"] = user.email
        session["mobile"] = user.mobile

        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=user)


@app.route("/wishlist")
def wishlist():
    wishlist_ids = session.get("wishlist", [])
    wishlist_products = [p for p in Product.query.filter_by(is_active=True).all() if p.id in wishlist_ids]
    return render_template("wishlist.html", products=wishlist_products)


@app.route("/add-to-wishlist/<int:product_id>")
def add_to_wishlist(product_id):
    if "wishlist" not in session:
        session["wishlist"] = []

    if product_id not in session["wishlist"]:
        session["wishlist"].append(product_id)
        session.modified = True
        return jsonify({"status": "added"})
    else:
        session["wishlist"].remove(product_id)
        session.modified = True
        return jsonify({"status": "removed"})


@app.route("/wishlist/remove/<int:product_id>")
def remove_from_wishlist(product_id):
    if "wishlist" in session and product_id in session["wishlist"]:
        session["wishlist"].remove(product_id)
        session.modified = True
    return redirect(url_for("wishlist"))


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

    from sqlalchemy.orm import joinedload

    orders = Order.query.options(
        joinedload(Order.product),
        joinedload(Order.address)
    ).filter_by(
        user_id=session["user_id"]
    ).order_by(
        Order.id.desc()
    ).all()

    print("ORDERS:", orders)

    return render_template("my_orders.html", orders=orders)


@app.route("/category/<name>")
def category(name):
    q = request.args.get("q")
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color")
    type_ = request.args.get("type")
    brand = request.args.get("brand")
    sort = request.args.get("sort")
    sub = request.args.get("sub")

    # ✅ exact category match
    query = Product.query.filter_by(is_active=True).filter(Product.category.ilike(name))

    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))

    if type_:
        query = query.filter(Product.type.ilike(type_))

    if brand:
        query = query.filter(Product.brand.ilike(brand))

    if sub:
        query = query.filter(Product.sub.ilike(sub))

    if color:
        query = query.filter(Product.color.ilike(color))

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

    return render_template("shop.html", products=products, page=name)





from sqlalchemy import and_

@app.route("/search")
def search():
    q = request.args.get("q", "").strip().lower()

    products = Product.query.filter_by(is_active=True)

    if q:
        words = q.replace("-", " ").split()

        category = None
        product_type = None

        if "men" in words:
            category = "men"
        if "women" in words:
            category = "women"

        # last word = main product
        product_type = words[-1].rstrip("s")

        if category:
            products = products.filter(
                and_(
                    Product.category.ilike(f"%{category}%"),
                    Product.type.ilike(f"%{product_type}%")
                )
            )
        else:
            products = products.filter(
                Product.type.ilike(f"%{product_type}%")
            )

    results = products.all()

    return render_template("search.html", products=results, query=q)


@app.route("/live-search")
def live_search():

    q = request.args.get("q", "").strip()

    if not q:
        return jsonify([])

    words = q.lower().split()

    products = Product.query.filter_by(is_active=True)

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

    for key, item in cart.items():
        # ⚡ split key into product_id and size if needed
        if "_" in key:
            pid, size = key.split("_")
        else:
            pid = key
            # old items without size
            if isinstance(item, dict):
                size = item.get("size", "M")
            else:
                size = "M"

        product = Product.query.filter_by(id=int(pid), is_active=True).first()
        if not product:
            continue

        # qty
        if isinstance(item, dict):
            qty = item.get("qty", 1)
        else:
            qty = item

        subtotal = product.price * qty
        total += subtotal

        cart_items.append({
            "product": product,
            "qty": qty,
            "size": size,
            "subtotal": subtotal
        })

    # discount logic
    discount = 0
    if total > 3000:
        discount = 600
    elif total > 2000:
        discount = 300
    elif total > 1000:
        discount = 100

    final_amount = total - discount
    session["total_after_coupon"] = final_amount

    return render_template("cart.html",
                           cart_items=cart_items,
                           total=total,
                           discount=discount,
                           final_amount=final_amount)


@app.route("/clear")
def clear_cart():
    session.pop("cart", None)
    return "Cart Cleared ✅"



 # for showing messages

@app.route("/add/<int:product_id>")
def add_to_cart(product_id):

    cart = session.get("cart", {})
    pid = str(product_id)

    size = request.args.get("size")
    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:


        flash("This product is unavailable ❌", "error")
        return redirect(request.referrer or "/")

    # ❌ size lekapothe block
    if not size:
        flash("Please select a size before adding to cart!", "error")
        return redirect(request.referrer or "/")

    # 🔥 STEP 9 START (STOCK CHECK)
    size_item = ProductSize.query.filter_by(
        product_id=product_id,
        size=size
    ).first()

    if not size_item or size_item.stock <= 0:
        flash("Out of stock ❌", "error")
        return redirect(request.referrer or "/")
    # 🔥 STEP 9 END

    # cart key
    cart_key = f"{pid}_{size}"

    # already exists
    if cart_key in cart:

        # 🔥 check if adding exceeds stock
        if cart[cart_key]["qty"] >= size_item.stock:
            flash("Maximum stock reached ⚠️", "error")
            return redirect(request.referrer or "/")

        cart[cart_key]["qty"] += 1

    else:
        cart[cart_key] = {"qty": 1, "size": size}

    session["cart"] = cart

    flash("Product added to cart ✅", "success")
    return redirect(url_for("cart"))




@app.route("/increase/<int:product_id>/<size>")
def increase(product_id, size):
    cart = session.get("cart", {})
    key = f"{product_id}_{size}"

    if key in cart:
        cart[key]["qty"] += 1

    session["cart"] = cart
    return redirect(url_for("cart"))


@app.route("/decrease/<int:product_id>/<size>")
def decrease(product_id, size):
    cart = session.get("cart", {})
    key = f"{product_id}_{size}"

    if key in cart:
        if cart[key]["qty"] > 1:
            cart[key]["qty"] -= 1
        else:
            del cart[key]

    session["cart"] = cart
    return redirect(url_for("cart"))


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
        pincode = (request.form.get("pincode") or "").strip()

        # ✅ Indian pincode format check (6 digits)
        if not PIN_RE.match(pincode):
            return "Invalid Indian Pincode ❌ (6 digits)", 400

        addr = Address(
            user_id=session["user_id"],
            name=request.form.get("name"),
            mobile=request.form.get("mobile"),
            email=request.form.get("email"),   # email optional
            house=request.form.get("house"),
            street=request.form.get("street"),
            city=request.form.get("city"),
            state=request.form.get("state"),
            pincode=pincode
        )
        db.session.add(addr)
        db.session.commit()
        return redirect(url_for("address"))

    return render_template("add_address.html")

@app.route("/delete-address/<int:id>")
def delete_address(id):
    if "user_id" not in session:
        return redirect(url_for("home"))

    # 🔒 Only delete if address belongs to logged-in user
    addr = Address.query.filter_by(
        id=id,
        user_id=session["user_id"]
    ).first()

    if addr:
        db.session.delete(addr)
        db.session.commit()

    return redirect(url_for("address"))








PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}

@app.route("/api/pincode/<pin>")
def api_pincode(pin):
    pin = (pin or "").strip()

    if not PIN_RE.match(pin):
        return jsonify({"ok": False, "error": "Invalid pincode"}), 400

    url = f"https://api.postalpincode.in/pincode/{pin}"

    last_err = None
    for attempt in range(1, 4):  # ✅ 3 retries
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()

            if data and data[0].get("Status") == "Success":
                post_offices = data[0].get("PostOffice") or []
                first = post_offices[0] if post_offices else {}

                return jsonify({
                    "ok": True,
                    "city": first.get("District", ""),
                    "state": first.get("State", ""),
                    "post_offices": [po.get("Name", "") for po in post_offices]
                })

            return jsonify({"ok": False, "error": "Pincode not found"}), 404

        except requests.exceptions.RequestException as e:
            last_err = e
            # small delay before retry
            time.sleep(0.4 * attempt)

    print("PINCODE ROUTE ERROR (after retries):", repr(last_err))
    return jsonify({"ok": False, "error": "Pincode provider unstable, try again"}), 503




def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect("/login")

            if session.get("role") != role:
                return "❌ Access Denied"

            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/make-admin")
def make_admin():

    user1 = User.query.filter_by(mobile="7993412492").first()
    user2 = User.query.filter_by(mobile="9985212492").first()

    if user1:
        user1.role = "admin"

    if user2:
        user2.role = "admin"

    db.session.commit()

    return "Admins created ✅"



@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_users = User.query.count()

    return render_template(
        "admin/dashboard.html",
        total_products=total_products,
        total_orders=total_orders,
        total_users=total_users
)


@app.route("/admin/add-product", methods=["GET", "POST"])
@role_required("admin")
def add_product():
    try:
        if request.method == "POST":

            # ===== FORM DATA =====
            name = request.form["name"]
            price = request.form["price"]
            category = request.form["category"]
            sizes = request.form.get("sizes")
            stocks = request.form.get("stocks")
            type_ = request.form.get("type")
            brand = request.form.get("brand")
            description = request.form.get("description")

            img1 = request.files.get("image1")
            img2 = request.files.get("image2")
            img3 = request.files.get("image3")

            print("IMG1 NAME:", img1.filename if img1 else "NO FILE")
            print("IMG2 NAME:", img2.filename if img2 else "NO FILE")
            print("IMG3 NAME:", img3.filename if img3 else "NO FILE")

            # ===== IMAGE 1 (Required) =====
            img1_path = None
            if img1 and img1.filename != "":
                upload_result1 = cloudinary.uploader.upload(
                    img1,
                    folder="kalasilks/products",
                    resource_type="image"
                )
                print("UPLOAD RESULT 1:", upload_result1)

                public_id1 = upload_result1["public_id"]

                img1_path = cloudinary.CloudinaryImage(public_id1).build_url(
                    secure=True,
                    format="jpg"
                )

                print("FINAL IMG1 URL:", img1_path)

            # ===== IMAGE 2 (Optional) =====
            img2_path = None
            if img2 and img2.filename != "":
                upload_result2 = cloudinary.uploader.upload(
                    img2,
                    folder="kalasilks/products",
                    resource_type="image"
                )
                print("UPLOAD RESULT 2:", upload_result2)

                public_id2 = upload_result2["public_id"]

                img2_path = cloudinary.CloudinaryImage(public_id2).build_url(
                    secure=True,
                    format="jpg"
                )

                print("FINAL IMG2 URL:", img2_path)

            # ===== IMAGE 3 (Optional) =====
            img3_path = None
            if img3 and img3.filename != "":
                upload_result3 = cloudinary.uploader.upload(
                    img3,
                    folder="kalasilks/products",
                    resource_type="image"
                )
                print("UPLOAD RESULT 3:", upload_result3)

                public_id3 = upload_result3["public_id"]

                img3_path = cloudinary.CloudinaryImage(public_id3).build_url(
                    secure=True,
                    format="jpg"
                )

                print("FINAL IMG3 URL:", img3_path)

            # ===== SAVE PRODUCT =====
            new_product = Product(
                name=name,
                price=price,
                category=category,
                sizes=sizes,
                type=type_,
                brand=brand,
                description=description,
                image=img1_path,
                image2=img2_path,
                image3=img3_path
            )

            db.session.add(new_product)
            db.session.commit()

            # ===== SAVE SIZES WITH STOCK =====
            if sizes and stocks:
                size_list = sizes.split(",")
                stock_list = stocks.split(",")

                if len(size_list) != len(stock_list):
                    return "Sizes and Stocks count mismatch ❌"

                for i in range(len(size_list)):
                    ps = ProductSize(
                        product_id=new_product.id,
                        size=size_list[i].strip(),
                        stock=int(stock_list[i].strip())
                    )
                    db.session.add(ps)

                db.session.commit()
                update_product_visibility(new_product.id)
                db.session.commit()

            return redirect("/admin/dashboard")

        return render_template("admin/add_product.html")

    except Exception as e:
        print("ADD PRODUCT ERROR:", e)
        return f"Add Product Error: {e}"


@app.route("/admin/products")
@role_required("admin")
def manage_products():
    products = Product.query.all()
    return render_template("admin/manage_products.html", products=products)

@app.route("/admin/delete-product/<int:id>", methods=["POST"])
@role_required("admin")
def delete_product(id):
    try:
        product = Product.query.get_or_404(id)

        # first delete all size-stock rows
        ProductSize.query.filter_by(product_id=product.id).delete()

        # then delete main product
        db.session.delete(product)
        db.session.commit()

        flash("Product deleted successfully ✅", "success")

    except Exception as e:
        db.session.rollback()
        print("DELETE PRODUCT ERROR:", e)
        flash(f"Error deleting product: {str(e)}", "danger")

    return redirect("/admin/products")

@app.route("/admin/edit-product/<int:id>", methods=["GET", "POST"])
@role_required("admin")
def edit_product(id):
    product = Product.query.get_or_404(id)
    size_rows = ProductSize.query.filter_by(product_id=id).all()

    if request.method == "POST":
        sizes = product.sizes or ""
        stocks = request.form.get("stocks", "").strip()

        size_list = [s.strip() for s in sizes.split(",") if s.strip()]
        stock_list = [s.strip() for s in stocks.split(",") if s.strip()]

        if len(size_list) != len(stock_list):
            flash("Stocks count should match sizes count ❌", "danger")
            return redirect(url_for("edit_product", id=id))

        ProductSize.query.filter_by(product_id=id).delete()

        for i in range(len(size_list)):
            ps = ProductSize(
                product_id=product.id,
                size=size_list[i],
                stock=int(stock_list[i] or 0)
            )
            db.session.add(ps)

        update_product_visibility(product.id)
        db.session.commit()

        flash("Stock updated successfully ✅", "success")
        return redirect(url_for("manage_products"))

    sizes_text = ",".join([s.size for s in size_rows])
    stocks_text = ",".join([str(s.stock or 0) for s in size_rows])

    return render_template(
        "admin/edit_product.html",
        product=product,
        sizes_text=sizes_text,
        stocks_text=stocks_text
    )
    

@app.route("/admin/orders")
@role_required("admin")
def admin_orders():
    orders = Order.query.options(
        joinedload(Order.product),
        joinedload(Order.address)
    ).order_by(Order.id.desc()).all()

    print("ADMIN ORDERS:", orders)

    return render_template("admin/orders.html", orders=orders)



@app.route("/payment", methods=["GET", "POST"])
def payment():
    total_after_coupon = session.get("total_after_coupon") or 0

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        method = request.form.get("method")

        if method == "cod":
            session["payment_method"] = "cod"
            session["final_amount"] = total_after_coupon + 30
            return redirect(url_for("payment_success"))

        elif method == "online":
            session["payment_method"] = "razorpay"
            session["final_amount"] = total_after_coupon
            return redirect(url_for("razorpay_checkout"))

    return render_template("payment.html", total_after_coupon=total_after_coupon)

@app.route("/tracking-webhook", methods=["POST"])
def tracking_webhook():
    data = request.get_json(silent=True)
    print("WEBHOOK DATA:", data)

    try:
        if not data:
            return "OK", 200

        order_id = data.get("order_id")
        status = data.get("current_status")
        awb = data.get("awb")
        courier = data.get("courier_name")

        order = Order.query.filter_by(order_id=order_id).first()

        if not order:
            print("ORDER NOT FOUND:", order_id)
            return "OK", 200

        # ✅ CORRECT FIELD NAMES
        order.awb_code = awb
        order.courier_name = courier

        # status update
        status_upper = status.upper()

        if "DELIVERED" in status_upper:
            order.status = "DELIVERED"
        elif "OUT FOR DELIVERY" in status_upper:
            order.status = "OUT FOR DELIVERY"
        elif "SHIPPED" in status_upper or "IN TRANSIT" in status_upper:
            order.status = "SHIPPED"
        elif "CANCELLED" in status_upper:
            order.status = "CANCELLED"
        elif "PICKUP" in status_upper:
            order.status = "PICKUP PENDING"

        db.session.commit()
        print("UPDATED:", order.order_id, order.status)

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return "OK", 200

@app.route("/razorpay-checkout")
def razorpay_checkout():
    if "user_id" not in session:
        return redirect("/login")

    amount = session.get("final_amount")
    address_id = session.get("address")

    if not amount:
        return redirect("/cart")

    if not address_id:
        return redirect("/address")

    amount_paise = int(float(amount) * 100)

    razorpay_order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1
    })

    session["razorpay_order_id"] = razorpay_order["id"]

    user = User.query.get(session["user_id"])

    return render_template(
        "razorpay_checkout.html",
        razorpay_key=os.getenv("RAZORPAY_KEY_ID"),
        amount=amount_paise,
        order_id=razorpay_order["id"],
        user=user
    )

@app.route("/razorpay-verify", methods=["POST"])
def razorpay_verify():
    if "user_id" not in session:
        return redirect("/login")

    razorpay_payment_id = request.form.get("razorpay_payment_id")
    razorpay_order_id = request.form.get("razorpay_order_id")
    razorpay_signature = request.form.get("razorpay_signature")

    try:
        client.utility.verify_payment_signature({
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_signature": razorpay_signature
        })

        payment = client.payment.fetch(razorpay_payment_id)
        print("RAZORPAY PAYMENT FETCH:", payment)

        if payment.get("status") != "captured":
            return "Payment not captured yet ❌", 400

        session["payment_method"] = "razorpay"
        session["razorpay_payment_id"] = razorpay_payment_id

        return redirect(url_for("payment_success"))

    except Exception as e:
        print("RAZORPAY VERIFY ERROR:", e)
        return "Payment verification failed ❌", 400


@app.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    payload = request.data
    signature = request.headers.get("X-Razorpay-Signature")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    try:
        client.utility.verify_webhook_signature(
            payload.decode("utf-8"),
            signature,
            secret
        )
    except Exception as e:
        print("Webhook verify failed:", e)
        return "Invalid webhook", 400

    data = request.json
    event = data.get("event")
    print("RAZORPAY WEBHOOK EVENT:", event)

    # later idhi use chesi backup shipment creation cheyyachu
    return "OK", 200

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

from sqlalchemy.orm import joinedload

from urllib.parse import quote
@app.route("/payment-success")
def payment_success():
    if "user_id" not in session:
        return redirect("/login")

    cart = session.get("cart", {})
    address_id = session.get("address")
    payment_method = session.get("payment_method")

    if not cart:
        return redirect("/cart")

    if not address_id or not payment_method:
        return redirect("/checkout")

    created_ids = []
    cart_items = build_cart_items_from_session(cart)

    # 1) STOCK CHECK + ORDER CREATE
    for item in cart_items:
        product = item["product"]
        qty = item["qty"]
        size = item["size"]

        if size:
            size_obj = ProductSize.query.filter_by(
                product_id=product.id,
                size=size
            ).first()

            if not size_obj or size_obj.stock < qty:
                flash(f"{size} size is out of stock ❌", "error")
                return redirect("/cart")

            size_obj.stock -= qty
            update_product_visibility(product.id)

        for _ in range(qty):
            order = Order(
                order_id="SKS" + str(int(time.time() * 1000)) + str(random.randint(10, 99)),
                user_id=session["user_id"],
                product_id=product.id,
                address_id=address_id,
                payment_method=payment_method,
                status="PLACED",
                size=size,
                payment_id=session.get("razorpay_payment_id")
            )
            db.session.add(order)
            db.session.flush()
            created_ids.append(order.id)
            time.sleep(0.001)  # unique order_id kosam tiny delay

    db.session.commit()

    orders = Order.query.options(
        joinedload(Order.product),
        joinedload(Order.address)
    ).filter(Order.id.in_(created_ids)).all()

    final_amount = session.get("final_amount") or session.get("total_after_coupon", 0)

    # 2) SHIPROCKET CREATE
    try:
        user = User.query.get(session["user_id"])
        address = Address.query.get(address_id)

        # One grouped order id for Shiprocket
        master_order_id = orders[0].order_id if orders else "SKSORDER"

        sr_result = create_shiprocket_order(
            main_order_id=master_order_id,
            user=user,
            address=address,
            cart_items=cart_items,
            payment_method=payment_method,
            total_amount=final_amount
        )

        if sr_result["ok"]:
            sr_data = sr_result["data"]

            shiprocket_order_id = sr_data.get("order_id")
            shipment_id = sr_data.get("shipment_id")
            status_text = sr_data.get("status") or "CREATED"

            for o in orders:
                o.shiprocket_order_id = str(shiprocket_order_id or "")
                o.shiprocket_shipment_id = str(shipment_id or "")
                o.shiprocket_status = status_text

            db.session.commit()
        else:
            print("Shiprocket create failed:", sr_result["error"])

    except Exception as e:
        print("Shiprocket integration failed:", e)

    # 3) EMAIL / WHATSAPP
    try:
        user = User.query.get(session["user_id"])
        address = Address.query.get(address_id)

        customer_name = user.username or "Customer"
        customer_mobile = user.mobile or ""
        city = (address.city or "").strip() if address else ""
        delivery_days = "2-3"
        order_no = orders[0].order_id if orders else "SKSORDER"

        address_html = ""
        if address:
            address_html = f"""
            <div>
                <b>{address.name or customer_name}</b><br>
                {address.mobile or customer_mobile}<br>
                {address.house or ""}<br>
                {address.street or ""}<br>
                {address.city or ""}, {address.state or ""} - {address.pincode or ""}
            </div>
            """

        items_html = ""
        for o in orders:
            product_name = o.product.name if o.product else "Product"
            product_price = getattr(o.product, "price", 0) if o.product else 0

            product_image_url = "https://www.kalasilks.com/static/images/placeholder.png"
            if o.product and o.product.image:
                img = o.product.image.strip()
                encoded_img = quote(img)

                if img.startswith(("http://", "https://")):
                    product_image_url = img
                elif img.startswith("static/"):
                    product_image_url = f"https://www.kalasilks.com/{encoded_img}"
                elif img.startswith(("images/", "uploads/")):
                    product_image_url = f"https://www.kalasilks.com/static/{encoded_img}"
                else:
                    product_image_url = f"https://www.kalasilks.com/static/images/{encoded_img}"

            items_html += f"""
            <table style="width:100%; margin-bottom:18px; border-collapse:collapse;">
                <tr>
                    <td style="width:90px; vertical-align:top;">
                        <img src="{product_image_url}" alt="{product_name}" style="width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid #333;">
                    </td>
                    <td style="vertical-align:top;color:#ffffff;font-size:15px;line-height:1.5;">
                        <div style="font-weight:bold;">{product_name}</div>
                        <div style="color:#cccccc;">Size: {o.size or '-'}</div>
                    </td>
                    <td style="text-align:right;vertical-align:top;color:#ffffff;font-weight:bold;font-size:15px;">
                        ₹{product_price}
                    </td>
                </tr>
            </table>
            """

        orders_link = "https://www.kalasilks.com/my-orders"

        if customer_mobile:
            send_whatsapp_order_confirmation(
                customer_mobile,
                customer_name,
                order_no,
                final_amount,
                delivery_days,
                city or "Your City"
            )

        if user and user.email:
            send_order_email(
                user,
                order_no,
                final_amount,
                address_html,
                items_html,
                orders_link
            )

    except Exception as e:
        print("Order WhatsApp/Email send failed:", e)

    # 4) CLEAR SESSION
    session.pop("cart", None)
    session.pop("total_after_coupon", None)
    session.pop("final_amount", None)

    return render_template(
        "payment_success.html",
        orders=orders,
        final_amount=final_amount
    )


    
@app.route("/shop")
def shop():

    q = request.args.get("q")
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color")
    type_ = request.args.get("type")
    category = request.args.get("category")
    sort = request.args.get("sort")
    sub = request.args.get("sub")
    size = request.args.get("size")
    brand = request.args.get("brand")

    query = Product.query.filter_by(is_active=True)

    # 🔍 SEARCH
    if q:
        words = q.lower().split()
        for w in words:
            like = f"%{w.rstrip('s')}%"
            query = query.filter(or_(
                Product.name.ilike(like),
                Product.category.ilike(like),
                Product.type.ilike(like),
                Product.brand.ilike(like)   # 🔥 ADD THIS
            ))

    # 🧥 CATEGORY
    if category:
        query = query.filter(Product.category.ilike(f"%{category.strip()}%"))

    # 👕 TYPE
    if type_:
        query = query.filter(Product.type.ilike(f"%{type_.strip()}%"))

    # 🏷 BRAND (🔥 IMPROVED)
    if brand:
        brand_clean = brand.strip().lower()

        query = query.filter(
            Product.brand.ilike(f"%{brand_clean}%")
        )

    # 🔽 SUB CATEGORY
    if sub:
        query = query.filter(Product.sub.ilike(f"%{sub.strip()}%"))

    # 📏 SIZE
    if size:
        query = query.filter(Product.size == size)

    # 🎨 COLOR
    if color:
        query = query.filter(Product.color.ilike(f"%{color.strip()}%"))

    # 💰 PRICE
    if min_price:
        query = query.filter(Product.price >= int(min_price))

    if max_price:
        query = query.filter(Product.price <= int(max_price))

    # 🔃 SORT
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


@app.route("/product/<int:pid>")
def product_page(pid):
    product = Product.query.filter_by(id=pid, is_active=True).first_or_404()
    sizes = ProductSize.query.filter_by(product_id=pid).all()

    return render_template("product.html", product=product, sizes=sizes)

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
