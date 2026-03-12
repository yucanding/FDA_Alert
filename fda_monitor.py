import requests
import yfinance as yf
from bs4 import BeautifulSoup
import time
import re
import os

# --- 配置 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')
ID_FILE = "last_fda_ids.txt"

def get_verified_stock_data(company_name):
    """通过 yfinance 搜索并校验美股身份"""
    try:
        search = yf.Search(company_name, max_results=3)
        if not search.quotes:
            return None
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
    except:
        return None

def send_tg_message(text):
    if not TG_TOKEN or not TG_CHAT_ID or not text: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    # 使用 POST 发送，确保长文本能正常传输
    requests.post(url, json={
        "chat_id": TG_CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True
    })

def main():
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
        new_items_list = []
        current_all_ids = list(old_ids)

        for header in date_headers:
            date_str = header.get_text(strip=True)
            table = header.find_next('table')
            if not table: continue
            
            for row in table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                submission = cols[3].get_text(strip=True).upper()
                if submission != "ORIG-1": continue

                link_tag = cols[0].find('a')
                appl_no = re.search(r'ApplNo=(\d+)', link_tag['href']).group(1) if link_tag else ""
                
                if appl_no and appl_no not in old_ids:
                    company = cols[4].get_text(strip=True)
                    stock = get_verified_stock_data(company)
                    
                    if stock:
                        drug_name = cols[0].get_text(strip=True).split('\n')[0]
                        fda_link = f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={appl_no}"
                        
                        # 中文模板，无加粗
                        item_msg = (f"💊FDA新药获批❗\n"
                                    f"📅日期: {date_str}\n"
                                    f"🎫代码: ${stock['ticker']}\n"
                                    f"🏢公司: {company}\n"
                                    f"💰市值: ${stock['market_cap']:.2f}B\n"
                                    f"💵股价: ${stock['price']:.2f}\n"
                                    f"🔗链接: {fda_link}")
                        
                        new_items_list.append(item_msg)
                        current_all_ids.append(appl_no)
                    
                    time.sleep(1)

        # 合并推送逻辑
        if new_items_list:
            # 用分隔线将多个条目拼接成一条消息
            combined_message = "\n\n------------------\n\n".join(new_items_list)
            send_tg_message(combined_message)
            
            with open(ID_FILE, "w") as f:
                f.write("\n".join(current_all_ids[-200:]))
        else:
            print("没有发现新的美股上市公司 ORIG-1 获批。")

    except Exception as e:
        print(f"执行出错: {e}")

if __name__ == "__main__":
    main()