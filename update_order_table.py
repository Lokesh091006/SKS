import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(database_url)

queries = [
    'ALTER TABLE "order" ADD COLUMN shiprocket_order_id VARCHAR(100)',
    'ALTER TABLE "order" ADD COLUMN shiprocket_shipment_id VARCHAR(100)',
    'ALTER TABLE "order" ADD COLUMN shiprocket_status VARCHAR(100)',
    'ALTER TABLE "order" ADD COLUMN awb_code VARCHAR(100)',
    'ALTER TABLE "order" ADD COLUMN courier_name VARCHAR(100)',
    'ALTER TABLE "order" ADD COLUMN tracking_url VARCHAR(500)',
    'ALTER TABLE "order" ADD COLUMN payment_id VARCHAR(120)'
]

with engine.connect() as conn:
    for q in queries:
        try:
            conn.execute(text(q))
            print("✅ Ran:", q)
        except Exception as e:
            print("⚠️ Skipped / Error:", q, e)

    conn.commit()

print("Done ✅")