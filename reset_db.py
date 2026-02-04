from app import app
from database import db

with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database reset done ✅")
