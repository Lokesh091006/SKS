from database import db

class ProductSize(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    size = db.Column(db.String(10))
    stock = db.Column(db.Integer)