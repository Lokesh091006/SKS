from database import db

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)

    category = db.Column(db.String(50))
    type = db.Column(db.String(50))       
    color = db.Column(db.String(30))
    brand = db.Column(db.String(50))
    sizes = db.Column(db.String(100))  

    image = db.Column(db.String(200))
    image2 = db.Column(db.String(200))
    image3 = db.Column(db.String(200))

