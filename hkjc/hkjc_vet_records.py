import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime

def calculate_days_between(date_str1, date_str2):
    """計算兩個日期字串之間的相隔天數 (格式: DD/MM/YYYY 或 YYYY/MM/DD)"""
    if not date_str1 or not date_str2:
        return None
    try:
        # 嘗試解析 DD/MM/YYYY
        d1 = datetime.strptime(date_str1, "%d/%m/%Y") if "/" in date_str1 and len(date_str1.split('/')[2]) == 4 else datetime.strptime(date_str1, "%Y/%m/%d")
        d2 = datetime.strptime(date_str2, "%d/%m/%Y") if "/" in date_str2 and len(date_str2.split('/')[2]) == 4 else datetime.strptime(date_str2, "%Y/%m/%d")
        return abs((d2 - d1).days)
    except Exception:
        return None

def run_veterinary_records_v2(race_date, racecourse="ST", total_races=11):
    """
    【傷患紀錄高級特徵優化器 V2】
    1. 標準化後備馬 Schema (統一改為"馬號")
    2. 自動衍生機器學習核心時間特徵: 傷患距今日數、康復耗時
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8'
    }
    
    vet_dataset = {}
    print(f"🎬 【傷患紀錄 V2 高級特徵雷達】啟動。目標賽日: {race_date}")
    
    for race_no in range(1, total_races + 1):
        race_key = f"第 {race_no} 場"
        vet_dataset[race_key] = []
        
        url = f"https://racing.hkjc.com/zh-hk/local/information/veterinaryrecord?racedate={race_date}&Racecourse={racecourse}&RaceNo={race_no}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            if response.status_code != 200: continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            headers_list = None
            race_records = []
            
            for tr in soup.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if not cells or not any(cells): continue
                
                # 捕獲表頭
                if "馬名" in cells and any(k in "".join(cells) for k in ["傷患", "獸醫", "檢驗", "詳情"]):
                    headers_list = [str(h).strip() for h in cells]
                    continue
                
                # 提取數據
                if headers_list and cells[0].isdigit():
                    raw_info = {}
                    for i in range(min(len(headers_list), len(cells))):
                        raw_info[headers_list[i]] = str(cells[i]).strip()
                    
                    if len(raw_info) <= 2: continue
                    
                    # ------ 🧠 核心特徵工程 & Schema 標準化開始 ------
                    standardized_info = {}
                    
                    # 1. 識別並標準化後備馬與主力馬的 ID
                    is_standby = "否"
                    horse_id = ""
                    if "馬號" in raw_info:
                        horse_id = raw_info["馬號"].zfill(2) # 補齊雙位數如 "03"
                    elif "編號" in raw_info:
                        horse_id = raw_info["編號"].zfill(2)
                        is_standby = "是"
                        
                    standardized_info["馬號"] = horse_id
                    standardized_info["是否後備馬"] = is_standby
                    standardized_info["馬名"] = raw_info.get("馬名", "")
                    
                    # 2. 清洗日期與文字描述
                    injury_date = raw_info.get("日期", raw_info.get("傷患紀錄", ""))
                    pass_date = raw_info.get("通過日期", raw_info.get("通過獸醫檢驗日期", ""))
                    
                    if injury_date in ["---", "--", "-", "無", ""]: injury_date = ""
                    if pass_date in ["---", "--", "-", "無", ""]: pass_date = ""
                        
                    standardized_info["傷患日期"] = injury_date
                    standardized_info["傷患詳情"] = " ".join(raw_info.get("詳情", raw_info.get("傷患紀錄", "")).split())
                    standardized_info["通過檢驗日期"] = pass_date
                    
                    # 3. 衍生量化模型關鍵時間特徵
                    # 特徵 A: 傷患距今相隔日數
                    days_since_injury = calculate_days_between(injury_date, race_date)
                    standardized_info["特徵_傷患距今日數"] = days_since_injury if days_since_injury is not None else -1
                    
                    # 特徵 B: 醫療康復期耗時 (日至)
                    recovery_duration = calculate_days_between(injury_date, pass_date)
                    standardized_info["特徵_康復期耗時天數"] = recovery_duration if recovery_duration is not None else -1
                    
                    race_records.append(standardized_info)
            
            vet_dataset[race_key] = race_records
            print(f"✅ {race_key} 特徵對齊完成! (主力+後備共: {len(race_records)} 隻)")
            time.sleep(1.2)
            
        except Exception as e:
            print(f"❌ {race_key} 異常: {e}")
            continue

    output_filename = f"hkjc_vet_features_v2_20260704.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(vet_dataset, f, ensure_ascii=False, indent=4)
    print(f"\n🎉 恭喜！【V2 高級特徵衍生數據集】已成功打包：'{output_filename}'")

if __name__ == "__main__":
    run_veterinary_records_v2("2026/07/04", racecourse="ST")