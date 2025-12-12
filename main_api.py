# main_api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from match_product import app as match_product_app
from sql_agent import app as sql_agent_app

main = FastAPI(title="BillShop Tool Gateway")

# py -m uvicorn main_api:main --host 0.0.0.0 --port 5068 --reload

main.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔗 Mount sub-apps
main.mount("/match", match_product_app)
main.mount("/sql", sql_agent_app)
