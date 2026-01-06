from fastapi import FastAPI, Body
from pydantic import BaseModel
import os
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_openai import ChatOpenAI

# ===============================
# ENV + DB
# ===============================
load_dotenv()

engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USERNAME')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}/"
    f"{os.getenv('DB_NAME')}"
)

# ===============================
# LLM (NO AGENT – OPTIONAL)
# ===============================
# LLM giờ chỉ dùng để format / summary (không quyết logic)
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

# ===============================
# FASTAPI
# ===============================
app = FastAPI(title="Sale Analysis AI (Final – Rule Based)")


class SaleAnalysisRequest(BaseModel):
    window_days: int = 30
    high_stock_threshold: int = 30
    low_stock_threshold: int = 5


# ===============================
# BUSINESS RULES (CORE)
# ===============================
def decide_discount_and_reason(inventory_qty: int, high: int, low: int):
    """
    Quyết định % sale + reason theo LUẬT CỨNG.
    AI KHÔNG được phép thay đổi.
    """
    if inventory_qty <= low:
        return (
            0,
            "Tồn kho bằng hoặc thấp hơn ngưỡng cho phép, sản phẩm sắp hoặc đã hết hàng nên không áp dụng giảm giá."
        )

    ratio = inventory_qty / high

    if ratio >= 3:
        return (
            10,
            "Tồn kho gấp nhiều lần ngưỡng chuẩn, hàng quay vòng rất chậm nên cần giảm giá để giải phóng tồn kho."
        )
    elif ratio >= 2:
        return (
            8,
            "Tồn kho cao hơn mức an toàn trong thời gian dài, cần hỗ trợ giá để tăng tốc độ bán ra."
        )
    elif ratio >= 1:
        return (
            5,
            "Tồn kho vượt ngưỡng chuẩn, áp dụng giảm nhẹ để kích cầu và cải thiện tốc độ quay vòng."
        )
    else:
        return (
            0,
            "Tồn kho đang ở mức an toàn, không cần áp dụng giảm giá."
        )


@app.post("/sale-analysis")
async def run_sale_analysis(
    req: SaleAnalysisRequest = Body(default=SaleAnalysisRequest())
):
    # ===============================
    # SQL QUERY
    # ===============================
    with engine.connect() as conn:
        slow_rows = conn.execute(
            text("""
                SELECT id, name, inventory_qty
                FROM product
                WHERE inventory_qty >= :high
                  AND inventory_qty > :low
            """),
            {
                "high": req.high_stock_threshold,
                "low": req.low_stock_threshold
            }
        ).fetchall()

        near_out_rows = conn.execute(
            text("""
                SELECT id, name, inventory_qty
                FROM product
                WHERE inventory_qty <= :low
            """),
            {"low": req.low_stock_threshold}
        ).fetchall()

    # ===============================
    # APPLY BUSINESS RULES
    # ===============================
    slow_products = []
    for r in slow_rows:
        p = dict(r._mapping)
        discount, reason = decide_discount_and_reason(
            p["inventory_qty"],
            req.high_stock_threshold,
            req.low_stock_threshold
        )
        p["recommended_discount"] = discount
        p["reason"] = reason
        slow_products.append(p)

    near_out_products = []
    for r in near_out_rows:
        p = dict(r._mapping)
        discount, reason = decide_discount_and_reason(
            p["inventory_qty"],
            req.high_stock_threshold,
            req.low_stock_threshold
        )
        p["recommended_discount"] = discount
        p["reason"] = reason
        near_out_products.append(p)

    # ===============================
    # FINAL REPORT (JSON THUẦN)
    # ===============================
    report = {
        "slow_moving_products": slow_products,
        "near_out_of_stock_products": near_out_products,
        "discount_control_alerts": []
    }

    return {"report": report}
