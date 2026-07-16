import requests
from bs4 import BeautifulSoup
import json
import time
import os
import sys

def run_one_shot_formline(race_date, total_races=11):
    """
    一鍵式自動化函數：直接連線馬會抓取網頁，並在記憶體中同步進行動態表頭對齊與結構化拆解。
    運行一次，直接產出最終機器學習級別的 JSON 檔案。
    
    :param race_date: 賽事日期，格式必須為 "YYYY/MM/DD" (例如 "2026/06/13")
    :param total_races: 當天賽事的總場數，預設抓取 11 場
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8'
    }
    
    ultimate_formline_data = {}
    
    print(f"🎬 【自動化啟動】開始爬取並同步精煉 {race_date} 的同場對壘數據...")
    
    for race_no in range(1, total_races + 1):
        race_key = f"第 {race_no} 場"
        ultimate_formline_data[race_key] = []
        
        # 構建馬會官方同場對壘網頁 URL
        url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/FormLine.aspx?RaceDate={race_date}&RaceNo={race_no}"
        print(f"📡 正在請求: {race_key} -> {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'  # 強制指定編碼，防止中文亂碼
            
            if response.status_code != 200:
                print(f"⚠️  {race_key} 網頁請求失敗 (狀態碼: {response.status_code})，跳過此場次。")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 安全錨定機制：直接撈取頁面上所有表格行 tr 進行通用平鋪掃描
            all_trs = soup.find_all('tr')
            
            current_meeting_info = {}
            headers_list = None
            horses_list = []
            has_valid_rows = False
            
            for tr in all_trs:
                # 乾淨擷取整行所有單元格的文字，過濾掉純空白
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th']) if td.get_text(strip=True)]
                if not cells:
                    continue
                
                # 【特徵識別 1】：識別歷史賽事元數據行 (特徵：長度短，且首欄包含日期 '/' 或年份 '202')
                if len(cells) <= 6 and any(k in str(cells[0]) for k in ["/", "202"]):
                    
                    # 狀態機斷點：在更換下一場歷史賽事之前，如果已有累積的馬匹數據，先封包結算
                    if headers_list and horses_list:
                        ultimate_formline_data[race_key].append({
                            "歷史對壘賽事": current_meeting_info,
                            "對壘馬匹表現": horses_list
                        })
                    
                    # 即時解構並精煉賽事基本資訊
                    current_meeting_info = {
                        "日期場次": str(cells[0]).strip() if len(cells) > 0 else "",
                        "場地": str(cells[1]).strip() if len(cells) > 1 else "",
                        "途程": str(cells[2]).strip() if len(cells) > 2 else "",
                        "班次": str(cells[3]).strip() if len(cells) > 3 else "",
                        "跑道": str(cells[4]).strip().replace('"', '') if len(cells) > 4 else "",
                        "路況": str(cells[5]).strip() if len(cells) > 5 else ""
                    }
                    
                    # 重置局部狀態
                    headers_list = None
                    horses_list = []
                    has_valid_rows = True
                
                # 【特徵識別 2】：識別動態表頭行
                elif "馬名" in cells and "負磅" in cells:
                    headers_list = [str(h).strip() for h in cells]
                    
                # 【特徵識別 3】：識別實體馬匹數據行
                else:
                    if headers_list and "馬名" in headers_list:
                        # 確保該行欄位數量合理（避免雜訊干擾）
                        if len(cells) >= min(3, len(headers_list)):
                            horse_dict = {}
                            # 動態精準對齊「表頭鍵」與「數據值」
                            for i in range(min(len(headers_list), len(cells))):
                                horse_dict[headers_list[i]] = str(cells[i]).strip()
                            horses_list.append(horse_dict)
            
            # 迴圈結束後，補償寫入最後一場殘留的歷史交鋒
            if headers_list and horses_list:
                ultimate_formline_data[race_key].append({
                    "歷史對壘賽事": current_meeting_info,
                    "對壘馬匹表現": horses_list
                })
            
            if not has_valid_rows:
                print(f"ℹ️  {race_key} 網頁解析完成，但本日此場可能無同場對壘歷史紀錄。")
                
            # 頻率保護：禮貌型爬蟲，每次請求完休息 1.5 秒，避免觸發馬會防火牆 (WAF)
            time.sleep(1.5)
            
        except Exception as e:
            print(f"❌ 抓取 {race_key} 時發生非預期異常: {e}")
            continue

    # 定義輸出的最終終極 JSON 檔名
    date_str = race_date.replace('/', '')
    output_filename = f"hkjc_formline_ultimate.json"
    
    print(f"💾 正在將精煉後的數據直接寫入檔案...")
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(ultimate_formline_data, f, ensure_ascii=False, indent=4)
        
    print(f"\n🎉 【一鍵大功告成】最終極結構化 JSON 檔案已直接生成：'{output_filename}'")

if __name__ == "__main__":
    # 從命令列讀取目標賽事日期 (請嚴格保持 YYYY/MM/DD 格式)
    # 用法: python hkjc_formline.py 2026/07/12 [total_races]
    if len(sys.argv) < 2:
        print("❌ 請提供目標賽事日期，格式為 YYYY/MM/DD")
        print("用法: python hkjc_formline.py 2026/07/12 [total_races]")
        sys.exit(1)

    TARGET_DATE = sys.argv[1]

    total_races = 11
    if len(sys.argv) >= 3:
        try:
            total_races = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  場次數 '{sys.argv[2]}' 無效，使用預設值 {total_races}")

    # 執行一鍵式腳本
    run_one_shot_formline(TARGET_DATE, total_races=total_races)  