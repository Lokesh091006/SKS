from database import db
from datetime import datetime

class Order(db.Model):
    __tablename__ = "order"

    id = db.Column(db.Integer, primary_key=True)

   
    order_id = db.Column(db.String(20), nullable=False)

    
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    address_id = db.Column(db.Integer, db.ForeignKey("address.id"), nullable=False)

   
    payment_method = db.Column(db.String(20), nullable=False)  
    status = db.Column(db.String(20), default="Placed")        
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    
    user = db.relationship("User", backref="orders")
    product = db.relationship("Product", backref="orders")
    address = db.relationship("Address", backref="orders")

