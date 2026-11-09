# core/database.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY") 

# 공용으로 사용할 수 있는 supabase 클라이언트 생성
supabase: Client = create_client(url, key)