from datetime import datetime
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 기존 배당 서비스 임포트[cite: 5]
from services.stock_dvdservice import process_sync_dividend

# 주식 일별 데이터 서비스 임포트
from services.stock_service import set_stock_sum_data
from services.stock_service import process_stock_50day_data
from services.stock_service import process_stock_day_data


router = APIRouter()


# 주식 일별 데이터 요청 바디 모델
class StockDayDataRequest(BaseModel):
  stock_sum: bool = Field(
      default=True, description="요약 데이터 업서트 실행 여부 (bstockSum)"
  )


# 1. 배당 정보 동기화 (POST)
@router.post("/sync-dividend", summary="배당 정보 동기화")
def sync_dividend():
  result = process_sync_dividend()  #[cite: 5]
  return result


# 2. 주식 일별 데이터 자동 동기화 (POST)
@router.post("/sync-stocksum", summary="주식 일별 데이터 자동 동기화")
def sync_stock_sum_data(request: StockDayDataRequest = StockDayDataRequest()):
  """이번 달 기준으로 10개월 전 1일자와 저번 달(전월) 날짜를 자동으로 계산하여

  주식 일별 데이터를 수집하고 Supabase에 업서트합니다.
  """
  try:
    now = datetime.now()
    gubn = ''
    strEndDate = now.strftime("%Y%m")  + "01" # 예: '202610'

    # 2. 이번 달 기준으로 10개월 전의 1일 구하기 (예: 11월 기준 -> 올해 1월)
    start_target_date = now - relativedelta(months=10)
    strStartDate = start_target_date.strftime("%Y/%m")  # 예: '2026/01'
    strStartDate = strStartDate.replace("/", "") + "01"
    
    # 비즈니스 로직 함수 호출
    result = set_stock_sum_data(
        gubn =gubn,
        beginBasDt=strStartDate,
        strEndDate=strEndDate,
    )

    if result.get("status") == "error":
      raise HTTPException(status_code=500, detail=result.get("message"))

    return {
        "calculated_range": {
            "start_date": strStartDate,
            "end_date": strEndDate,
        },
        **result,
    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")

@router.post("/sync-stock-50day", summary="50일합계 데이터 수동 동기화")
def sync_stock_50day():
    result = process_stock_50day_data()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result

@router.post("/sync-stock-day", summary="일별 데이터 수동 동기화")
def sync_stock_day_data():
    result = process_stock_day_data()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result