from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi import FastAPI, Body
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from typing_extensions import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from fastapi import FastAPI

app = FastAPI()
# uvicorn main:app --reload --port 8000

origins = [
    "http://localhost:4000",
    "http://127.0.0.1:4000",
]

# Allow CORS for your Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # allow both localhost + 127.0.0.1
    allow_credentials=True,
    allow_methods=["*"],            # allow GET, POST, OPTIONS, etc.
    allow_headers=["*"],            # allow all headers
)

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
    next: str  # execute_query | skip_query


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
    return {}


def route_next(state: State):
    nxt = state.get("next")
    if nxt in ("execute_query", "skip_query"):
        return nxt
    return "stay"


def execute_query(state: State):
    try:
        query = state["query"].strip()
        with engine.connect() as conn:
            result = conn.execute(text(query))

            if query.lower().startswith("select"):
                rows = result.fetchall()
                rows_as_dict = [dict(r._mapping) for r in rows]
                return {"result": rows_as_dict}
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

graph_builder.add_conditional_edges(
    "decider",
    route_next,
    {
        "execute_query": "execute_query",
        "skip_query": "skip_query",
        "stay": "decider",
    },
)

graph_builder.add_edge("execute_query", "generate_answer")
graph_builder.add_edge("skip_query", "generate_answer")

memory = MemorySaver()
graph = graph_builder.compile(
    checkpointer=memory, interrupt_before=["decider"]
)


class QuestionInput(BaseModel):
    question: str
    thread_id: str = "1"


class DecisionInput(BaseModel):
    thread_id: str
    decision: str  # "y" or "n"


@app.post("/ask")
async def ask(input: QuestionInput):
    """
    Step 1: User asks a question.
    This will run until the 'decider' node and interrupt.
    Response includes the proposed SQL for review.
    """
    config = {"configurable": {"thread_id": input.thread_id}}
    steps = list(graph.stream(
        {"question": input.question}, config, stream_mode="updates"))

    # Extract proposed query for review
    sql_query = None
    for step in steps:
        if "write_query" in step:
            sql_query = step["write_query"]["query"]

    return {
        "steps": steps,
        "proposed_query": sql_query,
        "message": "Review the proposed query and call /decide with y/n"
    }


@app.post("/decide")
async def decide(input: DecisionInput):
    """
    Step 2: User decides (y/n).
    Resume from checkpoint with execute_query or skip_query.
    """
    config = {"configurable": {"thread_id": input.thread_id}}
    if input.decision.lower().startswith("y"):
        graph.update_state(config, {"next": "execute_query"})
    else:
        graph.update_state(config, {"next": "skip_query"})

    steps = list(graph.stream(None, config, stream_mode="updates"))

    # Extract final answer if present
    answer = None
    for step in steps:
        if "generate_answer" in step:
            answer = step["generate_answer"]["answer"]

    return {
        "steps": steps,
        "final_answer": answer,
    }
