
"""
DART 공시 모니터링 → 텔레그램 알림 + 구글 스프레드시트 기록
매일 GitHub Actions로 자동 실행됩니다.
"""

import os
import json
import requests
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

DART_API_KEY       = os.environ["DART_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
GOOGLE_SHEET_ID    = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDS_JSON  = os.environ["GOOGLE_CREDS_JSON"]

REPORT_TYPES = {
    "유상증자결정":         "C002",
    "무상증자결정":         "C003",
    "감자결정":            "C004",
    "합병결정":            "C011",
    "분할결정":            "C012",
    "영업양수도결정":       "C009",
    "자기주식취득결정":     "C007",
    "전환사채발행결정":     "C014",
    "신주인수권부사채발행": "C015",
}

def fetch_disclosures(bgn_de, end_de):
    url = "https://opendart.fss.or.kr/api/list.json"
    all_items = []
    for report_name, pblntf_ty in REPORT_TYPES.items():
        params = {
            "crtfc_key": DART_API_KEY,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "pblntf_detail_ty": pblntf_ty,
            "page_no": "1",
            "page_count": "100",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "000" and data.get("list"):
            for item in data["list"]:
                item["_report_category"] = report_name
            all_items.extend(data["list"])
    return all_items

def send_telegram(items):
    if not items:
        print("오늘 해당 공시 없음")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    header = f"📢 *DART 주요사항 공시 알림* ({today})\n총 {len(items)}건\n{'─'*30}\n"
    messages = [header]
    for item in items:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
        msg = (
            f"🏢 *{item['corp_name']}* ({item.get('stock_code','비상장')})\n"
            f"📋 {item['_report_category']}\n"
            f"📅 {item['rcept_dt']}\n"
            f"🔗 [공시 보기]({dart_url})\n"
            f"{'─'*30}\n"
        )
        messages.append(msg)
    full_message = ""
    for chunk in messages:
        if len(full_message) + len(chunk) > 3800:
            _send_telegram_message(full_message)
            full_message = chunk
        else:
            full_message += chunk
    if full_message:
        _send_telegram_message(full_message)

def _send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()

def write_to_sheet(items):
    if not items:
        return
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet("공시기록")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="공시기록", rows=1000, cols=8)
        ws.append_row(["접수일", "회사명", "종목코드", "보고서분류", "보고서명", "공시링크", "수집일시"])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for item in items:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
        rows.append([
            item["rcept_dt"],
            item["corp_name"],
            item.get("stock_code", "비상장"),
            item["_report_category"],
            item["report_nm"],
            dart_url,
            now_str,
        ])
    ws.append_rows(rows, value_input_option="USER_ENTERED")

def main():
    today = datetime.now()
    if today.weekday() == 0:
        bgn_de = (today - timedelta(days=3)).strftime("%Y%m%d")
    else:
        bgn_de = (today - timedelta(days=1)).strftime("%Y%m%d")
    end_de = (today - timedelta(days=1)).strftime("%Y%m%d")
    items = fetch_disclosures(bgn_de, end_de)
    send_telegram(items)
    write_to_sheet(items)

if __name__ == "__main__":
    main()
