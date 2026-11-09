# services/stock_service.py
import os
import requests
from dotenv import load_dotenv
from core.config import URL, DVD_URL
from core.database import supabase
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

service_key = os.getenv("SERVICE_KEY", "")

def process_sync_dividend():
    """배당 정보를 동기화하는 공용 비즈니스 로직 함수"""
    try:
        response = supabase.rpc("dvd_mt_corp_no_select", {}).execute()
        
        rows = response.data  

        json_string = json.dumps(rows, ensure_ascii=False, indent=2)
        print(json_string)
        
        if not rows:
            return {"status": "success", "message": "조회된 법인 데이터가 없습니다.", "count": 0}

        str_dvd_url_parent = f"{URL}{DVD_URL}&serviceKey={service_key}"
        headers = {
            "user-agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.2; .NET CLR 1.0.3705;)"
        }

        # [추가] 네트워크 불안정 및 타임아웃 대응을 위한 세션 및 자동 재시도 설정
        session = requests.Session()
        retries = Retry(
            total=3,                # 최대 3회 재시도
            backoff_factor=1,       # 재시도 대기 시간 (1초, 2초, 4초...)
            status_forcelist=[500, 502, 503, 504]
        )
        session.mount('https://', HTTPAdapter(max_retries=retries))

        success_count = 0
        for dr in rows:
            corp_no = dr.get("corp_no")
            str_dvd_url = f"{str_dvd_url_parent}&crno={corp_no}"
            
            try:
                # [추가] 연결 타임아웃(5초), 읽기 타임아웃(30초) 설정 및 예외 처리
                res = session.get(str_dvd_url, headers=headers, timeout=(20, 60))
                if res.status_code != 200:
                    print(f"API 응답 에러 (법인번호: {corp_no}, 상태코드: {res.status_code})")
                    continue
            except requests.exceptions.RequestException as e:
                print(f"API 요청 실패 (법인번호: {corp_no}): {e}")
                continue
                
            try:
                r = res.json()
                items = r["response"]["body"]["items"]["item"]
            except (KeyError, TypeError, ValueError):
                # 데이터가 없거나 형식이 잘못된 경우 건너뜀
                continue
            
            if isinstance(items, dict):
                items = [items]
                
            for o in items:
                ht = {
                    "p_corp_no": str(o.get("crno", "")),
                    "p_stock_name": str(o.get("isinCdNm", "")),
                    "p_kcd_nm": str(o.get("scrsItmsKcdNm", "")),
                    "p_dvd_amt": str(o.get("stckGenrDvdnAmt", "")),
                    "p_dvd_std_day": str(o.get("dvdnBasDt", "")),
                    "p_dvd_pay_day": str(o.get("cashDvdnPayDt", ""))
                }
                supabase.rpc("dvd_mt_upsert", ht).execute()
                success_count += 1

        return {"status": "success", "message": "동기화가 완료되었습니다.", "processed_count": success_count}

    except Exception as e:
        return {"status": "error", "message": str(e)}