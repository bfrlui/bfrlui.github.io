# hkjc_career_history.py
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time

def parse_horse_career(horse_id, horse_name):
    """前往馬會官網爬取單匹馬的生涯歷史，並透過動態欄位錨定進行精準量化"""
    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}&Option=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code != 200: return None
    except: return None

    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table')
    history_table = None
    for t in tables:
        t_text = t.get_text()
        if "班次" in t_text and "途程" in t_text and "名次" in t_text:
            history_table = t
            break
            
    if not history_table:
        return {"生涯總結": "無出賽紀錄", "級數與負磅": "無資料", "走位風格": "未知", "場地偏好": "未知"}

    # 🌟【核心升級：動態偵測表頭索引】
    header_row = history_table.find('tr')
    headers_text = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
    
    # 初始化索引字典（給予安全預設值，若找不到則動態覆蓋）
    # 🌟 修正：實際表頭為「馬場/跑道/賽道」，預設值改為正確的欄位索引 3
    idx = {"venue": 3, "class": 3, "dist": 4, "going": 5, "weight": 7, "placing": 9, "run_pos": 10}
    
    for i, h in enumerate(headers_text):
        # 🌟 修正：實際場地欄位表頭是「馬場/跑道/賽道」，而非「處境」
        if "處境" in h or "馬場" in h or "跑道" in h or "賽道" in h: idx["venue"] = i
        if "班次" in h or "級數" in h: idx["class"] = i
        if "途程" in h: idx["dist"] = i
        if "狀況" in h or "場地" in h: idx["going"] = i
        if "負磅" in h: idx["weight"] = i
        if "名次" in h: idx["placing"] = i
        if "走位" in h or "沿途" in h: idx["run_pos"] = i

    rows = history_table.find_all('tr')[1:]
    
    total_runs = 0
    total_wins = 0
    total_places = 0
    dist_stats = {}   
    class_stats = {}  
    goings_dict = {}  
    running_styles = []
    early_positions = []  # 🌟 新增：收集每場早段位置（沿途走位第一個數字），用於量化前速
    max_win_weight = 0 

    # === 以下是 for row in rows: 內部的完全體整合邏輯 ===
    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all('td')]
        if len(cols) <= max(idx.values()): continue
            
        try:
            # 依據動態索引精準取值
            venue_text = cols[idx["venue"]]
            class_text = cols[idx["class"]]
            dist_text = cols[idx["dist"]]
            going_text = cols[idx["going"]]
            weight_text_raw = cols[idx["weight"]]
            placing_text = cols[idx["placing"]]
            run_pos_text = cols[idx["run_pos"]]

            # 1. 處理名次 (Placing) - 完美解決斜線(1/14)與並頭馬(1 DH)問題
            placing_stage1 = placing_text.strip().split('/')[0].split(' ')[0]
            placing_clean = "".join(filter(str.isdigit, placing_stage1))

            if placing_clean.isdigit():
                p_num = int(placing_clean)
                if 1 <= p_num <= 14:
                    total_runs += 1
                    is_win = (p_num == 1)
                    is_place = (p_num in [1, 2, 3])
                    
                    if is_win: total_wins += 1
                    if is_place: total_places += 1
            else:
                continue # 排除未完賽、退出等異常狀況

            # 2. 處理途程 (Distance)
            dist_clean = "".join(filter(str.isdigit, dist_text))
            if dist_clean and len(dist_clean) >= 3:
                venue_key = "田" if "田" in venue_text or "沙" in venue_text else "谷"
                dist_key = f"{venue_key}{dist_clean}米"
                if dist_key not in dist_stats: 
                    dist_stats[dist_key] = {"runs":0, "wins":0, "places":0}
                dist_stats[dist_key]["runs"] += 1
                if is_win: dist_stats[dist_key]["wins"] += 1
                if is_place: dist_stats[dist_key]["places"] += 1

            # 3. 處理班次 (Class) -> 🌟 這次把它穩穩地補回來！
            cls_match = re.search(r'[1-5一二三四五]', class_text)
            if cls_match:
                c_level = cls_match.group()
                c_level = c_level.replace('一','1').replace('二','2').replace('三','3').replace('四','4').replace('五','5')
                if c_level not in class_stats: 
                    class_stats[c_level] = {"runs":0, "places":0}
                class_stats[c_level]["runs"] += 1
                if is_place: 
                    class_stats[c_level]["places"] += 1
                
            # 4. 處理負磅 (Weight)
            weight_clean = "".join(filter(str.isdigit, weight_text_raw))
            if weight_clean.isdigit() and is_win:
                w = int(weight_clean)
                if w > max_win_weight: 
                    max_win_weight = w

            # 5. 場地與走位
            if going_text:
                if going_text not in goings_dict: goings_dict[going_text] = {"runs": 0, "places": 0}
                goings_dict[going_text]["runs"] += 1
                if is_place: goings_dict[going_text]["places"] += 1
            if run_pos_text:
                running_styles.append(run_pos_text)
                # 🌟 新增：解析沿途走位第一個數字作為早段位置（如 "10 8 3" -> 10）
                ep_match = re.match(r'\s*(\d+)', run_pos_text)
                if ep_match:
                    early_positions.append(int(ep_match.group(1)))
                
        except Exception: continue

    if total_runs == 0:
        return {"生涯總結": "無有效歷史紀錄", "級數與負磅": "無資料", "走位風格": "未知", "場地偏好": "未知"}

    # ==================== 【修復版：最擅長途程計算邏輯】 ====================
    best_dist = "暫無數據"
    max_score = -1
    max_runs = -1  # 🌟 新增：用於在分數相同時比拼出賽次數

    for dk, dv in dist_stats.items():
        # 🌟 修正前：score = dv["places"] * 10 + dv["wins"] (位置權重過高)
        # 🌟 修正後：優先考慮頭馬，頭馬值 10 分，位置值 1 分
        score = dv["wins"] * 10 + dv["places"]        
        
        # 🌟 核心修復：如果分數更高，或者分數相同但「出賽次數更多」
        if (score > max_score) or (score == max_score and dv["runs"] > max_runs):
            max_score = score
            max_runs = dv["runs"]
            if score > 0:
                best_dist = f"{dk} (出賽{dv['runs']}次，獲{dv['wins']}勝{dv['places']}位)"
            else:
                # 如果從未上名過，則客觀顯示為出賽最多的途程並註明未上名
                best_dist = f"{dk} (出賽{dv['runs']}次，未曾上名)"

    # ==================== 【修復版：最擅長班次計算邏輯】 ====================
    best_class = "暫無數據"
    max_cls_places = -1
    max_cls_runs = -1  # 🌟 新增：用於班次同分時比拼出賽次數

    for ck, cv in class_stats.items():
        # 🌟 同理修復班次：避免 0 分馬全部被鎖死在第一筆遇見的班次
        if (cv["places"] > max_cls_places) or (cv["places"] == max_cls_places and cv["runs"] > max_cls_runs):
            max_cls_places = cv["places"]
            max_cls_runs = cv["runs"]
            if max_cls_places > 0:
                best_class = f"第 {ck} 班 (出賽{cv['runs']}次，上名{cv['places']}次)"
            else:
                best_class = f"第 {ck} 班 (出賽{cv['runs']}次，未曾上名)"
            
    w_text = f"曾負重磅 {max_win_weight} 磅奪冠，具備頂磅承載力！" if max_win_weight >= 132 else f"歷史最高奪冠負磅為 {max_win_weight} 磅。"

    # 走位與場地優化邏輯
    style_text = "中前段跟前，直路透出" 
    # 🌟 升級：以「全部出賽」的早段位置量化前速，而非只看第一筆樣本
    early_avg = (sum(early_positions) / len(early_positions)) if early_positions else 7.0
    early_front_ratio = (sum(1 for p in early_positions if p <= 3) / len(early_positions)) if early_positions else 0.0

    if early_positions:
        if early_avg <= 3.5:
            style_text = "主動放頭馬，直路大膽抗衡"
        elif early_avg >= 9.0:
            style_text = "早段留後蓄銳，依賴直路外疊發力後追"
        # 中間區間維持預設「中前段跟前，直路透出」
    elif running_styles:
        # 回退：若無法解析數字，沿用舊邏輯取第一筆
        sample = running_styles[0]
        if sample.startswith("1") or sample.startswith("2"): style_text = "主動放頭馬，直路大膽抗衡"
        elif any(x in sample for x in ["9", "10", "11", "12", "13", "14"]): style_text = "早段留後蓄銳，依賴直路外疊發力後追"

    # 🌟 新增：量化前速指標，供 RAG 引擎做場級步速總結
    front_speed = "高" if early_avg <= 4.0 else ("中" if early_avg <= 7.0 else "低")
    front_speed_metric = f"早段平均位置 {early_avg:.1f}（前速{front_speed}），早段前置(≤3)佔比 {round(early_front_ratio*100)}%"

    best_going = "常規好地"
    for g, s in goings_dict.items():
        if s["places"] > 0 and any(k in g for k in ["黏", "濕", "軟"]):
            best_going = f"{g}（特種場地上名率 {round((s['places']/s['runs'])*100)}%）"

    return {
        "生涯總結": f"在港總出賽 {total_runs} 次，累積 {total_wins}冠 {total_places-total_wins}位。歷史最擅長途程為：{best_dist}。",
        "級數與負磅": f"歷史最擅長適應班次為：{best_class}。{w_text}",
        "走位風格": f"走位形態多呈現為 [{style_text}]。",
        "前速指標": front_speed_metric,
        "場地偏好": f"表現最佳場地：{best_going}。"
    }

def main():
    # 🌟 新增：支援透過命令列參數指定單一場次，例如 python hkjc_career_history.py 1
    # 若未帶參數則處理全部場次（維持舊行為）
    target_race = None
    if len(sys.argv) > 1:
        try:
            target_race = int(sys.argv[1])
        except ValueError:
            print(f"❌ 錯誤：場次編號必須為數字，您輸入的是 '{sys.argv[1]}'。")
            return

    starters_file = "hkjc_starters_perfect.json"
    if not os.path.exists(starters_file):
        print(f"❌ 錯誤：找不到當日排位檔案 {starters_file}，請確認檔名！")
        return

    with open(starters_file, "r", encoding="utf-8") as f:
        starters_data = json.load(f)

    # 🔍 自動診斷：印出 JSON 數據格式
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

    # 🌟 若指定了場次，則只保留該場次的資料
    if target_race is not None:
        race_key = f"第 {target_race} 場"
        if race_key not in starters_data or not isinstance(starters_data[race_key], list):
            available = [k for k, v in starters_data.items() if isinstance(v, list)]
            print(f"❌ 錯誤：找不到場次 '{race_key}'！")
            print(f"👉 目前檔案中可用的場次標籤為：{available}")
            return
        starters_data = {race_key: starters_data[race_key]}
        print(f"🎯 已鎖定單一場次：{race_key}，僅處理該場次馬匹。\n")

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
    # 🌟 若指定單一場次，則輸出至 race_{n}_career_history.json，避免覆蓋全場次檔案
    if target_race is not None:
        out_file = f"hkjc_career_history_race_{target_race}.json"
    else:
        out_file = "hkjc_career_history.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(career_big_data, f, ensure_ascii=False, indent=4)
        
    print("\n" + "="*50)
    print(f"🎉 執行完畢！共成功建立 {success_count} 匹馬的全生涯大數據。")
    print(f"💾 檔案已儲存至: '{out_file}'")
    if success_count == 0:
        print("🚨 警告：最終輸出仍為空！請觀看上方【自動診斷】印出的原始欄位，確認代表馬匹烙印碼（如 L148）的英文鍵名到底是哪一個。")

if __name__ == "__main__":
    main()