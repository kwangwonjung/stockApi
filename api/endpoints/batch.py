from fastapi import APIRouter
from services.stock_dvdservice import process_sync_dividend

router = APIRouter()

# 배당 정보 가져오기
@router.post("/sync-dividend")
def sync_dividend():
    result = process_sync_dividend()
    return result