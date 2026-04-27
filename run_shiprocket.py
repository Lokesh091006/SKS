from app import app, process_shiprocket_orders

with app.app_context():
    print("⏳ Cron running...")
    process_shiprocket_orders()