import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from typing_extensions import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

# Load .env
load_dotenv()

engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USERNAME')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
)
db = SQLDatabase(engine)


class State(TypedDict):
    question: str
    query: str
    result: str
    answer: str
    # 'next' sẽ được set khi user chọn y/n (execute_query | skip_query)
    next: str


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

system_message = """
Given an input question, create a syntactically correct {dialect} query.
- Only execute SELECT queries directly.
- For UPDATE/DELETE/INSERT/ALTER/CREATE/DROP/TRUNCATE: DO NOT execute.
  Instead, output the SQL inside ```sql ... ``` for admin review.
Use only real tables/columns from schema:
{table_info}
"""
user_message = "Question: {input}"

query_prompt = ChatPromptTemplate(
    [("system", system_message), ("user", user_message)]
)


class QueryOutput(TypedDict):
    query: Annotated[str, ..., "SQL query candidate"]


def clean_sql(query: str) -> str:
    q = query.strip()
    if "```sql" in q:
        q = q.split("```sql")[1].split("```")[0].strip()
    elif "```" in q:
        q = q.split("```")[1].split("```")[0].strip()
    return q


def write_query(state: State):
    prompt = query_prompt.invoke({
        "dialect": db.dialect,
        "table_info": db.get_table_info(),
        "input": state["question"],
    })
    structured_llm = llm.with_structured_output(QueryOutput)
    result = structured_llm.invoke(prompt)
    sql_candidate = clean_sql(result["query"])
    return {"query": sql_candidate}


def decider(state: State):
    """No-op node; routing happens via conditional edges based on state['next']."""
    return {}


def route_next(state: State):
    # 'next' được set sau khi hỏi y/n. Nếu chưa có, giữ nguyên tại 'decider'.
    nxt = state.get("next")
    if nxt in ("execute_query", "skip_query"):
        return nxt
    # Ở lần chạy đầu, chưa có quyết định -> đứng lại ở decider (nhờ interrupt_before)
    return "stay"


def execute_query(state: State):
    try:
        query = state["query"].strip()
        with engine.connect() as conn:
            result = conn.execute(text(query))

            # If it's a SELECT → fetch rows
            if query.lower().startswith("select"):
                rows = result.fetchall()
                # convert rows (SQLAlchemy Row objects) to list of dicts for readability
                rows_as_dict = [dict(r._mapping) for r in rows]
                return {"result": rows_as_dict}

            # Otherwise (UPDATE/INSERT/DELETE) → commit + return affected rows
            else:
                conn.commit()
                return {"result": f"✅ Executed. Rows affected: {result.rowcount}"}

    except Exception as e:
        return {"result": f"❌ Error executing query: {e}"}


def skip_query(state: State):
    return {"result": "❌ Operation cancelled by user."}


def generate_answer(state: State):
    prompt = (
        "Given the user question, SQL query, and SQL result, answer the question.\n\n"
        f"Question: {state['question']}\n"
        f"SQL Query: {state['query']}\n"
        f"SQL Result: {state['result']}"
    )
    response = llm.invoke(prompt)
    return {"answer": response.content}


# Build graph
graph_builder = StateGraph(State)
graph_builder.add_node("write_query", write_query)
graph_builder.add_node("decider", decider)
graph_builder.add_node("execute_query", execute_query)
graph_builder.add_node("skip_query", skip_query)
graph_builder.add_node("generate_answer", generate_answer)

graph_builder.add_edge(START, "write_query")
graph_builder.add_edge("write_query", "decider")

# Conditional edges xuất phát từ 'decider'
graph_builder.add_conditional_edges(
    "decider",
    route_next,
    {
        "execute_query": "execute_query",
        "skip_query": "skip_query",
        "stay": "decider",  # lần đầu, chưa có quyết định
    },
)

# Sau khi chọn nhánh, sinh câu trả lời
graph_builder.add_edge("execute_query", "generate_answer")
graph_builder.add_edge("skip_query", "generate_answer")

# MemorySaver + interrupt BEFORE 'decider' để chờ y/n trước khi rẽ nhánh
memory = MemorySaver()
graph = graph_builder.compile(
    checkpointer=memory, interrupt_before=["decider"]
)

# ---------------- RUN ----------------
user_question = "Tỉnh tây ninh có id là?"
config = {"configurable": {"thread_id": "1"}}

print(">>> Start run")

# First run until interrupt at 'decider'
for step in graph.stream({"question": user_question}, config, stream_mode="updates"):
    print(step)

# Ask user y/n
decision = input("\nDo you want to execute the query? (y/n): ")

# Update checkpoint with the decision
if decision.lower().startswith("y"):
    graph.update_state(config, {"next": "execute_query"})
else:
    graph.update_state(config, {"next": "skip_query"})

# Resume from the checkpoint
for step in graph.stream(None, config, stream_mode="updates"):
    print(step)
