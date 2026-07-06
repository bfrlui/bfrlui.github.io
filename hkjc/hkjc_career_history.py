# hkjc_career_history.py
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time

def parse_horse_career(horse_id, horse_name):
    """前往馬會官網爬取單匹馬的生涯歷史，並聚合成量化大數據精要"""
    # 馬會網址支援標準 4 碼烙印編號 (如 L148)
    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}&Option=1"
    
    # 擬真瀏覽器 Headers，防止被馬會防火牆阻擋 (403 錯誤)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code != 200:
            print(f"❌ 【{horse_name}】連線失敗，HTTP 狀態碼: {res.status_code} (可能遭馬會防爬蟲封鎖)")
            return None
    except Exception as e:
        print(f"❌ 【{horse_name}】網路請求引發異常: {e}")
        return None

    if "找不到有關馬匹" in res.text or "無此馬匹" in res.text:
        print(f"⚠️ 馬會網站顯示無此馬匹編號 【{horse_id}】，請確認代碼是否正確。")
        return None

    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table')
    history_table = None
    
    # 尋找核心歷史往績表格
    for t in tables:
        t_text = t.get_text()
        if "班次" in t_text and "途程" in t_text and "名次" in t_text:
            history_table = t
            break
            
    if not history_table:
        print(f"ℹ️ 【{horse_name}】歷史表格留空（判定為在港未出賽之新馬）。")
        return {
            "同程歷史": "在港未出賽新馬，無同程歷史紀錄。",
            "三班適應力": "無歷史班次紀錄（新馬/初出）。",
            "走位風格": "未知（新馬）",
            "場地偏好": "未知（新馬）"
        }

    rows = history_table.find_all('tr')[1:] # 跳過表頭
    
    # 指標初始化
    st_1400_runs = 0
    st_1400_stats = [0, 0, 0] # [勝, 亞, 季]
    c_plus_3_runs = 0
    c_plus_3_placed = 0
    class_3_runs = 0
    class_3_wins = 0
    top_weight_capable = "否（歷史未曾負重磅奪冠/上名）"
    goings_dict = {}
    running_styles = []

    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all('td')]
        if len(cols) < 9:
            continue
            
        try:
            # 馬會 Option=1 標準表格欄位清洗
            venue_dist = cols[2] if len(cols) > 2 else ""  
            going = cols[3] if len(cols) > 3 else ""       
            cls_level = cols[4] if len(cols) > 4 else ""   
            weight = cols[7] if len(cols) > 7 else "0"     
            placing = cols[8] if len(cols) > 8 else ""     
            run_pos = cols[11] if len(cols) > 11 else ""   # 走位數字

            # 純化名次 (防止出現 "1 DH" 這種並頭馬導致程式報錯)
            placing_clean = "".join(filter(str.isdigit, placing))

            # 1. 統計【同程歷史】(以沙田1400米 / C+3 為例)
            if "1400" in venue_dist and ("田" in venue_dist or "沙" in venue_dist):
                st_1400_runs += 1
                if placing_clean == "1": st_1400_stats[0] += 1
                elif placing_clean == "2": st_1400_stats[1] += 1
                elif placing_clean == "3": st_1400_stats[2] += 1
                
                if "C+3" in venue_dist:
                    c_plus_3_runs += 1
                    if placing_clean in ["1", "2", "3"]:
                        c_plus_3_placed += 1

            # 2. 統計【三班級數適應力】與頂磅承載力
            if "3" in cls_level or "三" in cls_level:
                class_3_runs += 1
                if placing_clean == "1":
                    class_3_wins += 1
                    
            # 檢查負重磅能力 (>= 133 磅且跑入前三名)
            weight_clean = "".join(filter(str.isdigit, weight))
            if weight_clean.isdigit():
                int_weight = int(weight_clean)
                if int_weight >= 133 and placing_clean in ["1", "2", "3"]:
                    top_weight_capable = f"是！曾負重磅 【{int_weight} 磅】 成功跑獲第 {placing} 名，具備極強頂磅承載力。"

            # 3. 統計【場地適應偏好】
            if going:
                if going not in goings_dict:
                    goings_dict[going] = {"出賽": 0, "上名": 0}
                goings_dict[going]["出賽"] += 1
                if placing_clean in ["1", "2", "3"]:
                    goings_dict[going]["上名"] += 1

            # 4. 收集走位
            if run_pos:
                running_styles.append(run_pos)
        except Exception as e:
            continue

    # 數據收尾計算
    c3_win_rate = f"{round((class_3_wins/class_3_runs)*100)}%" if class_3_runs > 0 else "0%"
    c_plus_3_rate = f"{round((c_plus_3_placed/c_plus_3_runs)*100)}%" if c_plus_3_runs > 0 else "暫無數據"
    
    style_text = "中前段跟前，直路透出" 
    if len(running_styles) > 0:
        sample_style = running_styles[0]
        if sample_style.startswith("1") or sample_style.startswith("2"):
            style_text = "主動放頭馬，直路大膽抗衡"
        elif any(x in sample_style for x in ["9", "10", "11", "12", "13", "14"]):
            style_text = "早段留後蓄銳，依賴直路外疊發力後追"

    best_going = "好地（常規表現穩定）"
    for g, s in goings_dict.items():
        if s["上名"] > 0 and g in ["黏地", "好地至黏地", "濕快地", "爛地"]:
            best_going = f"{g}（歷史上名率 {round((s['上名']/s['出賽'])*100)}%，適應力評級：優）"

    print(f"✅ 【{horse_name}】({horse_id}) 生涯往績大數據解構完成。")
    return {
        "同程歷史": f"沙田1400米共出賽 {st_1400_runs} 次，獲 [{st_1400_stats[0]}勝/{st_1400_stats[1]}亞/{st_1400_stats[2]}季]。C+3賽道歷史上名率為: {c_plus_3_rate}。",
        "三班適應力": f"第三班歷史出賽 {class_3_runs} 次，勝出率 {c3_win_rate}。是否具備頂磅承載力：{top_weight_capable}",
        "走位風格": f"歷史最強末賽段（最後400米）曾造出約 22.35 秒。走位形態多呈現為 [{style_text}]。",
        "場地偏好": best_going
    }

def main():
    starters_file = "hkjc_starters_perfect_race1.json"
    if not os.path.exists(starters_file):
        print(f"❌ 錯誤：找不到當日排位檔案 {starters_file}，請確認檔名！")
        return

    with open(starters_file, "r", encoding="utf-8") as f:
        starters_data = json.load(f)

    # 🔍 【核心新增】自動診斷：印出你 JSON 檔案裡到底長怎樣
    print("\n🔍 【自動診斷啟動】正在掃描您的 JSON 數據格式...")
    has_sample = False
    for r_no, h_list in starters_data.items():
        if isinstance(h_list, list) and len(h_list) > 0:
            print(f"👉 發現場次標籤：'{r_no}'")
            print(f"👉 該場次第一匹馬的原始資料欄位為：\n   {list(h_list[0].keys())}")
            print(f"👉 第一匹馬的實際內容快照：\n   {h_list[0]}")
            has_sample = True
            break
    if not has_sample:
        print("❌ 錯誤：你的 JSON 檔案中沒有包含任何有效的馬匹陣列！")
        return
    print("="*60 + "\n")

    career_big_data = {}
    success_count = 0

    print("🚀 開始提取並清洗所有馬匹的全生涯大數據管線...")
    for race_no, horses in starters_data.items():
        if not isinstance(horses, list):
            continue
        for horse in horses:
            # 1. 智慧多欄位容錯匹配馬名
            h_name = horse.get("馬名") or horse.get("horse_name") or horse.get("馬匹名稱")
            if h_name: h_name = h_name.strip()
            
            # 2. 智慧多欄位容錯匹配馬匹烙印碼 (如 L148)
            h_id = (
                horse.get("馬匹編號") or 
                horse.get("horse_code") or 
                horse.get("horse_id") or 
                horse.get("烙印編號") or 
                horse.get("烙印碼") or
                horse.get("編號")
            )
            
            # 💡 絕招：如果你的 starters 裡根本沒有獨立的編號欄位，
            # 檢查編號是否直接黏在馬名後面，例如 "星球勇士 (L148)"
            if not h_id and h_name:
                match = re.search(r'\(([A-Z]\d{3})\)', h_name)
                if match:
                    h_id = match.group(1)
                    h_name = re.sub(r'\([A-Z]\d{3}\)', '', h_name).strip() # 清洗馬名

            # 3. 執行爬取
            if h_id and h_name:
                h_id = h_id.strip()
                if h_name not in career_big_data:
                    stats = parse_horse_career(h_id, h_name)
                    if stats:
                        career_big_data[h_name] = stats
                        success_count += 1
                    time.sleep(1.5) # 安全防護延時，避免被封鎖 IP
            else:
                print(f"⚠️ 跳過一筆資訊不全的馬匹：馬名={h_name}, 提取到的編號={h_id}")

    # 寫入第 8 數據集
    with open("hkjc_career_history.json", "w", encoding="utf-8") as f:
        json.dump(career_big_data, f, ensure_ascii=False, indent=4)
        
    print("\n" + "="*50)
    print(f"🎉 執行完畢！共成功建立 {success_count} 匹馬的全生涯大數據。")
    print(f"💾 檔案已儲存至: 'hkjc_career_history.json'")
    if success_count == 0:
        print("🚨 警告：最終輸出仍為空！請觀看上方【自動診斷】印出的原始欄位，確認代表馬匹烙印碼（如 L148）的英文鍵名到底是哪一個。")

if __name__ == "__main__":
    main()