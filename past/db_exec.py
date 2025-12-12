import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env variables (DB_HOST, DB_USERNAME, DB_PASSWORD, DB_NAME)
load_dotenv()

# Create pooled SQLAlchemy engine
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}",
    pool_size=5,        # keep 5 persistent connections
    max_overflow=10,    # allow 10 extra if needed
    pool_pre_ping=True  # test before using
)

# Function to execute any SQL


def execute_sql(query: str):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))

            # If it's a SELECT → fetch results
            if query.strip().lower().startswith("select"):
                rows = result.fetchall()
                print("✅ Query OK. Rows fetched:", len(rows))
                for row in rows:
                    print(row)
            else:
                # For UPDATE/INSERT/DELETE → commit
                conn.commit()
                print("✅ Executed. Rows affected:", result.rowcount)

    except Exception as e:
        print("❌ Error executing query:", e)


if __name__ == "__main__":
    # Example queries
    # execute_sql("SELECT NOW();")
    # execute_sql("UPDATE product SET price = 5000000 WHERE id = 2;")
    execute_sql("SELECT price FROM product WHERE name = 'Yonex Astrox 100zz'")
