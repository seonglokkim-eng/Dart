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

# 원하는 보고서명 목록 (정확히 일치하거나 포함된 것만 가져옴)
TARGET_REPORTS = [
    "매출액또는손익구조30%(대규모법인은15%)이상변동",
    "매출액또는손익구조30%(대규모법인은15%)이상변경",
    "공급계약체결",
    "공급계약체결(자진공시)",
    "시설외투자등",
    "시설외투자등(자율공시)",
    "신규시설투자등",
    "신규시설투자등(자율공시)",
    "임원ㆍ주요주주특정증권등소유상황보고서",
    "기업가치제고계획(자율공시)",
    "장래계획에관한사항",
    "수시공시의무관련사항(공정공시)",
    "기타경영사항(자율공시)",
    "주요사항보고서(타법인주식및출자증권양도결정)",
    "주요사항보고서(타법인주식및출자증권양수결정)",
    "주식등의대량보유상황보고서(일반)",
]

def is_target(report_nm):
    # 기재정정 제외
    if "기재정정" in report_nm:
        return False
    # 목록에 있는 보고서명과 일치하는 것만
    for target in TARGET_REPORTS:
        if target == report_nm.strip():
            return True
    return False

def fetch_disclosures(bgn_de, end_de):
    url = "https://opendart.fss.or.kr/api/list.json"
    all_items = []
    page_no = 1

    while True:
        params = {
            "crtfc_key": DART_API_KEY,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": str(page_no),
            "page_count": "100",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "000" or not data.get("list"):
            break

        for item in data["list"]:
            if is_target(item.get("report_nm", "")):
                item["_report_category"] = item["report_nm"]
                all_items.append(item)

        # 마지막 페이지 확인
        total = int(data.get("total_count", 0))
        if page_no * 100 >= total:
            break
        page_no += 1

    return all_items

def send_telegram(items):
    if not items:
        print("해당 공시 없음")
        return

    # 보고서명별로 그룹핑
    groups = {}
    for item in items:
        report_nm = item["report_nm"]
        if report_nm not in groups:
            groups[report_nm] = []
        groups[report_nm].append(item)

    today = datetime.now().strftime("%Y-%m-%d")

    # 보고서명 1건당 메세지 1개
    for report_nm, group_items in groups.items():
        lines = [f"📢 *{report_nm}* ({today})\n"]
        for item in group_items:
            dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
            corp = f"{item['corp_name']}({item.get('stock_code','비상장')})"
            lines.append(f"• {corp} [공시]({dart_url})")
        _send_telegram_message("\n".join(lines))

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
        ws.append_row(["접수일", "회사명", "종목코드", "보고서명", "공시링크", "수집일시"])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for item in items:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}"
        rows.append([
            item["rcept_dt"],
            item["corp_name"],
            item.get("stock_code", "비상장"),
            item["report_nm"],
            dart_url,
            now_str,
        ])
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"스프레드시트 기록 완료: {len(rows)}행 추가")

def main():
    today = datetime.now()
    if today.weekday() == 0:
        bgn_de = (today - timedelta(days=3)).strftime("%Y%m%d")
    else:
        bgn_de = (today - timedelta(days=1)).strftime("%Y%m%d")
    end_de = (today - timedelta(days=1)).strftime("%Y%m%d")

    print(f"조회 기간: {bgn_de} ~ {end_de}")
    items = fetch_disclosures(bgn_de, end_de)
    print(f"수집된 공시 수: {len(items)}")
    send_telegram(items)
    write_to_sheet(items)

if __name__ == "__main__":
    main()
