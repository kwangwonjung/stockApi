from datetime import datetime
import json
import os
from core.config import ETF_URL, INDEX_URL, STOCK_URL, URL
from core.database import supabase
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

load_dotenv()

service_key = os.getenv("SERVICE_KEY", "")


def process_stock_day_data(
    dtStockStartBaseDt_text, dtStockEndBaseDt_value, bstockSum=True
):
  """주식 일별 데이터를 수집하고 Supabase에 업서트하는 메인 함수"""
  try:
    # 1. 대상 주식/종목 목록 조회 (Supabase RPC 호출)
    params = {"p_stock_name": ""}
    response = supabase.rpc("stock_mt_std_select", params).execute()
    rows = response.data

    if not rows:
      return {
          "status": "success",
          "message": "조회된 주식 데이터가 없습니다.",
          "count": 0,
      }

    # 2. 날짜 계산
    strStartDate = dtStockStartBaseDt_text.replace("/", "") + "01"

    end_date_plus_1 = dtStockEndBaseDt_value + relativedelta(months=1)
    strEndDate = end_date_plus_1.strftime("%Y%m") + "01"

    strEndDate2 = dtStockEndBaseDt_value.strftime("%Y%m")

    # 3. set_day_data 함수 호출 (C#의 setDayData 역할)
    result = set_day_data(
        rows, strStartDate, strEndDate, strEndDate2, bstockSum
    )

    return result

  except Exception as e:
    return {"status": "error", "message": str(e)}


def set_day_data(rows, beginBasDt, endBasDt, strEndDate2, bstockSum):
  """C#의 setDayData 메서드 구조를 반영한 데이터 처리 및 업서트 함수"""

  headers = {
      "user-agent": (
          "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.2; .NET CLR"
          " 1.0.3705;)"
      )
  }

  # 네트워크 불안정 및 타임아웃 대응을 위한 세션 및 자동 재시도 설정
  session = requests.Session()
  retries = Retry(
      total=3,
      backoff_factor=1,
      status_forcelist=[500, 502, 503, 504],
  )
  session.mount("https://", HTTPAdapter(max_retries=retries))

  success_count = 0

  # 각 종목별 데이터 순회 및 처리
  for dr in rows:
    strStockCode = str(dr.get("stock_code", ""))
    stockGubn = str(dr.get("stock_gubn", ""))

    try:
      targetURL = ""
      likeSrtnCd = ""

      # URL 조건 분기
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

      # API 요청
      res = session.get(targetURL, headers=headers, timeout=(20, 60))
      if res.status_code != 200:
        print(
            f"⚠️ [API 응답 에러] 종목코드: {strStockCode} | 상태코드:"
            f" {res.status_code}"
        )
        continue

      r = res.json()
      item_list = (
          r.get("response", {}).get("body", {}).get("items", {}).get("item")
      )

      if not item_list:
        continue

      if isinstance(item_list, dict):
        item_list = [item_list]

      # 일별 데이터 업서트
      for o in item_list:
        iht = {
            "p_stock_code": strStockCode,
            "p_yyyymmdd": str(o.get("basDt", "")),
            "p_close_price": str(o.get("clpr", "")),
        }
        supabase.rpc("stock_upsert", iht).execute()
        

      # 요약 데이터 업서트 (bstockSum이 True인 경우)
      if bstockSum:
        is_today = strEndDate2.upper() == "TODAY"
        ht2 = {
            "p_stock_code": strStockCode,
            "p_from_yyyymmdd": beginBasDt,
            "p_to_yyyymmdd": strEndDate2,
            "p_gubn": "TODAY" if is_today else "",
        }
        supabase.rpc("stock_sum_upsert", ht2).execute()
        success_count += 1

    except Exception as e:
      # 💡 특정 종목 처리 중 에러 발생 시 어떤 종목에서 문제가 생겼는지 터미널에 명확히 출력
      print(
          f"❌ [에러 발생 종목] 종목코드: {strStockCode} | 에러 내용: {str(e)}"
      )
      continue

  return {
      "status": "success",
      "message": "생성되었습니다.",
      "processed_count": success_count,
  }