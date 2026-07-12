import requests
import json
import re
import time
import sys
from bs4 import BeautifulSoup

# 從命令列讀取 racedate 與 Racecourse
# 用法: python hkjc_trackwork.py 2026/07/08 HV
if len(sys.argv) < 3:
    print("❌ 請提供 racedate 與 Racecourse")
    print("用法: python hkjc_trackwork.py <racedate YYYY/MM/DD> <Racecourse 例如 ST/HV>")
    sys.exit(1)

RACEDATE = sys.argv[1]
RACECOURSE = sys.argv[2]

base_url = f"https://racing.hkjc.com/zh-hk/local/information/localtrackwork?racedate={RACEDATE}&Racecourse={RACECOURSE}&RaceNo="
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

hkjc_trackwork_data = {}

print("🌐 啟動馬會網頁版「晨操數據精準雷達 (完美修復版)」...")

for race_no in range(1, 12):
    race_key = f"第 {race_no} 場"
    url = f"{base_url}{race_no}"
    print(f"🔄 正在精準解析：{race_key} 晨操資料...")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"⚠️ {race_key} 請求失敗 (Status Code: {response.status_code})")
            continue
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # 定位核心數據表
        target_table = None
        for t in soup.find_all("table"):
            table_text = t.get_text()
            if "快操" in table_text and "踱步" in table_text:
                target_table = t
                break
                
        if not target_table:
            print(f"⚠️ {race_key} 找不到包含晨操特徵的數據表格")
            continue
            
        rows = target_table.find_all("tr")
        race_horses = []
        
        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue
                
            # 解析單個格子內的所有行
            cells = []
            for td in tds:
                lines = [line.strip() for line in td.get_text(separator="\n").split("\n") if line.strip()]
                cells.append(lines)
            
            # 過濾機制
            if len(cells) >= 2 and cells[0] and cells[0][0].isdigit():
                horse_no = cells[0][0]
                
                # 🌟 修正 1：依據陣列長度，精準解構馬名、練馬師與近績
                info_cell = cells[1]
                horse_name = ""
                trainer = ""
                last_6_runs = ""
                
                if len(info_cell) == 1:
                    horse_name = info_cell[0]
                elif len(info_cell) == 2:
                    horse_name = info_cell[0]
                    trainer = info_cell[1]
                elif len(info_cell) >= 3:
                    horse_name = info_cell[0]
                    trainer = info_cell[1]
                    last_6_runs = info_cell[2]
                
                # 🌟 修正 2：時序重組函數（將被斷行的日期與內容重新縫合）
                def reassemble_trackwork(lines_list):
                    combined = []
                    current_record = ""
                    for line in lines_list:
                        # 如果行首符合日期格式 (例如 02/07:)，代表新一條紀錄開始
                        if re.match(r'^\d{2}/\d{2}:', line):
                            if current_record:
                                combined.append(current_record)
                            current_record = line
                        else:
                            if current_record:
                                # 將內容無縫接在日期後面
                                current_record += " " + line
                            else:
                                current_record = line
                    if current_record:
                        combined.append(current_record)
                    return combined
                
                # 安全分配各個操練欄位並進行重組
                trial = reassemble_trackwork(cells[2]) if len(cells) > 2 else []
                fast_work = reassemble_trackwork(cells[3]) if len(cells) > 3 else []
                trotting = reassemble_trackwork(cells[4]) if len(cells) > 4 else []
                swimming = reassemble_trackwork(cells[5]) if len(cells) > 5 else []
                treadmill = reassemble_trackwork(cells[6]) if len(cells) > 6 else []
                water_treadmill = reassemble_trackwork(cells[7]) if len(cells) > 7 else []
                resting = reassemble_trackwork(cells[8]) if len(cells) > 8 else []
                
                horse_entry = {
                    "馬號": horse_no,
                    "馬名": horse_name,
                    "練馬師": trainer,
                    "6次近績": last_6_runs,
                    "試閘": trial,
                    "快操": fast_work,
                    "踱步": trotting,
                    "游泳": swimming,
                    "馬匹跑步機": treadmill,
                    "馬匹水中步行機": water_treadmill,
                    "休歇": resting
                }
                race_horses.append(horse_entry)
        
        if race_horses:
            race_horses.sort(key=lambda x: int(x["馬號"]))
            hkjc_trackwork_data[race_key] = race_horses
            print(f"✅ {race_key} 晨操解析成功！共收錄 {len(race_horses)} 匹馬。")
            
    except Exception as e:
        print(f"💥 解析 {race_key} 晨操時發生錯誤: {e}")
        
    time.sleep(1)

# 儲存最終完美的 JSON
output_json = "hkjc_trackwork_perfect.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(hkjc_trackwork_data, f, ensure_ascii=False, indent=4)

print(f"\n🎉 【完美修正版】晨操數據已成功落地：{output_json}")