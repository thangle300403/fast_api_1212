from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent
from langchain import hub
# py -m pip install fastapi uvicorn python-slugify chromadb SQLAlchemy PyMySQL langchain langchain-core langchain-community langchain-openai langgraph openai tiktoken python-dotenv aiohttp requests pydantic

# uvicorn sql_agent:app --reload --port 5068

# uvicorn sql_agent:app --host 0.0.0.0 --port 5068 --reload


# Load environment variables
load_dotenv()

# DB connection
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
)

allowed_tables = [
    "order",
    "order_item",
    "product",
    "category",
    "comment",
    "brand",
    "status",
    "ward",
    "province",
    "transport",
    "image_item",
]

db = SQLDatabase(engine, include_tables=allowed_tables)

# LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Toolkit
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# System prompt
# System prompt
prompt_template = hub.pull("langchain-ai/sql-agent-system-prompt")
system_message = (
    prompt_template.format(dialect="MySQL", top_k=5)
    + "\n\nIMPORTANT RULES:\n"
      "1. You are ONLY allowed to execute SELECT queries.\n"
      "2. For UPDATE/DELETE/INSERT/ALTER/DROP/CREATE or any DML/DDL queries, "
      "you must refuse and explain that only read-only access is permitted.\n"
      "3. Never attempt to change the database state.\n"
      "4. If the user asks for modifications, respond with a polite refusal."
      "5. Answers must be in Vietnamese."
)


# Agent
agent_executor = create_react_agent(
    llm, toolkit.get_tools(), prompt=system_message)

# FastAPI app
app = FastAPI()

# Request body schema


class QueryRequest(BaseModel):
    query: str
    email: str | None = None
    top_product: str | None = None


@app.post("/sql")
async def run_sql_agent(req: QueryRequest):
    """Run SQL agent with a user query and return AI answer."""

   # ✅ Build richer query context for LLM
    user_query = req.query
    if req.top_product:
        user_query += f"\n(Sản phẩm được quan tâm: {req.top_product})"

    print("🧩 Final SQL Agent query:", user_query)

    lowered = req.query.lower()

    # 🔒 Rule: if query mentions orders
    if "order" in lowered or "đơn" in lowered:
        print("email", req.email)
        if not req.email or req.email.strip() == '':
            return {"answer": "❌ Bạn cần đăng nhập (cung cấp email) để xem thông tin đơn hàng."}

        # Try to detect an order ID (e.g., "1234")
        import re
        order_id_match = re.search(r"\b\d+\b", req.query)
        if order_id_match:
            order_id = order_id_match.group(0)

            with engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT o.id
                        FROM `order` o
                        JOIN customer c ON o.customer_id = c.id
                        WHERE o.id = :order_id AND c.email = :email
                    """),
                    {"order_id": order_id, "email": req.email}
                ).fetchone()

            if not result:
                return {"answer": f"❌ Không tìm thấy đơn hàng #{order_id} thuộc về email {req.email}."}

    events = agent_executor.stream(
        {"messages": [("user", user_query)]},
        stream_mode="values",
    )

    final_answer = None
    for event in events:
        final_answer = event["messages"][-1].content

        print(final_answer)

    return {"answer": final_answer}
