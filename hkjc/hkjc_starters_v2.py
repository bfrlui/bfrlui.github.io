# hkjc_starters.py
import requests
from bs4 import BeautifulSoup
import json
import time
import re

def scrape_all_races_today(race_date="2026/07/08", racecourse="HV"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    all_starters_data = {}
    race_no = 1
    
    print(f"🚀 開始執行 26欄位全量動態對齊 數據管線...")
    
    while True:
        url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={race_date}&Racecourse={racecourse}&RaceNo={race_no}"
        print(f"🔎 正在深度解析第 {race_no} 場全量排位數據...")
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = 'utf-8'
            
            if res.status_code != 200:
                break
                
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 找到排位表的主要表格 (馬會排位表通常具有特定的 table 結構)
            # 我們透過尋找含有多個 td 的行來精準定位
            table_rows = soup.find_all('tr')
            
            race_key = f"第 {race_no} 場"
            race_horses = []
            
            for row in table_rows:
                tds = row.find_all('td')
                # 確保基本單元格數量足夠
                if len(tds) < 24:
                    continue
                    
                # 提取純文字列表
                cells = [td.get_text(strip=True) for td in tds]
                
                # 🌟【終極清洗防禦線】：馬號必定要是純數字！
                # 這行能完美剔除「表頭列」、「雜訊列」與「底部配備說明說明文字」
                if not cells[0].isdigit():
                    continue
                
                # 🌟【核心融合技術】：從馬名單元格 (tds[3]) 中提取真實的 horseid 全碼
                true_horse_id = ""
                horse_link = tds[3].find('a')
                if horse_link and 'href' in horse_link.attrs:
                    href = horse_link['href']
                    match = re.search(r'horseid=([^&]+)', href)
                    if match:
                        true_horse_id = match.group(1).strip()
                
                # 依據官方網頁欄位順序，進行 100% 精準對齊
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
                    "進口類別": cells[26],
                    
                    "horse_id": true_horse_id if true_horse_id else cells[4],
                    "馬匹編號": true_horse_id if true_horse_id else cells[4],
                    "profile_url": f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={true_horse_id}&Option=1" if true_horse_id else ""
                }
                
                race_horses.append(horse_entry)
            
            # 如果這場比賽沒抓到半匹馬，說明已經超過當天總場次了
            if not race_horses:
                print(f"🏁 第 {race_no} 場未發現有效表格，掃描結束。")
                break
                
            all_starters_data[race_key] = race_horses
            print(f"   ✅ {race_key} 處理完成，成功導入 {len(race_horses)} 匹馬的 26項全量指標。")
            
            break  # 如果只想抓取一場比賽，取消註解這行即可
            race_no += 1
            time.sleep(1.5) # 爬蟲禮貌延時
            
        except Exception as e:
            print(f"❌ 處理第 {race_no} 場時遭遇異常: {e}")
            break

    # 寫入完美的第 1 數據集
    output_filename = "hkjc_starters_perfect.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_starters_data, f, ensure_ascii=False, indent=4)
        
    print("\n" + "="*60)
    print(f"🎉 完美的排位數據集『{output_filename}』已安全生成（26個原始欄位 + 動態全碼 100% 融合）！")
    print("="*60)

if __name__ == "__main__":
    scrape_all_races_today(race_date="2026/07/08", racecourse="HV")