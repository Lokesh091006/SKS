import random,re,time,requests,os
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import razorpay

from flask import Flask, render_template, redirect, session, url_for, request, jsonify
from database import db
from models.product import Product, TempOrder
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




def send_msg91_whatsapp_template(template_name, mobile, components):
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
                "name": template_name,
                "language": {
                    "code": "en",
                    "policy": "deterministic"
                },
                "namespace": "4141e79d_649d_402a_8391_fbd98e195512",
                "to_and_components": [
                    {
                        "to": ["91" + str(mobile).strip()],
                        "components": components
                    }
                ]
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "authkey": authkey
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=20)
        print(f"MSG91 {template_name}:", r.status_code, r.text)
        return r.text
    except Exception as e:
        print(f"MSG91 {template_name} ERROR:", e)
        return None







def send_whatsapp_order_confirmation(mobile, customer_name, order_id, amount, delivery_address):
    components = {
        "body_1": {"type": "text", "value": customer_name},
        "body_2": {"type": "text", "value": order_id},
        "body_3": {"type": "text", "value": str(amount)},
        "body_4": {"type": "text", "value": delivery_address},
    }

    return send_msg91_whatsapp_template(
        "order_confirm_kalasilks_09",
        mobile,
        components
    )


def send_whatsapp_out_for_delivery(mobile, customer_name, order_id, tracking_url=None):
    components = {
        "body_1": {"type": "text", "value": customer_name},
        "body_2": {"type": "text", "value": order_id},
    }

    if tracking_url:
        components["button_1"] = {
            "type": "text",
            "sub_type": "url",
            "value": tracking_url
        }

    return send_msg91_whatsapp_template(
        "order_ofd_kalasilks",
        mobile,
        components
    )

def send_whatsapp_delivered(mobile, customer_name, order_id):
    components = {
        "body_1": {"type": "text", "value": customer_name},
        "body_2": {"type": "text", "value": order_id},
    }

    return send_msg91_whatsapp_template(
        "order_delivered_kalasilks",
        mobile,
        components
    )


def send_whatsapp_refund(mobile, customer_name, order_id, amount):
    components = {
        "body_1": {"type": "text", "value": customer_name},
        "body_2": {"type": "text", "value": order_id},
        "body_3": {"type": "text", "value": str(amount)},
    }

    return send_msg91_whatsapp_template(
        "order_refund_kalasilks",   # 👈 template name (MSG91 lo create cheyali)
        mobile,
        components
    )









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
            "email": "no-reply@kalasilks.com"
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
            "email": "no-reply@kalasilks.com"
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
            "email": "no-reply@kalasilks.com"
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


from datetime import datetime, timedelta

def process_shiprocket_orders():
    print("Checking pending orders...")

    orders = Order.query.filter(
        Order.status == "PLACED",
        Order.shiprocket_order_id == None
    ).all()

    for order in orders:

        if not order.created_at:
            continue

        time_diff = datetime.now() - order.created_at

        print("Order:", order.order_id)
        print("Time diff:", time_diff)

        # 🔥 12hrs condition
        if time_diff >= timedelta(hours=12):

            try:
                user = User.query.get(order.user_id)
                address = Address.query.get(order.address_id)

                result = create_shiprocket_order(
                    main_order_id=order.order_id,
                    user=user,
                    address=address,
                    cart_items=[{
                        "product": order.product,
                        "qty": 1,
                        "size": order.size
                    }],
                    payment_method=order.payment_method,
                    total_amount=order.product.price if order.product else 0
                )

                print("Shiprocket response:", result)

                if result.get("ok"):
                    data = result.get("data", {})

                    order.shiprocket_order_id = str(data.get("order_id"))
                    order.shiprocket_status = "NEW"
                    order.status = "CONFIRMED"

                    db.session.commit()

                    print("✅ Shiprocket created:", order.order_id)

            except Exception as e:
                print("Shiprocket error:", e)




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






from flask import request, render_template
from sqlalchemy.sql.expression import func
@app.route("/", methods=["GET"])
def home():
    query = request.args.get("q", "").strip()
    page = "home"

    if query:
        words = query.lower().split()
        products_query = Product.query.filter_by(is_active=True)

        # SEARCH in name / category / type / brand
        for w in words:
            base = w.rstrip("s")
            like = f"%{base}%"
            products_query = products_query.filter(or_(
                Product.name.ilike(like),
                Product.category.ilike(like),
                Product.type.ilike(like),
                Product.brand.ilike(like)
            ))

        products = products_query.all()

        q_lower = query.lower()

        if any(x in q_lower for x in ["saree", "kurti", "legging", "chudidar", "nighty", "croptop", "women", "ladies"]):
            page = "women"
        elif any(x in q_lower for x in ["shirt", "tshirt", "jeans", "cottonpants", "men", "gents", "nightwear"]):
            page = "men"
        elif any(x in q_lower for x in ["kids", "boys", "girls", "babywear", "baby"]):
            page = "kids"
        elif products:
            first_category = (products[0].category or "").lower()

            if "women" in first_category:
                page = "women"
            elif "men" in first_category:
                page = "men"
            elif "kids" in first_category:
                page = "kids"
            else:
                page = "home"

    else:
        products = Product.query.filter_by(is_active=True)\
            .order_by(func.random())\
            .limit(20)\
            .all()

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
        session["username"] = user.username

        next_page = session.pop("next", None)
        if next_page:


            return redirect(next_page)

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

        next_page = session.pop("next", None)
        if next_page:



            return redirect(next_page)

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

from datetime import datetime

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

    return render_template(
        "my_orders.html",   # ⚠️ name match chesuko
        orders=orders,
        now=datetime.utcnow()   # 🔥 IMPORTANT
    )

@app.route("/category/<name>")
def category(name):
    q = request.args.get("q", "").strip()
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color", "").strip()
    type_ = request.args.get("type", "").strip()
    brand = request.args.get("brand", "").strip()
    sort = request.args.get("sort", "").strip()
    sub = request.args.get("sub", "").strip()

    name = name.strip().lower()

    query = Product.query.filter_by(is_active=True).filter(
        Product.category.ilike(name)
    )

    if q:
        words = q.lower().split()
        for w in words:
            like = f"%{w.rstrip('s')}%"
            query = query.filter(or_(
                Product.name.ilike(like),
                Product.category.ilike(like),
                Product.type.ilike(like),
                Product.brand.ilike(like)
            ))

    if type_:
        query = query.filter(Product.type.ilike(f"%{type_}%"))

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if sub:
        query = query.filter(Product.sub.ilike(f"%{sub}%"))

    if color:
        query = query.filter(Product.color.ilike(f"%{color}%"))

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

    return render_template(
        "shop.html",
        products=products,
        page=name,
        q=q,
        min_price=min_price,
        max_price=max_price,
        color=color,
        type_=type_,
        brand=brand,
        sort=sort,
        sub=sub
    )


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

    # 🔥 VERY IMPORTANT FIX
    session.pop("buy_now_item", None)

    cart = session.get("cart", {})
    cart_items = []
    total = 0

    for key, item in cart.items():

        # 🔹 split product_id & size
        if "_" in key:
            pid, size = key.split("_", 1)
        else:
            pid = key
            if isinstance(item, dict):
                size = item.get("size")
            else:
                size = None

        # 🔹 product fetch
        product = Product.query.filter_by(id=int(pid), is_active=True).first()
        if not product:
            continue

        # 🔹 quantity
        if isinstance(item, dict):
            qty = item.get("qty", 1)
        else:
            qty = item

        # 🔹 subtotal
        subtotal = product.price * qty
        total += subtotal

        # 🔥 STOCK FETCH
        stock = None

        if size:
            size_obj = ProductSize.query.filter_by(
                product_id=int(pid),
                size=size
            ).first()

            if size_obj:
                stock = size_obj.stock

        # 🔹 append
        cart_items.append({
            "product": product,
            "qty": qty,
            "size": size,
            "subtotal": subtotal,
            "stock": stock
        })

    final_amount = total
    session["total_after_coupon"] = final_amount

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total,
        discount=0,
        final_amount=final_amount
    )

@app.route("/clear")
def clear_cart():
    session.pop("cart", None)
    return "Cart Cleared ✅"



 # for showing messages

@app.route("/add/<int:product_id>")
def add_to_cart(product_id):

    cart = session.get("cart", {})

    size = (request.args.get("size") or "").strip()
    size = size if size else "nosize"

    qty_str = request.args.get("qty")
    qty = int(qty_str) if qty_str and qty_str.isdigit() else 1

    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:
        flash("This product is unavailable ❌", "error")
        return redirect(request.referrer or "/")

    all_sizes = ProductSize.query.filter_by(product_id=product_id).all()
    has_real_sizes = any((s.size or "").strip() for s in all_sizes)

    if has_real_sizes and size == "nosize":
        flash("Please select size ❌", "error")
        return redirect(request.referrer or "/")

    if has_real_sizes:
        size_item = ProductSize.query.filter_by(
            product_id=product_id,
            size=size
        ).first()

        if not size_item or size_item.stock <= 0:
            flash("Out of stock ❌", "error")
            return redirect(request.referrer or "/")

    cart_key = f"{product_id}_{size}"

    if cart_key in cart:
        cart[cart_key]["qty"] += qty
    else:
        cart[cart_key] = {
            "product_id": product_id,   # 🔥 IMPORTANT
            "qty": qty,
            "size": None if size == "nosize" else size
        }

    session["cart"] = cart

    flash("Added to cart ✅", "success")
    return redirect(url_for("cart"))

@app.route("/buy-now/<int:product_id>")
def buy_now(product_id):

    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:
        flash("This product is unavailable ❌", "error")
        return redirect(url_for("home"))

    size = (request.args.get("size") or "").strip()

    # ✅ SAFE QTY FIX
    qty_str = request.args.get("qty")
    if not qty_str or not qty_str.isdigit():
        qty = 1
    else:
        qty = int(qty_str)

    all_sizes = ProductSize.query.filter_by(product_id=product_id).all()
    has_real_sizes = any((s.size or "").strip() for s in all_sizes)

    if has_real_sizes and not size:
        flash("Please select a size first ❌", "error")
        return redirect(url_for("product_page", pid=product_id))

    if has_real_sizes:
        size_obj = ProductSize.query.filter_by(
            product_id=product_id,
            size=size
        ).first()

        if not size_obj or size_obj.stock <= 0:
            flash("Selected size is out of stock ❌", "error")
            return redirect(url_for("product_page", pid=product_id))

        if qty > size_obj.stock:
            flash(f"Only {size_obj.stock} item(s) available for size {size} ⚠️", "error")
            return redirect(url_for("product_page", pid=product_id))

    session["buy_now_item"] = {
        "product_id": product_id,
        "size": size if size else None,
        "qty": qty
    }

    if "user_id" not in session:
        session["next"] = url_for("address")
        flash("Login to proceed", "error")
        return redirect(url_for("login"))

    return redirect(url_for("address"))


@app.route("/increase/<int:product_id>/<size>")
def increase(product_id, size):
    cart = session.get("cart", {})
    key = f"{product_id}_{size}"

    if key not in cart:
        return redirect(url_for("cart"))

    # 🔥 current qty
    current_qty = cart[key]["qty"]

    # 🔥 stock fetch
    size_obj = ProductSize.query.filter_by(
        product_id=product_id,
        size=size
    ).first()

    if not size_obj:
        return redirect(url_for("cart"))

    # 🔥 MAIN LOGIC
    if current_qty >= size_obj.stock:
        flash(f"Only {size_obj.stock} item(s) available ⚠️", "error")
        return redirect(url_for("cart"))

    # ✅ safe to increase
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



# 🔥 NO SIZE - INCREASE
@app.route("/increase/<int:product_id>")
def increase_no_size(product_id):
    cart = session.get("cart", {})
    key = str(product_id)

    if key in cart:
        cart[key]["qty"] += 1

    session["cart"] = cart
    return redirect(url_for("cart"))


# 🔥 NO SIZE - DECREASE
@app.route("/decrease/<int:product_id>")
def decrease_no_size(product_id):
    cart = session.get("cart", {})
    key = str(product_id)

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
        session["next"] = url_for("address")
        flash("Login to proceed", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    buy_now_item = session.get("buy_now_item")
    cart = session.get("cart", {})

    if request.method == "POST":
        addr = Address.query.get(request.form["address_id"])
        if not addr or addr.user_id != user_id:
            flash("Invalid address selected ❌", "error")
            return redirect(url_for("address"))

        session["address"] = addr.id
        return redirect(url_for("payment"))

    addresses = Address.query.filter_by(user_id=user_id).all()

    # BUY NOW FLOW
    if buy_now_item:
        product = Product.query.filter_by(
            id=buy_now_item["product_id"],
            is_active=True
        ).first()

        if not product:
            session.pop("buy_now_item", None)
            flash("Product not found ❌", "error")
            return redirect(url_for("home"))

        qty = int(buy_now_item.get("qty", 1))
        size = buy_now_item.get("size")
        total = product.price * qty

        session["total_after_coupon"] = total

        return render_template(
            "address.html",
            addresses=addresses,
            buy_now=True,
            buy_product=product,
            buy_size=size,
            buy_qty=qty,
            total=total,
            final_amount=total
        )

    # NORMAL CART FLOW
    if not cart:
        flash("Your cart is empty", "error")
        return redirect(url_for("cart"))

    cart_items = []
    total = 0

    for key, item in cart.items():
        if "_" in key:
            pid, size = key.split("_", 1)
        else:
            pid = key
            size = item.get("size", "M") if isinstance(item, dict) else "M"

        product = Product.query.filter_by(id=int(pid), is_active=True).first()
        if not product:
            continue

        qty = item.get("qty", 1) if isinstance(item, dict) else item
        subtotal = product.price * qty
        total += subtotal

        cart_items.append({
            "product": product,
            "qty": qty,
            "size": size,
            "subtotal": subtotal
        })

    session["total_after_coupon"] = total

    return render_template(
        "address.html",
        addresses=addresses,
        buy_now=False,
        cart_items=cart_items,
        total=total,
        final_amount=total
    )



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
            color = request.form.get("color")
            variant_group = request.form.get("variant_group")
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
                color=color,
                brand=brand,
                variant_group=variant_group,
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
    print("🔥 ROUTE HIT")
    search = request.args.get("search")

    if search:
        products = Product.query.filter(
            Product.name.ilike(f"%{search}%")
        ).all()
    else:
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

        # 🔹 BASIC DETAILS UPDATE
        product.name = request.form.get("name")
        product.type = request.form.get("type")
        product.price = request.form.get("price")
        product.category = request.form.get("category")
        product.brand = request.form.get("brand")
        product.color = request.form.get("color")
        product.variant_group = request.form.get("variant_group")
        product.description = request.form.get("description")

        # 🔹 STOCK UPDATE
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

        # 🔹 IMAGE UPDATE (optional)
        image1 = request.files.get("image1")
        image2 = request.files.get("image2")
        image3 = request.files.get("image3")

        if image1 and image1.filename != "":
            filename1 = secure_filename(image1.filename)
            image1.save(os.path.join(app.config['UPLOAD_FOLDER'], filename1))
            product.image1 = filename1

        if image2 and image2.filename != "":
            filename2 = secure_filename(image2.filename)
            image2.save(os.path.join(app.config['UPLOAD_FOLDER'], filename2))
            product.image2 = filename2

        if image3 and image3.filename != "":
            filename3 = secure_filename(image3.filename)
            image3.save(os.path.join(app.config['UPLOAD_FOLDER'], filename3))
            product.image3 = filename3

        # 🔹 VISIBILITY UPDATE
        update_product_visibility(product.id)

        db.session.commit()

        flash("Product updated successfully ✅", "success")
        return redirect(url_for("manage_products"))

    # 🔹 PRE-FILL DATA
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


@app.route("/admin/sync-shiprocket/<int:order_db_id>")
@role_required("admin")
def sync_shiprocket_order(order_db_id):
    order = Order.query.get_or_404(order_db_id)

    if not order.shiprocket_order_id:
        flash("Shiprocket order id not found for this order ❌", "danger")
        return redirect("/admin/orders")

    token = get_shiprocket_token()
    if not token:
        flash("Shiprocket token failed ❌", "danger")
        return redirect("/admin/orders")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    def pick_best_shipment(shipments):
        """
        Best shipment:
        1) cancelled kakunda undali
        2) AWB unte better
        3) latest id prefer cheyyali
        """
        if not shipments:
            return None

        if isinstance(shipments, dict):
            shipments = [shipments]

        if not isinstance(shipments, list):
            return None

        def sort_key(x):
            status = str(x.get("status") or x.get("current_status") or "").upper()
            sid = x.get("shipment_id") or x.get("id") or 0
            awb = x.get("awb_code") or x.get("awb") or ""
            is_cancelled = 1 if "CANCEL" in status else 0
            has_awb = 1 if awb else 0

            try:
                sid_num = int(sid)
            except Exception:
                sid_num = 0

            return (1 - is_cancelled, has_awb, sid_num)

        shipments = sorted(shipments, key=sort_key, reverse=True)
        return shipments[0]

    try:
        # existing DB values backup
        old_shipment_id = order.shiprocket_shipment_id
        old_awb = order.awb_code
        old_courier = order.courier_name
        old_tracking = order.tracking_url
        old_sr_status = order.shiprocket_status

        # new temp vars
        shipment_id = None
        awb_code = None
        courier_name = None
        tracking_url = None
        shiprocket_status = None

        # --------------------------------
        # 1) ORDER SHOW API
        # --------------------------------
        url = f"https://apiv2.shiprocket.in/v1/external/orders/show/{order.shiprocket_order_id}"
        r = requests.get(url, headers=headers, timeout=30)
        print("SHIPROCKET SHOW ORDER:", r.status_code, r.text)
        r.raise_for_status()

        data = r.json()
        main = data.get("data", data) if isinstance(data, dict) else {}

        shipments = main.get("shipments")
        if not shipments:
            shipments = main.get("shipment_details", [])

        best = pick_best_shipment(shipments)

        if best:
            shipment_id = best.get("shipment_id") or best.get("id")
            awb_code = best.get("awb_code") or best.get("awb")
            courier_name = best.get("courier_name") or best.get("courier")
            tracking_url = best.get("tracking_url")
            shiprocket_status = best.get("status") or best.get("current_status")

        # main fallback
        shipment_id = shipment_id or main.get("shipment_id")
        awb_code = awb_code or main.get("awb_code")
        courier_name = courier_name or main.get("courier_name")
        tracking_url = tracking_url or main.get("tracking_url")
        shiprocket_status = shiprocket_status or main.get("status")

        print("BEST SHIPMENT ID:", shipment_id)
        print("SHOW API AWB:", awb_code)
        print("SHOW API COURIER:", courier_name)
        print("SHOW API STATUS:", shiprocket_status)
        print("SHOW API TRACK URL:", tracking_url)

        # --------------------------------
        # 2) TRACKING API
        # --------------------------------
        final_shipment_id = shipment_id or old_shipment_id

        if final_shipment_id:
            track_url_api = f"https://apiv2.shiprocket.in/v1/external/courier/track/shipment/{final_shipment_id}"
            tr = requests.get(track_url_api, headers=headers, timeout=30)
            print("SHIPROCKET TRACK RESPONSE:", tr.status_code, tr.text)

            if tr.ok:
                tdata = tr.json()
                tracking_data = tdata.get("tracking_data", {}) if isinstance(tdata, dict) else {}
                shipment_track = tracking_data.get("shipment_track", [])

                if shipment_track and isinstance(shipment_track, list):
                    tfirst = shipment_track[0] or {}

                    new_awb = tfirst.get("awb_code") or tfirst.get("awb")
                    new_courier = tfirst.get("courier_name") or tfirst.get("courier")
                    new_status = tfirst.get("current_status") or tfirst.get("status")

                    if new_awb:
                        awb_code = new_awb
                    if new_courier:
                        courier_name = new_courier
                    if new_status:
                        shiprocket_status = new_status

                new_tracking_url = tracking_data.get("track_url") or tracking_data.get("tracking_url")
                if new_tracking_url:
                    tracking_url = new_tracking_url

        # fallback track url
        if not tracking_url and awb_code:
            tracking_url = f"https://shiprocket.co/tracking/{awb_code}"

        # --------------------------------
        # 3) PROTECT EXISTING GOOD VALUES
        # --------------------------------
        if not shipment_id and old_shipment_id:
            shipment_id = old_shipment_id

        if not awb_code and old_awb:
            awb_code = old_awb

        if not courier_name and old_courier:
            courier_name = old_courier

        if not tracking_url and old_tracking:
            tracking_url = old_tracking

        if not shiprocket_status and old_sr_status:
            shiprocket_status = old_sr_status

        print("FINAL SHIPMENT ID:", shipment_id)
        print("FINAL AWB:", awb_code)
        print("FINAL COURIER:", courier_name)
        print("FINAL STATUS:", shiprocket_status)
        print("FINAL TRACK URL:", tracking_url)

        # --------------------------------
        # 4) SAVE ONLY SAFE VALUES
        # --------------------------------
        if shipment_id:
            order.shiprocket_shipment_id = str(shipment_id)

        if awb_code:
            order.awb_code = str(awb_code)

        if courier_name:
            order.courier_name = courier_name

        if tracking_url:
            order.tracking_url = tracking_url

        if shiprocket_status:
            order.shiprocket_status = shiprocket_status

            s = shiprocket_status.upper()
            if "DELIVERED" in s:
                order.status = "DELIVERED"
            elif "OUT FOR DELIVERY" in s:
                order.status = "OUT FOR DELIVERY"
            elif "SHIPPED" in s or "IN TRANSIT" in s:
                order.status = "SHIPPED"
            elif "CANCELLED" in s or "CANCELED" in s:
                order.status = "CANCELLED"
            elif "PICKUP" in s:
                order.status = "PICKUP PENDING"
            elif "NEW" in s:
                order.status = "PLACED"

        db.session.commit()
        flash("Shiprocket details synced successfully ✅", "success")

    except Exception as e:
        db.session.rollback()
        print("SYNC SHIPROCKET ERROR:", e)
        flash(f"Sync failed: {e}", "danger")

    return redirect("/admin/orders")


@app.route("/payment", methods=["GET", "POST"])
def payment():
    if "user_id" not in session:
        return redirect("/login")

    total_after_coupon = session.get("total_after_coupon")

    if total_after_coupon is None:
        return redirect(url_for("address"))

    if request.method == "POST":
        method = request.form.get("method")

        if method == "cod":
            session["payment_method"] = "cod"
            session["final_amount"] = total_after_coupon
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
        status = data.get("current_status") or data.get("status") or ""
        awb = data.get("awb") or data.get("awb_code")
        courier = data.get("courier_name") or data.get("courier")
        tracking_url = data.get("tracking_url")

        order = Order.query.filter_by(order_id=order_id).first()

        if not order:
            print("ORDER NOT FOUND:", order_id)
            return "OK", 200

        if awb:
            order.awb_code = str(awb)

        if courier:
            order.courier_name = courier

        if tracking_url:
            order.tracking_url = tracking_url

        if status:
            order.shiprocket_status = status

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

        user = User.query.get(order.user_id)
        customer_mobile = ""
        customer_name = "Customer"

        if user:
            customer_mobile = (user.mobile or "").strip()
            customer_name = user.username or "Customer"

        if customer_mobile and status:
            status_upper = status.upper()

            if "OUT FOR DELIVERY" in status_upper and not order.wa_ofd_sent:
                send_whatsapp_out_for_delivery(
                    customer_mobile,
                    customer_name,
                    order.order_id,
                    order.tracking_url or "https://www.kalasilks.com/my-orders"
                )
                order.wa_ofd_sent = True
                db.session.commit()

            elif "DELIVERED" in status_upper and not order.wa_delivered_sent:
                send_whatsapp_delivered(
                    customer_mobile,
                    customer_name,
                    order.order_id
                )
                order.wa_delivered_sent = True
                db.session.commit()

        print("UPDATED:", order.order_id, order.status, order.awb_code, order.courier_name, order.tracking_url)

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return "OK", 200


import json

@app.route("/razorpay-checkout")
def razorpay_checkout():

    if "user_id" not in session:
        return redirect("/login")

    amount = session.get("final_amount")
    cart = session.get("cart")

    if not amount or not cart:
        return redirect(url_for("cart"))

    amount_paise = int(float(amount) * 100)

    # ✅ CREATE ORDER IN RAZORPAY
    razorpay_order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1,
        "notes": {
            "user_id": str(session["user_id"]),
            "address_id": str(session.get("address", ""))
        }
    })

    # 🔥 DELETE OLD TEMP (important)
    TempOrder.query.filter_by(
        razorpay_order_id=razorpay_order["id"]
    ).delete()

    # 🔥 SAVE CART
    temp = TempOrder(
        user_id=session["user_id"],
        razorpay_order_id=razorpay_order["id"],
        total_amount=amount,
        address=session.get("address"),
        cart_data=json.dumps(cart)
    )

    db.session.add(temp)
    db.session.commit()

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

import json
import time
import os
from flask import request


@app.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():

    payload = request.data
    signature = request.headers.get("X-Razorpay-Signature")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    # 🔐 VERIFY SIGNATURE
    try:
        client.utility.verify_webhook_signature(
            payload.decode("utf-8"),
            signature,
            secret
        )
    except Exception as e:
        print("❌ Webhook verify failed:", e)
        return "Invalid", 400

    data = request.json
    event = data.get("event")

    # 🎯 HANDLE PAYMENT SUCCESS
    if event == "payment.captured":

        payment = data["payload"]["payment"]["entity"]
        payment_id = payment.get("id")
        razorpay_order_id = payment.get("order_id")

        print("💰 Payment captured:", payment_id)

        # 🔁 DUPLICATE CHECK
        existing = Order.query.filter_by(payment_id=payment_id).first()
        if existing:
            print("⚠️ Duplicate webhook ignored")
            return "OK", 200

        # 🔥 FETCH TEMP ORDER
        temp = TempOrder.query.filter_by(
            razorpay_order_id=razorpay_order_id
        ).first()

        if not temp:
            print("❌ TempOrder not found")
            return "OK", 200

        cart = json.loads(temp.cart_data)

        print("🔥 Creating real orders from cart")

        try:
            for item in cart.values():

                product_id = item.get("product_id")
                qty = item.get("qty", 1)
                size = item.get("size")

                if not product_id:
                    print("❌ product_id missing, skipping")
                    continue

                # 🔥 FETCH SIZE ITEM
                size_item = None
                if size:
                    size_item = ProductSize.query.filter_by(
                        product_id=product_id,
                        size=size
                    ).first()

                # 🔥 STOCK HANDLING (FIXED PART)

                if size_item:
                    # ✅ SIZE BASED PRODUCT
                    if size_item.stock < qty:
                        print("❌ Not enough stock")
                        continue

                    size_item.stock -= qty

                else:
                    # ✅ NO SIZE PRODUCT
                    product = Product.query.get(product_id)

                    if not product:
                        print("❌ Product not found")
                        continue

                    if product.stock < qty:
                        print("❌ Not enough stock (no size)")
                        continue

                    product.stock -= qty

                # 🧾 CREATE ORDER(S)
                for i in range(qty):
                    new_order = Order(
                        order_id=f"ORD{int(time.time()*1000)}{i}",
                        user_id=temp.user_id,
                        product_id=int(product_id),
                        address_id=int(temp.address) if temp.address else None,
                        payment_method="razorpay",
                        payment_id=payment_id,
                        size=size,
                        status="PLACED"
                    )

                    db.session.add(new_order)

            # 💾 SAVE ALL
            db.session.commit()
            print("✅ Orders created & stock updated")

            # 🗑 DELETE TEMP ORDER
            db.session.delete(temp)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            print("❌ DB Error:", e)

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


from urllib.parse import quote

@app.route("/payment-success")
def payment_success():
    if "user_id" not in session:
        return redirect("/login")

    # ✅ DUPLICATE ORDER PROTECTION
    existing_order = Order.query.filter_by(
        payment_id=session.get("razorpay_payment_id")
    ).first()

    if existing_order:
        print("Duplicate order avoided")
        return redirect(url_for("my_orders"))

    cart = session.get("cart", {})
    buy_now_item = session.get("buy_now_item")
    address_id = session.get("address")
    payment_method = session.get("payment_method")

    if not address_id or not payment_method:
        return redirect(url_for("address"))

    created_ids = []
    cart_items = []

    # ---------------- BUY NOW FLOW ----------------
    if buy_now_item:
        product = Product.query.filter_by(
            id=buy_now_item["product_id"],
            is_active=True
        ).first()

        if not product:
            session.pop("buy_now_item", None)
            flash("Product not found ❌", "error")
            return redirect(url_for("home"))

        qty = int(buy_now_item.get("qty", 1))
        size = buy_now_item.get("size")

        cart_items = [{
            "product": product,
            "qty": qty,
            "size": size
        }]

    # ---------------- NORMAL CART FLOW ----------------
    else:
        if not cart:
            return redirect("/cart")

        cart_items = build_cart_items_from_session(cart)

    # ---------------- STOCK CHECK + ORDER CREATE ----------------
    try:
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
                    return redirect(url_for("product_page", pid=product.id))

                size_obj.stock -= qty
                update_product_visibility(product.id)

            for _ in range(qty):
                new_order = Order(
                    order_id="SKS" + str(int(time.time() * 1000)) + str(random.randint(10, 99)),
                    user_id=session["user_id"],
                    product_id=product.id,
                    address_id=address_id,
                    payment_method=payment_method,
                    payment_id=session.get("razorpay_payment_id"),
                    status="PLACED",
                    size=size
                )

                db.session.add(new_order)
                db.session.flush()
                created_ids.append(new_order.id)

                time.sleep(0.001)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("ORDER CREATE ERROR:", e)
        return "Order creation failed ❌"

    orders = Order.query.options(
        joinedload(Order.product),
        joinedload(Order.address)
    ).filter(Order.id.in_(created_ids)).all()

    final_amount = session.get("final_amount", 0)

    # ❌ SHIPROCKET REMOVE (12hrs tarvata create chestham)

    # ---------------- WHATSAPP / EMAIL ----------------
    try:
        user = User.query.get(session["user_id"])
        address = Address.query.get(address_id)

        customer_name = user.username or "Customer"
        customer_mobile = user.mobile or ""
        order_no = orders[0].order_id if orders else "SKSORDER"

        delivery_address_text = ""
        if address:
            delivery_address_text = (
                f"{address.house or ''}, "
                f"{address.street or ''}, "
                f"{address.city or ''}, "
                f"{address.state or ''} - {address.pincode or ''}"
            ).strip(", ")

        # WhatsApp confirmation
        if customer_mobile and orders:
            first_order = orders[0]

            if not first_order.wa_order_confirm_sent:
                send_whatsapp_order_confirmation(
                    customer_mobile,
                    customer_name,
                    order_no,
                    final_amount,
                    delivery_address_text or "Address not available"
                )

                for o in orders:
                    o.wa_order_confirm_sent = True
                db.session.commit()

        # Email
        if user and user.email:
            send_order_email(
                user,
                order_no,
                final_amount,
                "",
                "",
                "https://www.kalasilks.com/my-orders"
            )

    except Exception as e:
        print("Order WhatsApp/Email send failed:", e)

    # ---------------- CLEAR SESSION ----------------
    session.clear()

    return render_template(
        "payment_success.html",
        orders=orders,
        final_amount=final_amount
    )  

@app.route("/shop")
def shop():
    q = request.args.get("q", "").strip()
    min_price = request.args.get("min")
    max_price = request.args.get("max")
    color = request.args.get("color", "").strip()
    type_ = request.args.get("type", "").strip()
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "").strip()
    sub = request.args.get("sub", "").strip()
    size = request.args.get("size", "").strip()
    brand = request.args.get("brand", "").strip()

    query = Product.query.filter_by(is_active=True)

    if q:
        words = q.lower().split()
        for w in words:
            like = f"%{w.rstrip('s')}%"
            query = query.filter(or_(
                Product.name.ilike(like),
                Product.category.ilike(like),
                Product.type.ilike(like),
                Product.brand.ilike(like)
            ))

    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))

    if type_:
        query = query.filter(Product.type.ilike(f"%{type_}%"))

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if sub:
        query = query.filter(Product.sub.ilike(f"%{sub}%"))

    if size:
        query = query.filter(Product.size == size)

    if color:
        query = query.filter(Product.color.ilike(f"%{color}%"))

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

    page = "home"
    if category:
        page = category.lower()
    elif products:
        first_cat = (products[0].category or "").strip().lower()
        if "men" in first_cat:
            page = "men"
        elif "women" in first_cat:
            page = "women"
        elif "kids" in first_cat:
            page = "kids"

    return render_template(
        "shop.html",
        products=products,
        page=page,
        q=q,
        min_price=min_price,
        max_price=max_price,
        color=color,
        type_=type_,
        category=category,
        sort=sort,
        sub=sub,
        size=size,
        brand=brand
    )



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


from datetime import datetime, timedelta

@app.route("/cancel-order/<order_id>", methods=["POST"])
def cancel_order(order_id):

    if "user_id" not in session:
        return redirect("/login")

    order = Order.query.filter_by(order_id=order_id).first()

    if not order:
        return "Order not found ❌"

    # ⏱️ 12hrs check
    if not order.created_at:
        return "Invalid order ❌"

    time_diff = datetime.utcnow() - order.created_at

    if time_diff > timedelta(hours=12):
        return "Cancel time expired ❌"

    # already cancelled check
    if order.status == "CANCELLED":
        return redirect(url_for("my_orders"))

    # 🟢 cancel order
    order.status = "CANCELLED"
    db.session.commit()

    # 🟢 refund (Razorpay)
    if order.payment_method == "razorpay" and order.payment_id:
        try:
            client.payment.refund(order.payment_id)
            print("Refund initiated")

            

            # 🟢 WhatsApp msg
            user = User.query.get(order.user_id)

            if user and user.mobile:
                send_whatsapp_refund(
                    user.mobile,
                    user.username or "Customer",
                    order.order_id,
                    order.product.price if order.product else 0
                )

        except Exception as e:
            print("Refund error:", e)
            print("CANCEL HIT:", order_id)
            print("PAYMENT METHOD:", order.payment_method)
            print("PAYMENT ID:", order.payment_id) 

    return redirect(url_for("my_orders"))
@app.route("/product/<int:pid>")
def product_page(pid):
    product = Product.query.filter_by(id=pid, is_active=True).first_or_404()
    sizes = ProductSize.query.filter_by(product_id=pid).all()

    related_colors = []

    if product.variant_group and product.variant_group.strip():
        all_variant_products = Product.query.filter(
            Product.variant_group == product.variant_group,
            Product.is_active == True
        ).order_by(Product.id.asc()).all()

        for item in all_variant_products:
            color_value = (item.color or "").strip()

            if color_value:   # color empty kakapothe matrame add chesthundi
                related_colors.append(item)

    return render_template(
        "product.html",
        product=product,
        sizes=sizes,
        related_colors=related_colors
    )

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


@app.route("/run-shiprocket")
def run_shiprocket():
    process_shiprocket_orders()
    return "Shiprocket checked ✅"

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    import threading
    import time

    def run_shiprocket_worker():
        while True:
            with app.app_context():
                process_shiprocket_orders()
            time.sleep(300)  # every 5 mins

    # ✅ Start background worker
    threading.Thread(target=run_shiprocket_worker, daemon=True).start()

    app.run(debug=True)
