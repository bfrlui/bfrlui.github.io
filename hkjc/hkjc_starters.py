import requests
import json
import re
import time
from bs4 import BeautifulSoup

base_url = "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/07/04&Racecourse=ST&RaceNo="
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

brand_pattern = re.compile(r'[A-Z]\d{3}')
hkjc_structured_data = {}

print("🌐 啟動馬會網頁版「結構化精準雷達」...")

for race_no in range(1, 12):
    race_key = f"第 {race_no} 場"
    url = f"{base_url}{race_no}"
    print(f"🔄 正在精準解析：{race_key}...")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            continue
            
        soup = BeautifulSoup(response.content, "html.parser")
        rows = soup.find_all("tr")
        race_horses = []
        
        for row in rows:
            # 1. 抓取該行所有 td，故意不使用 'if c'，確保完美保留空欄位
            cells = [re.sub(r'\s+', ' ', td.get_text().strip()) for td in row.find_all("td")]
            
            # 2. 嚴格過濾：馬會排位表標準行至少有 26-27 個 td，且第一個元素必須是數字（馬號）
            if len(cells) >= 26 and cells[0].isdigit():
                # 如果長度稍微不足 27，自動補齊空字串防呆
                while len(cells) < 27:
                    cells.append("")
                
                # 3. 依據官方網頁欄位順序，進行 100% 精準對齊與中文鍵值化對應
                horse_entry = {
                    "馬號": cells[0],
                    "6次近績": cells[1],
                    "馬名": cells[3],
                    "烙印編號": cells[4],
                    "負磅": cells[5],
                    "騎師": cells[6],
                    "可能超磅": cells[7],
                    "檔位": cells[8],
                    "練馬師": cells[9],
                    "國際評分": cells[10],
                    "評分": cells[11],
                    "評分+/-": cells[12],
                    "排位體重": cells[13],
                    "排位體重+/-": cells[14],
                    "最佳時間": cells[15],
                    "馬齡": cells[16],
                    "分齡讓磅": cells[17],
                    "性別": cells[18],
                    "今季獎金": cells[19],
                    "優先參賽次序": cells[20],
                    "上賽距今日數": cells[21],
                    "配備": cells[22],
                    "馬主": cells[23],
                    "父系": cells[24],
                    "母系": cells[25],
                    "進口類別": cells[26]
                }
                race_horses.append(horse_entry)
        
        if race_horses:
            # 依馬號排序
            race_horses.sort(key=lambda x: int(x["馬號"]))
            hkjc_structured_data[race_key] = race_horses
            print(f"✅ {race_key} 解析成功！共收錄 {len(race_horses)} 匹參賽馬。")
            
    except Exception as e:
        print(f"💥 解析 {race_key} 時發生錯誤: {e}")
        
    time.sleep(1)

# 儲存為終極結構化 JSON
output_json = "hkjc_starters_perfect.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(hkjc_structured_data, f, ensure_ascii=False, indent=4)

print(f"\n🎉 完美落地！請檢查新生成的：{output_json}")