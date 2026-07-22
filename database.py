import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
        print("[ERROR] Database credentials missing. Please verify the .env configuration.")
        return None

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return None