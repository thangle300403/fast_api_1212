# match_product.py
import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import slugify
import chromadb
import re
from openai import OpenAI  # pip install openai
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="BillShop Match Product API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

CHROMA_URL = os.getenv("CHROMA_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL_NEXT")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ✅ Chroma 0.5+ client
host, port = re.sub(r"^https?://", "", CHROMA_URL).split(":")
client = chromadb.HttpClient(host=host, port=int(port))
collection = client.get_or_create_collection("product_descriptions")

# ✅ OpenAI embeddings (must match how the collection was built)
oa = OpenAI(api_key=OPENAI_API_KEY)


def embed_query(text: str):
    emb = oa.embeddings.create(model="text-embedding-3-large", input=text)
    return emb.data[0].embedding  # list[float], 3072 dims


@app.get("/match_product")
def match_product(query: str = Query(..., description="User message to match product")):
    try:
        query = query.strip()
        if not query:
            return {"success": False, "message": "Empty query"}

        # 🔑 IMPORTANT: we embed query ourselves to avoid ONNX + ensure dimension match
        qvec = embed_query(query)

        # 🔍 Query using query_embeddings (NOT query_texts)
        results = collection.query(
            query_embeddings=[qvec],
            n_results=8,
            include=["metadatas", "distances", "documents"]
        )

        if not results.get("metadatas") or not results["metadatas"][0]:
            return {"success": False, "message": "No products found"}

        metas = results["metadatas"][0]
        dists = results["distances"][0]
        normalized_q = " ".join(query.lower().split())

        candidates = []
        for meta, dist in zip(metas, dists):
            name = meta.get("name", "")
            price = float(meta.get("price", 0) or 0)
            score = 1 - float(dist)  # convert distance → similarity
            normalized_name = " ".join(name.lower().split())
            has_exact = normalized_name in normalized_q
            has_partial = normalized_name.replace(" pro", "") in normalized_q
            bonus = 0.5 if has_exact else (0.2 if has_partial else 0.0)
            total = score + bonus
            candidates.append({
                "name": name,
                "price": price,
                "product_id": meta.get("product_id"),
                "featured_image": meta.get("featured_image"),
                "score": round(score, 4),
                "total_score": round(total, 4),
            })

        if not candidates:
            return {"success": False, "message": "No match found"}

        # 🟢 Apply minimum score filter
        filtered = [c for c in candidates if c["total_score"] >= 0.6]

        if not filtered:
            return {"success": False, "top_match": "No product matched the minimum score "}

        filtered.sort(key=lambda x: x["total_score"], reverse=True)
        top = filtered[0]

        print("✅ Top match:", top["name"],
              f"(score: {top['total_score']})", flush=True)

        slug = slugify.slugify(top["name"])
        url = f"{FRONTEND_URL}/san-pham/{slug}-{top['product_id']}"
        encoded_msg = f"tôi muốn thêm {top['name']} vào giỏ hàng"
        img_src = f"{IMAGE_BASE_URL}/{top['featured_image']}"

        card_html = f"""
<div class="product-card"
     style="border:1px solid #ccc;border-radius:8px;
            padding:8px;margin-bottom:8px;
            display:flex;align-items:center;gap:10px;
            background:#f8f9fa;max-width:400px;">
  <img src="{img_src}" alt="{top['name']}"
       style="width:70px;height:70px;object-fit:contain;border-radius:6px;" />
  <div style="flex:1;line-height:1.3;">
    <a href="{url}"
       style="font-weight:bold;font-size:14px;color:#1D4ED8;display:block;margin-bottom:4px;"
       target="_blank">{top['name']}</a>
    <span style="font-size:13px;color:#16A34A;">💰 {int(top['price']):,}đ</span>
  </div>
  <button class="add-to-cart-btn"
          data-product="{top['name']}" data-msg="{encoded_msg}"
          style="background:#FACC15;color:#000;border:none;
                 padding:4px 8px;border-radius:4px;
                 font-size:12px;font-weight:500;cursor:pointer;">
    🛒 Thêm
  </button>
</div>
""".strip()

        return {
            "success": True,
            "top_match": top,
            "matched_products": [
                f"{p['name']} (điểm {p['total_score']:.2f})" for p in candidates[:5]
            ],
            "card_html": card_html,
        }

    except Exception as e:
        import traceback
        print("❌ VECTOR SEARCH ERROR:", e, flush=True)
        print(traceback.format_exc(), flush=True)
        return JSONResponse(
            status_code=500,
            content={"success": False,
                     "message": f"Internal error: {type(e).__name__}", "details": str(e)},
        )
