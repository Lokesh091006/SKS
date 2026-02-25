from database import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(10), unique=True, nullable=False)
    username = db.Column(db.String(50))
    email = db.Column(db.String(100), unique=True)
    role = db.Column(db.String(20), default="customer") 