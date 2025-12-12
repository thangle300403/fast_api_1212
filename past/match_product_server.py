from mcp.server.fastmcp import FastMCP
from slugify import slugify
import os
from dotenv import load_dotenv
from chromadb import HttpClient
from chromadb.config import Settings

load_dotenv()

# 🌐 Environment
FRONTEND_URL = os.getenv("FRONTEND_URL_NEXT", "https://billwinslow.top")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://cdn.billwinslow.top")
CHROMA_URL = os.getenv("CHROMA_URL", "http://72.60.211.155:8000")

# 🚀 Initialize MCP server
mcp = FastMCP("BillShop Match Product")

# 🧠 Connect to remote Chroma server
print(f" Connecting to Chroma at {CHROMA_URL} ...")
chroma_client = HttpClient(
    host=CHROMA_URL, settings=Settings(anonymized_telemetry=False))
collection = chroma_client.get_or_create_collection("product_descriptions")
print(" Connected to Chroma collection: product_descriptions")


@mcp.tool()
def match_product(user_question: str) -> dict:
    """Find matching product in vector DB"""
    query = user_question.lower().strip()

    # 🔍 Semantic search
    results = collection.query(query_texts=[query], n_results=8)
    if not results.get("documents") or not results["documents"][0]:
        return {"success": False, "message": "Không tìm thấy sản phẩm phù hợp."}

    # 🎯 Process results
    candidates = []
    for idx, doc in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][idx]
        score = 1 - results["distances"][0][idx]
        candidates.append({
            "name": metadata["name"],
            "price": metadata["price"],
            "metadata": metadata,
            "score": score
        })

    # ⚡ Textual boost
    for c in candidates:
        norm_name = c["name"].lower()
        bonus = 0.5 if norm_name in query else 0.2 if norm_name.replace(
            " pro", "") in query else 0
        c["totalScore"] = c["score"] + bonus

    # 🏆 Top match
    top = sorted(candidates, key=lambda x: x["totalScore"], reverse=True)[0]

    # 🖼️ Build HTML card
    p = top["metadata"]
    slug = slugify(p["name"])
    url = f"{FRONTEND_URL}/san-pham/{slug}-{p['product_id']}"
    img = f"{IMAGE_BASE_URL}/{p['featured_image']}"

    card = f"""
<div class="product-card" style="border:1px solid #ccc;border-radius:8px;padding:8px;margin-bottom:8px;
display:flex;align-items:center;gap:10px;background:#f8f9fa;max-width:400px;">
  <img src="{img}" alt="{p['name']}" style="width:70px;height:70px;object-fit:contain;border-radius:6px;" />
  <div style="flex:1;line-height:1.3;">
    <a href="{url}" target="_blank" style="font-weight:bold;font-size:14px;color:#1D4ED8;display:block;margin-bottom:4px;">
      {p['name']}
    </a>
    <span style="font-size:13px;color:#16A34A;">💰 {p['price']:,}đ</span>
  </div>
</div>
""".strip()

    return {
        "success": True,
        "topMatchedProduct": p,
        "matchedProdInUserQues": [
            f"{c['name']} (giá {c['price']:,}đ, điểm {c['totalScore']:.2f})"
            for c in candidates
        ],
        "productDetailUrls": card
    }


if __name__ == "__main__":
    print(" Starting MCP stdio server for match_product...")
    mcp.run(transport="stdio")
