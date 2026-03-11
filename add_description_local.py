from app import app, db

with app.app_context():
    try:
        db.session.execute(db.text("ALTER TABLE product ADD COLUMN description TEXT"))
        db.session.commit()
        print("✅ Local SQLite lo description column add ayindi")
    except Exception as e:
        print("⚠️ Error / already exists:", e)