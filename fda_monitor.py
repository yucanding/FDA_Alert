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

def convert_date_to_chinese(date_str):
    """将英文日期 March 10, 2026 转换为 2026年3月10日"""
    try:
        # FDA 格式通常是 "March 10, 2026"
        dt = datetime.strptime(date_str, "%B %d, %Y")
        return dt.strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月")
    except:
        # 如果解析失败，返回原字符串，确保程序不崩溃
        return date_str

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
            raw_date = header.get_text(strip=True)
            # 💡 转换日期格式
            chinese_date = convert_date_to_chinese(raw_date)
            
            table = header.find_next('table')
            if not table: continue
            
            for row in table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                submission = cols[3].get_text(strip=True).upper()
                if submission != "ORIG-1": continue

                # 提取纯药品名
                full_drug_text = cols[0].get_text(separator="\n", strip=True)
                drug_name_only = full_drug_text.split('\n')[0].strip()
                
                # 提取 ApplNo
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
                        
                        # 组合消息
                        item_msg = (f"❗FDA新药获批 (ORIG-1)❗\n"
                                    f"📅日期: {chinese_date}\n"
                                    f"🏢公司: ${stock['ticker']} ({company})\n"
                                    f"💊药品: {drug_name_only}\n"
                                    f"💰市值: ${stock['market_cap']:.2f}B\n"
                                    f"💵股价: ${stock['price']:.2f}\n"
                                    f"🔗链接: {fda_link}")
                        
                        new_items_list.append(item_msg)
                        current_all_ids.append(appl_no)
                    
                    time.sleep(1)

        if new_items_list:
            combined_message = "\n\n------------------\n\n".join(new_items_list)
            send_tg_message(combined_message)
            
            with open(ID_FILE, "w") as f:
                f.write("\n".join(current_all_ids[-200:]))
        else:
            print("未发现新的美股上市公司获批项目。")

    except Exception as e:
        print(f"出错: {e}")

if __name__ == "__main__":
    main()

