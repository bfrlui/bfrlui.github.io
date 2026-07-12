import requests
from bs4 import BeautifulSoup
import json
import time

def run_exceptional_factors_v4(race_date, racecourse="ST", total_races=11):
    """
    【V4 行雙軌掃描版】特別因素與同廄馬匹全能對齊器
    直接採用行級（tr）雷達掃描，完美破解橫向動態多欄位與外層嵌套表格盲點。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8'
    }
    
    exceptional_dataset = {}
    print(f"🎬 【特別因素+同廄戰術 V4 行雙軌掃描】開始處理 {race_date} ({racecourse}) 的核心數據...")
    
    for race_no in range(1, total_races + 1):
        race_key = f"第 {race_no} 場"
        
        # 初始化結構
        exceptional_dataset[race_key] = {
            "個別馬匹因素": [],
            "同廄馬匹摘要": []
        }
        
        url = f"https://racing.hkjc.com/zh-hk/local/information/exceptionalfactors?racedate={race_date}&Racecourse={racecourse}&RaceNo={race_no}"
        print(f"📡 正在請求: {race_key} -> {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                print(f"⚠️  {race_key} 網頁請求失敗，跳過。")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            list_main = []
            list_stable = []
            multi_entry_horse_ids = set() # 儲存這場所有同廄出擊的馬號
            headers_list = None
            
            # 直接提取頁面所有的 tr 行進行流式掃描，完全無視表格嵌套層級
            for tr in soup.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if not cells or not any(cells):
                    continue
                
                # 【軌道一：個別馬匹變更因素表頭識別】
                if "馬名" in cells and ("馬號" in cells or "編號" in cells):
                    headers_list = [str(h).strip() for h in cells]
                    continue
                    
                # 【軌道一數據行：首欄為數字（馬號）】
                if headers_list and cells[0].isdigit():
                    horse_factors = {}
                    for i in range(min(len(headers_list), len(cells))):
                        key = headers_list[i]
                        val = str(cells[i]).strip()
                        if val in ["---", "--", "-", "無", ""]:
                            val = ""
                        if val != "":
                            horse_factors[key] = val
                            
                    if len(horse_factors) > 2: # 確保不只抓到馬號馬名，必須有實質特徵變更
                        list_main.append(horse_factors)
                    continue
                
                # 【軌道二數據行：處理同廄馬匹戰術（首欄為練馬師中文名，非數字）】
                if len(cells) >= 2 and not cells[0].isdigit():
                    # 安全過濾：跳過頁面所有的中英文表頭、說明文字、版權資訊
                    if any(h in cells[0] for h in ["練馬師", "馬號", "馬名", "特別因素", "編號", "日期", "版權"]):
                        continue
                    
                    # 掃描後續欄位，動態提取馬匹（馬會格式通常為 "02 全能勇士" 或 "2 全能勇士"）
                    horses_found = []
                    for cell in cells[1:]:
                        c_str = cell.strip()
                        if not c_str:
                            continue
                        
                        # 利用「前導數字提取法」驗證此格子是否為馬匹格，並抓出馬號
                        prefix_no = ""
                        for char in c_str:
                            if char.isdigit():
                                prefix_no += char
                            else:
                                break
                        if prefix_no:
                            horses_found.append(prefix_no)
                    
                    # 如果成功在這個中文開頭的行裡找到了馬匹號碼，說明這是一行正確的「同廄戰術行」
                    if horses_found:
                        trainer = cells[0]
                        for h_no in horses_found:
                            multi_entry_horse_ids.add(int(h_no))
                            
                        list_stable.append({
                            "練馬師": trainer,
                            "馬號": ", ".join(horses_found) # 重新組合成標準格式 "02, 03, 05"
                        })
            
            # ----------------------------------------------------
            # 【雙軌交叉反向對齊】
            # ----------------------------------------------------
            for horse in list_main:
                h_no = horse.get("馬號", "")
                if h_no.isdigit() and int(h_no) in multi_entry_horse_ids:
                    horse["同廄多駒出戰"] = "是"
            
            # 寫入本場資料庫
            exceptional_dataset[race_key]["個別馬匹因素"] = list_main
            exceptional_dataset[race_key]["同廄馬匹摘要"] = list_stable
            
            print(f"✅ {race_key} 解析成功! (變更馬匹: {len(list_main)} 隻 | 同廄戰術: {len(list_stable)} 組)")
            time.sleep(1.5)
            
        except Exception as e:
            print(f"❌ 抓取 {race_key} 發生非預期異常: {e}")
            continue

    clean_date = race_date.replace('/', '')
    output_filename = f"hkjc_exceptional_ultimate.json"
    
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(exceptional_dataset, f, ensure_ascii=False, indent=4)
        
    print(f"\n🎉 【V4 行掃描雙軌對齊完成】最終數據集已成功覆蓋生成：'{output_filename}'")

if __name__ == "__main__":
    import sys  # 🛠️ 確保引入系統參數模組

    # 用法: python hkjc_exceptional.py <賽事日期> <馬場代碼> [總場次]
    # 例:   python hkjc_exceptional.py 2026/07/12 ST 11
    TARGET_DATE = "2026/07/08"  # 設定預設賽事日期
    RACECOURSE = "HV"           # 設定預設馬場代碼
    TOTAL_RACES = 11            # 設定預設總場次

    if len(sys.argv) > 1:
        TARGET_DATE = sys.argv[1]
    if len(sys.argv) > 2:
        RACECOURSE = sys.argv[2]
    if len(sys.argv) > 3:
        try:
            TOTAL_RACES = int(sys.argv[3])
        except ValueError:
            print(f"❌ 錯誤：總場次 '{sys.argv[3]}' 不是有效數字，使用預設 {TOTAL_RACES} 場。")

    print(f"📅 賽事日期: {TARGET_DATE}　🏟️ 馬場代碼: {RACECOURSE}　🏁 總場次: {TOTAL_RACES}")
    run_exceptional_factors_v4(TARGET_DATE, racecourse=RACECOURSE, total_races=TOTAL_RACES)