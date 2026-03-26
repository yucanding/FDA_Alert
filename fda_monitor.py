import requests
import yfinance as yf
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime

# --- 配置 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')
ID_FILE = "last_fda_ids.txt"
LAST_SUCCESS_FILE = "last_success_date_drug.txt" # <--- 新增状态文件

def convert_date_to_chinese(date_str):
    try:
        dt = datetime.strptime(date_str, "%B %d, %Y")
        return dt.strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月")
    except:
        return date_str

def get_verified_stock_data(company_name):
    try:
        search = yf.Search(company_name, max_results=3)
        if not search.quotes: return None
        core_name = company_name.split()[0].upper()
        for quote in search.quotes:
            ticker = quote['symbol']
            name = (quote.get('shortname', '') or quote.get('longname', '')).upper()
            if core_name in name and "." not in ticker:
                stock = yf.Ticker(ticker)
                return {
                    "ticker": ticker,
                    "price": stock.fast_info.last_price,
                    "market_cap": stock.fast_info.market_cap / 1e9
                }
        return None
    except: return None

def send_tg_message(text):
    if not TG_TOKEN or not TG_CHAT_ID or not text: return
    target_ids = [chat_id.strip() for chat_id in TG_CHAT_ID.split(',') if chat_id.strip()]
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for chat_id in target_ids:
        try:
            requests.post(url, json={
                "chat_id": chat_id, 
                "text": text, 
                "parse_mode": "HTML", 
                "disable_web_page_preview": True
            }, timeout=10)
        except Exception as e:
            print(f"发送失败: {e}")

def main():
    # --- 1. 今日熔断检查 ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_SUCCESS_FILE):
        with open(LAST_SUCCESS_FILE, "r") as f:
            if f.read().strip() == today_str:
                print(f"📌 今日 ({today_str}) 已成功推送，跳过本次执行。")
                return

    url = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=report.page"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    if os.path.exists(ID_FILE):
        with open(ID_FILE, "r") as f:
            old_ids = set(f.read().splitlines())
    else:
        old_ids = set()

    try:
        response = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        tab_panel = soup.find('div', id='example2-tab2')
        if not tab_panel: return

        date_headers = tab_panel.find_all('h4')
        records_to_send = []
        current_all_ids = list(old_ids)

        for header in date_headers:
            raw_date = header.get_text(strip=True)
            chinese_date = convert_date_to_chinese(raw_date)
            table = header.find_next('table')
            if not table: continue
            
            for row in table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                submission = cols[3].get_text(strip=True).upper()
                if submission != "ORIG-1": continue

                full_drug_text = cols[0].get_text(separator="\n", strip=True)
                drug_name_only = full_drug_text.split('\n')[0].strip()
                
                link_tag = cols[0].find('a')
                appl_no = ""
                if link_tag and 'href' in link_tag.attrs:
                    match = re.search(r'ApplNo=(\d+)', link_tag['href'])
                    if match: appl_no = match.group(1)
                
                if appl_no and appl_no not in old_ids:
                    company = cols[4].get_text(strip=True)
                    stock = get_verified_stock_data(company)
                    
                    if stock:
                        fda_link = f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={appl_no}"
                        records_to_send.append({
                            "date": chinese_date,
                            "ticker": stock['ticker'],
                            "company": company,
                            "drug": drug_name_only,
                            "cap": stock['market_cap'],
                            "price": stock['price'],
                            "link": fda_link
                        })
                    current_all_ids.append(appl_no)
                    time.sleep(1)

        # 统一组装并发送消息
        if records_to_send:
            final_msg = f"<b>🧬 FDA新药获批更新 ({len(records_to_send)}家上市企业)</b>\n\n"
            msg_blocks = []
            for idx, item in enumerate(records_to_send, 1):
                block = (f"{idx}. 📅日期: {item['date']}\n"
                         f"    🏢公司: ${item['ticker']} ({item['company']})\n"
                         f"    💊药品: {item['drug']}\n"
                         f"    💰市值: ${item['cap']:.2f}B\n"
                         f"    💵股价: ${item['price']:.2f}\n"
                         f'    🔗<a href="{item["link"]}">点击查看公告</a>')
                msg_blocks.append(block)
            
            final_msg += "\n\n---------------\n\n".join(msg_blocks) + "\n\n#FDA #DrugApproval"
            send_tg_message(final_msg)
            
            # 记录成功状态
            with open(LAST_SUCCESS_FILE, "w") as f:
                f.write(today_str)
            
            with open(ID_FILE, "w") as f:
                f.write("\n".join(current_all_ids[-200:]))
        else:
            print("💡 本次扫描没有发现新的获批。")

    except Exception as e:
        print(f"🛑 运行发生异常: {e}")

if __name__ == "__main__":
    main()
