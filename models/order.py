from database import db
from datetime import datetime

class Order(db.Model):
    __tablename__ = "order"

    id = db.Column(db.Integer, primary_key=True)

    # Public order id (shown to user)
    order_id = db.Column(db.String(20), nullable=False)

    # Relations
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    address_id = db.Column(db.Integer, db.ForeignKey("address.id"), nullable=False)

    # Order info
    payment_method = db.Column(db.String(20), nullable=False)  # COD / ONLINE
    status = db.Column(db.String(20), default="Placed")        # Placed, Shipped, Delivered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship("User", backref="orders")
    product = db.relationship("Product", backref="orders")
    address = db.relationship("Address", backref="orders")

