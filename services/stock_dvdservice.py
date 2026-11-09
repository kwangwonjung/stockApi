# services/stock_service.py
import os
import requests
from dotenv import load_dotenv
from core.config import URL, DVD_URL
from core.database import supabase

load_dotenv()

service_key = os.getenv("SERVICE_KEY", "")

def process_sync_dividend():
    """배당 정보를 동기화하는 공용 비즈니스 로직 함수"""
    try:
        response = supabase.rpc("dvd_mt_corp_no_select", {}).execute()
        rows = response.data  
        
        if not rows:
            return {"status": "success", "message": "조회된 법인 데이터가 없습니다.", "count": 0}

        str_dvd_url_parent = f"{URL}{DVD_URL}{service_key}"
        headers = {
            "user-agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.2; .NET CLR 1.0.3705;)"
        }

        success_count = 0
        for dr in rows:
            corp_no = dr.get("corp_no")
            str_dvd_url = f"{str_dvd_url_parent}&crno={corp_no}"
            
            res = requests.get(str_dvd_url, headers=headers)
            if res.status_code != 200:
                continue
                
            r = res.json()
            try:
                items = r["response"]["body"]["items"]["item"]
            except (KeyError, TypeError):
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