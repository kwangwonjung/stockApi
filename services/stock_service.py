from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import os
import time
from core.config import ETF_URL, INDEX_URL, STOCK_URL, URL
from core.database import supabase
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

service_key = os.getenv("SERVICE_KEY", "")


def process_stock_month_data(
    dtStockStartBaseDt_text, dtStockEndBaseDt_value, bstockSum=True
):
  """주식 일별 데이터를 수집하고 Supabase에 업서트하는 메인 함수"""
  try:
    params = {"p_stock_name": ""}
    response = supabase.rpc("stock_mt_std_select", params).execute()
    rows = response.data

    if not rows:
      return {
          "status": "success",
          "message": "조회된 주식 데이터가 없습니다.",
          "count": 0,
      }

    strStartDate = dtStockStartBaseDt_text.replace("/", "") + "01"
    end_date_plus_1 = dtStockEndBaseDt_value + relativedelta(months=1)
    strEndDate = end_date_plus_1.strftime("%Y%m") + "01"
    strEndDate2 = dtStockEndBaseDt_value.strftime("%Y%m")

    result = set_day_data(
        rows, strStartDate, strEndDate, strEndDate2, bstockSum
    )
    return result

  except Exception as e:
    return {"status": "error", "message": str(e)}


def process_stock_50day_data():
  """
    C의 setStockToDayCreate 로직을 반영한 파라미터 없는 일별 데이터 수집 함수
    명칭: process_stock_50day_data
    """
  try:
    params = {"p_stock_name": ""}
    response = supabase.rpc("stock_mt_day_select", params).execute()
    rows = response.data

    if not rows:
      return {
          "status": "success",
          "message": "조회된 주식 데이터가 없습니다.",
          "processed_count": 0,
      }

    strStartDate = str(rows[0].get("yyyymmdd", ""))
    strEndDate = "TODAY"
    gubn = "TODAY"

    result = set_stock_sum_data(
        gubn=gubn,
        beginBasDt=strStartDate,
        strEndDate=strEndDate,
    )
    return result

  except Exception as e:
    return {"status": "error", "message": str(e)}


def process_stock_day_data():
  try:
    params = {"p_stock_name": ""}
    response = supabase.rpc("stock_mt_day_select", params).execute()
    rows = response.data

    if not rows:
      return {
          "status": "success",
          "message": "조회된 주식 데이터가 없습니다.",
          "processed_count": 0,
      }

    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst)

    beginBasDt = (today - timedelta(days=7)).strftime("%Y%m%d")
    endBasDt = (today - timedelta(days=1)).strftime("%Y%m%d")

    result = set_day_data(rows=rows, beginBasDt=beginBasDt, endBasDt=endBasDt)
    return result

  except Exception as e:
    return {"status": "error", "message": str(e)}


def _fetch_single_stock_items(session, headers, dr, beginBasDt, endBasDt):
  """단일 종목의 API 데이터를 호출하여 업서트할 데이터 리스트를 반환하는 내부 워커 함수"""
  strStockCode = str(dr.get("stock_code", ""))
  stockGubn = str(dr.get("stock_gubn", ""))
  upsert_items = []

  try:
    if strStockCode == "KOSPI":
      likeSrtnCd = "&idxNm=코스피&numOfRows=10000"
      targetURL = (
          URL
          + "service/"
          + INDEX_URL
          + "&serviceKey="
          + service_key
          + f"&beginBasDt={beginBasDt}&endBasDt={endBasDt}"
          + likeSrtnCd
      )
    elif stockGubn == "ETF":
      likeSrtnCd = f"&likeSrtnCd={strStockCode}&numOfRows=10000"
      targetURL = (
          URL
          + "service/"
          + ETF_URL
          + "&serviceKey="
          + service_key
          + f"&beginBasDt={beginBasDt}&endBasDt={endBasDt}"
          + likeSrtnCd
      )
    else:
      likeSrtnCd = f"&likeSrtnCd={strStockCode}&numOfRows=10000"
      targetURL = (
          URL
          + "service/"
          + STOCK_URL
          + "&serviceKey="
          + service_key
          + f"&beginBasDt={beginBasDt}&endBasDt={endBasDt}"
          + likeSrtnCd
      )

    # 요청 간 미세 딜레이를 주어 429(초당 호출 제한) 방지
    time.sleep(0.15)
    res = session.get(targetURL, headers=headers, timeout=(15, 45))

    if res.status_code != 200:
      print(
          f"⚠️ [API 응답 에러] 종목코드: {strStockCode} | 상태코드:"
          f" {res.status_code}"
      )
      return strStockCode, False, upsert_items

    r = res.json()
    item_list = (
        r.get("response", {}).get("body", {}).get("items", {}).get("item")
    )

    if not item_list:
      return strStockCode, False, upsert_items

    if isinstance(item_list, dict):
      item_list = [item_list]

    for o in item_list:
      upsert_items.append({
          "p_stock_code": strStockCode,
          "p_yyyymmdd": str(o.get("basDt", "")),
          "p_close_price": str(o.get("clpr", "")),
      })

    return strStockCode, True, upsert_items

  except Exception as e:
    print(
        f"❌ [에러 발생 종목 - 일별 데이터] 종목코드: {strStockCode} | 에러 내용:"
        f" {str(e)}"
    )
    return strStockCode, False, upsert_items


def set_day_data(rows, beginBasDt, endBasDt):
  """공공데이터 TPS 제한(429) 및 윈도우 소켓 충돌(10035)을 방지하면서 속도를 개선한 함수"""

  headers = {
      "user-agent": (
          "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.2; .NET CLR"
          " 1.0.3705;)"
      )
  }

  # 429(Too Many Requests) 발생 시 자동으로 잠시 대기 후 재시도하도록 설정
  session = requests.Session()
  retries = Retry(
      total=5,
      backoff_factor=1.0,
      status_forcelist=[429, 500, 502, 503, 504],
  )
  adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=5)
  session.mount("https://", adapter)

  success_count = 0
  all_upsert_list = []

  # 1단계: 공공데이터 API 트래픽 제한을 넘지 않도록 동시 요청을 3개로 제한
  with ThreadPoolExecutor(max_workers=3) as api_executor:
    futures = [
        api_executor.submit(
            _fetch_single_stock_items, session, headers, dr, beginBasDt, endBasDt
        )
        for dr in rows
    ]

    for future in as_completed(futures):
      _, is_success, items = future.result()
      if is_success:
        success_count += 1
        all_upsert_list.extend(items)

  # 2단계: 윈도우 소켓 충돌(WinError 10035) 방지를 위해 DB 업서트는 단일 스레드로 순차 실행
  # (API 호출이 병렬로 끝났기 때문에 DB 저장만 순차로 해도 전체 시간은 매우 짧습니다)
  for iht in all_upsert_list:
    try:
      supabase.rpc("stock_upsert", iht).execute()
    except Exception as e:
      print(f"❌ [DB 업서트 에러]: {str(e)}")

  return {
      "status": "success",
      "message": "일별 데이터가 생성되었습니다.",
      "processed_count": success_count,
  }


def set_stock_sum_data(gubn, beginBasDt, strEndDate):
  """요약 데이터 처리 및 업서트 함수"""
  try:
    ht2 = {
        "p_gubn": gubn,
        "p_from_yyyymmdd": beginBasDt,
        "p_to_yyyymmdd": strEndDate,
    }
    supabase.rpc("stock_sum_upsert_all", ht2).execute()

    return {
        "status": "success",
        "message": "요약 데이터가 생성되었습니다.",
    }

  except Exception as e:
    print(f"❌ [에러 발생 - 요약 데이터] 에러 내용: {str(e)}")
    return {"status": "error", "message": str(e)}
