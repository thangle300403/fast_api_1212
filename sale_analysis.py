from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from langchain_openai import ChatOpenAI
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langgraph.prebuilt import create_react_agent

# ==================================================
# ENV + DB
# ==================================================
load_dotenv()

engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USERNAME')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}/"
    f"{os.getenv('DB_NAME')}"
)

# 🔐 CHỈ CÁC BẢNG TỐI THIỂU CHO SALE ANALYSIS
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

# ==================================================
# LLM
# ==================================================
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
)

toolkit = SQLDatabaseToolkit(db=db, llm=llm)

# ==================================================
# SYSTEM PROMPT – SALE ANALYST AI
# ==================================================
SYSTEM_PROMPT = """
Bạn là Sale Analyst AI cho hệ thống bán hàng cầu lông (Admin-side).

VAI TRÒ:
- Phân tích dữ liệu sản phẩm từ database (READ-ONLY)
- Đánh giá tình trạng tồn kho và mức độ rủi ro kinh doanh
- Đề xuất sản phẩm CẦN XEM XÉT GIẢM GIÁ hoặc KHÔNG NÊN GIẢM GIÁ
- Hỗ trợ ADMIN ra quyết định, KHÔNG tự ý áp dụng sale

QUY TẮC BẮT BUỘC:
1. CHỈ ĐƯỢC dùng SELECT query
2. TUYỆT ĐỐI không UPDATE / INSERT / DELETE / ALTER
3. Không tự áp dụng sale, chỉ ĐỀ XUẤT
4. Inventory (inventory_qty) là yếu tố QUYẾT ĐỊNH CHÍNH
5. Không phải mọi sản phẩm bán chậm đều phải giảm giá

ĐỊNH NGHĨA NGHIỆP VỤ:

[SLOW-MOVING PRODUCT]
- inventoryQty >= HIGH_STOCK_THRESHOLD
- Mức độ quan tâm thấp (comment thấp trong WINDOW_DAYS)
→ Đây là TÍN HIỆU CẢNH BÁO tồn kho
→ KHÔNG đồng nghĩa với việc bắt buộc giảm giá
→ Chỉ được đề xuất giảm giá nếu KHÔNG vi phạm các quy tắc bên dưới

[ĐIỀU KIỆN ĐỀ XUẤT GIẢM GIÁ]
- Sản phẩm thuộc nhóm SLOW-MOVING
- Không thuộc nhóm gần hết hàng
- Không phát hiện rủi ro phá giá
→ Được phép đề xuất giảm giá NHẸ để hỗ trợ quay vòng tồn kho

[MỨC GIẢM GIÁ CHO PHÉP]
- Chỉ đề xuất giảm 8%
- Không đề xuất mức khác
- Mục tiêu là kích cầu nhẹ, KHÔNG xả kho

[NEAR-OUT-OF-STOCK]
- inventoryQty <= LOW_STOCK_THRESHOLD
→ TUYỆT ĐỐI KHÔNG đề xuất giảm giá
→ Chỉ đánh dấu cần chú ý do rủi ro thiếu hàng

[DISCOUNT CONTROL]
- Nếu discountPercentage hiện tại >= 10% → KHÔNG đề xuất thêm giảm giá
- Nếu discountPercentage >= 30% và inventory thấp → CẢNH BÁO ADMIN

OUTPUT FORMAT (BẮT BUỘC):
Sau khi hoàn tất phân tích và gọi tool,
hãy trả về DUY NHẤT danh sách các dòng theo mẫu sau:

<Tên sản phẩm>: giảm giá <X>%
NEAR-OUT-OF-STOCK: <Tên sản phẩm> - lí do
DISCOUNT CONTROL: lí do

QUY TẮC OUTPUT:
- Mỗi sản phẩm 1 dòng
- Chỉ ghi tên sản phẩm và % giảm giá
- Nếu không có sản phẩm nào đủ điều kiện giảm giá,
  trả về đúng 1 dòng:
  KHÔNG CÓ SẢN PHẨM NÀO CẦN XEM XÉT GIẢM GIÁ

NGÔN NGỮ:
- Tiếng Việt
- Văn phong ngắn gọn, trung tính, mang tính vận hành

"""

# ==================================================
# AGENT
# ==================================================
agent_executor = create_react_agent(
    llm,
    toolkit.get_tools(),
    prompt=SYSTEM_PROMPT
)

# ==================================================
# FASTAPI APP
# ==================================================
app = FastAPI(title="Sale Analysis AI")


class SaleAnalysisRequest(BaseModel):
    window_days: int = 30
    high_stock_threshold: int = 30
    low_stock_threshold: int = 5


@app.post("/sale-analysis")
async def run_sale_analysis(
    req: SaleAnalysisRequest = Body(default=SaleAnalysisRequest())
):
    """
    Admin triggers sale analysis.
    No user question needed.
    """

    analysis_task = f"""
    Phân tích tình trạng sản phẩm trong {req.window_days} ngày gần nhất.

    HIGH_STOCK_THRESHOLD = {req.high_stock_threshold}
    LOW_STOCK_THRESHOLD = {req.low_stock_threshold}

    Hãy:
    - Xác định sản phẩm SLOW-MOVING
    - Xác định sản phẩm NEAR-OUT-OF-STOCK
    - Phát hiện các trường hợp DISCOUNT nguy hiểm
    """

    events = agent_executor.stream(
        {"messages": [("user", analysis_task)]},
        stream_mode="values",
    )

    final_answer = None
    for event in events:
        final_answer = event["messages"][-1].content
        print(final_answer)

    return {
        "report": final_answer
    }
