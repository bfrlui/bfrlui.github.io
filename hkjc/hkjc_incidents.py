import requests
import json
import time
from bs4 import BeautifulSoup

base_url = "https://racing.hkjc.com/zh-hk/local/information/racereportext?racedate=2026/07/04&Racecourse=ST&RaceNo="
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

hkjc_incidents_data = {}

print("🌐 啟動馬會網頁版「各駒上次競賽事件摘要雷達」...")

for race_no in range(1, 13):  # 完整跑完 1 至 12 場
    race_key = f"第 {race_no} 場"
    url = f"{base_url}{race_no}"
    print(f"🔄 正在精準解析：{race_key} 競賽事件摘要...")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"⚠️ {race_key} 請求失敗 (Status Code: {response.status_code})")
            continue
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # 🌟 精準錨定修正：改用網頁實際存在的「烙號」與「描述」進行定位
        target_table = None
        for t in soup.find_all("table"):
            table_text = t.get_text()
            if "烙號" in table_text and "描述" in table_text:
                target_table = t
                break
                
        if not target_table:
            print(f"ℹ️ {race_key} 未發現符合特徵的事件摘要表格。")
            continue
            
        rows = target_table.find_all("tr")
        race_incidents = []
        
        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue
                
            cells = [td.get_text(strip=True) for td in tds]
            
            # 安全過濾：確保欄位數量達到 6 欄，且第一欄必須是數字（馬號）
            if len(cells) >= 6 and cells[0].isdigit():
                incident_entry = {
                    "馬號": cells[0],
                    "烙號": cells[1],
                    "馬名": cells[2],
                    "上次事件日期": cells[3],
                    "上次場次": cells[4],
                    "競賽事件摘要": cells[5]
                }
                race_incidents.append(incident_entry)
        
        if race_incidents:
            # 依馬號排序，確保結構整齊
            race_incidents.sort(key=lambda x: int(x["馬號"]))
            hkjc_incidents_data[race_key] = race_incidents
            print(f"✅ {race_key} 事件摘要解析成功！共收錄 {len(race_incidents)} 匹馬。")
        else:
            print(f"ℹ️ {race_key} 表格內無有效的馬匹事件數據。")
            
    except Exception as e:
        print(f"💥 解析 {race_key} 時發生重大錯誤: {e}")
        
    time.sleep(1)

# 儲存為格式完美的 JSON 檔案
output_json = "hkjc_incidents_perfect.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(hkjc_incidents_data, f, ensure_ascii=False, indent=4)

print(f"\n🎉 競賽事件摘要數據成功全量落地：{output_json}")