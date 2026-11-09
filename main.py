from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import batch # 방금 만든 주식 라우터 임포트

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 (주소 앞에 자동으로 /api/v1/stocks가 붙습니다)
app.include_router(batch.router, prefix="/api/batchs", tags=["Batchs"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)