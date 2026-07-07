# hkjc_career_history.py
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
import random

def parse_horse_career(horse_id, horse_name):
    """前往馬會官網傳統桌面版網址爬取單匹馬的生涯歷史（SSR 伺服器端渲染，100% 穿透防線）"""
    # 🌟 關鍵修正：改用傳統的隨端渲染網址，規避新版網頁的 JavaScript 空白骨架問題
    url = f"https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx?HorseId={horse_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx",
        "Connection": "keep-alive"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code != 200:
            return None
    except Exception as e:
        print(f"❌ 網絡請求超時或失敗 ({horse_name}): {e}")
        return None

    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table')
    history_table = None
    
    # 🌟 關鍵修正：傳統表格的表頭是「級數」而非「班次」，這裡進行雙向彈性相容
    for t in tables:
        t_text = t.get_text()
        if ("班次" in t_text or "級數" in t_text) and "途程" in t_text and "名次" in t_text:
            history_table = t
            break
            
    if not history_table:
        page_text = soup.get_text()
        if "找不到馬匹" in page_text or "沒有相關紀錄" in page_text or "未有海外賽績" in page_text or horse_id == "":
            return {
                "生涯總結": "在港未出賽新馬，無同程歷史紀錄。",
                "級數與負磅": "無歷史班次紀錄（新馬/初出）。",
                "走位風格": "未知（新馬）",
                "場地偏好": "未知（新馬）"
            }
        else:
            title_text = soup.title.string.strip() if soup.title else "無標題"
            snippet = re.sub(r'\s+', ' ', res.text[:150]).strip()
            print(f"🔍 提示：{horse_name}({horse_id}) 未能找到賽績表格")
            print(f"   [Debug 網頁實況] 標題: {title_text} | 內容片段: {snippet}")
            return None

    # 🌟【核心升級：動態偵測表頭索引】
    header_row = history_table.find('tr')
    headers_text = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
    
    # 初始化索引字典
    idx = {"venue": 3, "class": 6, "dist": 4, "going": 5, "weight": 13, "placing": 1, "run_pos": 17}
    
    for i, h in enumerate(headers_text):
        if "處境" in h or "馬場" in h: idx["venue"] = i
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
    max_win_weight = 0 

    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all('td')]
        if len(cols) <= max(idx.values()): continue
            
        try:
            venue_text = cols[idx["venue"]]
            class_text = cols[idx["class"]]
            dist_text = cols[idx["dist"]]
            going_text = cols[idx["going"]]
            weight_text_raw = cols[idx["weight"]]
            placing_text = cols[idx["placing"]]
            run_pos_text = cols[idx["run_pos"]]

            # 1. 清洗名次 (Placing)
            p_clean = placing_text.strip().split('/')[0].split(' ')[0]
            if not p_clean.isdigit(): continue
            
            p_num = int(p_clean)
            is_win = (p_num == 1)
            is_place = (p_num in [1, 2, 3])

            # 2. 處理場地與途程 (Venue & Distance)
            v_key = "其他"
            if "谷" in venue_text or "HV" in venue_text: v_key = "谷"
            elif "田" in venue_text or "ST" in venue_text: v_key = "從化" if "從" in venue_text else "沙田"

            dist_clean = "".join(filter(str.isdigit, dist_text))
            if dist_clean:
                total_runs += 1
                if is_win: total_wins += 1
                if is_place: total_places += 1
                
                dist_key = f"{v_key}{dist_clean}米"
                if dist_key not in dist_stats:
                    dist_stats[dist_key] = {"runs": 0, "wins": 0, "places": 0}
                dist_stats[dist_key]["runs"] += 1
                if is_win: dist_stats[dist_key]["wins"] += 1
                if is_place: dist_stats[dist_key]["places"] += 1

            # 3. 處理班次 (Class)
            cls_match = re.search(r'[1-5一二三四五]', class_text)
            if cls_match:
                c_level = cls_match.group()
                c_level = c_level.replace('一','1').replace('二','2').replace('三','3').replace('四','4').replace('五','5')
                c_key = f"第 {c_level} 班"
                if c_key not in class_stats:
                    class_stats[c_key] = {"runs": 0, "places": 0}
                class_stats[c_key]["runs"] += 1
                if is_place: class_stats[c_key]["places"] += 1

            # 4. 處理負磅 (Weight)
            weight_clean = "".join(filter(str.isdigit, weight_text_raw))
            if weight_clean.isdigit():
                w_val = int(weight_clean)
                if is_win and w_val > max_win_weight:
                    max_win_weight = w_val

            # 5. 處理場地狀況偏好 (Going)
            if going_text:
                if going_text not in goings_dict:
                    goings_dict[going_text] = {"runs": 0, "places": 0}
                goings_dict[going_text]["runs"] += 1
                if is_place: goings_dict[going_text]["places"] += 1

            # 6. 處理沿途走位風格 (Running Style)
            pos_numbers = [int(s) for s in re.findall(r'\d+', run_pos_text)]
            if pos_numbers:
                first_pos = pos_numbers[0]
                last_pos = pos_numbers[-1]
                if first_pos <= 3:
                    running_styles.append("放頭/前傾")
                elif last_pos < first_pos and (first_pos - last_pos) >= 4:
                    running_styles.append("留後發力後追")
                else:
                    running_styles.append("跟前/居中透出")

        except Exception as e:
            continue

    # 如果清洗完畢後完全沒有有效出賽紀錄，視為新馬
    if total_runs == 0:
        return {
            "生涯總結": "在港未出賽新馬，無同程歷史紀錄。",
            "級數與負磅": "無歷史班次紀錄（新馬/初出）。",
            "走位風格": "未知（新馬）",
            "場地偏好": "未知（新馬）"
        }

    # --- 數據組裝區，精準對接大數據 RAG 模型要求的 4 碼結構 ---
    # A. 最佳途程計算
    best_dist = "暫無數據"
    max_score = -1
    for dk, dv in dist_stats.items():
        score = dv["places"] * 10 + dv["wins"]
        if score > max_score:
            max_score = score
            best_dist = f"{dk} (出賽{dv['runs']}次，獲{dv['wins']}勝{dv['places']}位)"

    # B. 最擅長班次與重磅承載力
    best_class = "暫無數據"
    max_cls_places = -1
    for ck, cv in class_stats.items():
        if cv["places"] > max_cls_places:
            max_cls_places = cv["places"]
            best_class = f"{ck} (出賽{cv['runs']}次，上名{cv['places']}次)"
            
    weight_str = f"曾負重磅 {max_win_weight} 磅奪冠，具備頂磅承載力！" if max_win_weight >= 130 else f"歷史最高奪冠負磅為 {max_win_weight} 磅。"
    if max_win_weight == 0:
        weight_str = "歷史未曾負重磅奪冠。"

    # C. 走位型態歸納
    style_summary = "中前段跟前，直路透出"
    if running_styles:
        from collections import Counter
        most_common_style = Counter(running_styles).most_common(1)[0][0]
        if most_common_style == "放頭/前傾": style_summary = "主動放頭馬，直路大膽抗衡"
        elif most_common_style == "留後發力後追": style_summary = "早段留後蓄銳，依賴直路外疊發力後追"

    # D. 場地偏好歸納
    best_going = "常規好地"
    max_going_places = -1
    for gk, gv in goings_dict.items():
        if gv["places"] > max_going_places:
            max_going_places = gv["places"]
            rate = int((gv["places"] / gv["runs"]) * 100) if gv["runs"] > 0 else 0
            if "好" in gk or "快" in gk:
                best_going = "常規好地"
            else:
                best_going = f"{gk}（特種場地上名率 {rate}%）"

    return {
        "生涯總結": f"在港總出賽 {total_runs} 次，累積 {total_wins} 冠 {total_places} 位。歷史最擅長途程為：{best_dist}。",
        "級數與負磅": f"歷史最擅長適應班次為：{best_class}。{weight_str}",
        "走位風格": f"走位形態多呈現為 [{style_summary}]。",
        "場地偏好": f"表現最佳場地：{best_going}。"
    }

def main():
    starters_file = "hkjc_starters_perfect.json"
    history_file = "hkjc_career_history.json"

    if not os.path.exists(starters_file):
        print(f"❌ 錯誤：找不到輸入源檔案 {starters_file}，請確認檔案是否存在。")
        return

    with open(starters_file, 'r', encoding='utf-8') as f:
        try:
            starters_data = json.load(f)
        except Exception as e:
            print(f"❌ JSON 解析失敗，請檢查 {starters_file} 格式。錯誤: {e}")
            return

    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            try:
                career_big_data = json.load(f)
            except:
                career_big_data = {}
    else:
        career_big_data = {}

    starters_list = []
    for race_key, horses in starters_data.items():
        if isinstance(horses, list):
            starters_list.extend(horses)

    print("⏳ 開始批次爬取並解析出賽馬匹歷史底蘊...")
    success_count = 0

    for horse in starters_list:
        h_name = horse.get("馬名") or horse.get("horse_name")
        if not h_name or "馬名" in str(h_name) or "BO :" in str(h_name):
            continue

        h_id = (
            horse.get("烙印編號") or 
            horse.get("horse_code") or 
            horse.get("horse_id") or 
            horse.get("烙印碼") or
            horse.get("編號")
        )
        
        if h_id:
            clean_match = re.search(r'([A-Z]\d{3})', str(h_id))
            if clean_match:
                h_id = clean_match.group(1)

        if not h_id and h_name:
            match = re.search(r'\(([A-Z]\d{3})\)', h_name)
            if match:
                h_id = match.group(1)
                h_name = re.sub(r'\([A-Z]\d{3}\)', '', h_name).strip()

        if h_id and h_name:
            h_id = h_id.strip()
            h_name = h_name.strip()
            
            # 🌟 增量更新邏輯：如果目前在庫內部的數據是上次失敗產生的空白 dummy 新馬數據，也強制重新爬取校準
            is_dummy = "在港未出賽新馬" in str(career_big_data.get(h_name, {}).get("生涯總結", ""))
            
            if h_name not in career_big_data or is_dummy:
                print(f"🎬 正在解析：{h_name} ({h_id})...")
                stats = parse_horse_career(h_id, h_name)
                
                if stats:
                    career_big_data[h_name] = stats
                    success_count += 1
                    
                    with open(history_file, 'w', encoding='utf-8') as f:
                        json.dump(career_big_data, f, ensure_ascii=False, indent=4)
                
                time.sleep(random.uniform(3.0, 5.0))
        else:
            if h_name and "馬號" not in str(h_name):
                print(f"⚠️ 跳過一筆資訊不全的馬匹：馬名={h_name}, 提取到的編號={h_id}")

    print(f"🎉 運行結束！本次成功增量更新 {success_count} 匹馬的歷史底蘊至 {history_file}")

if __name__ == "__main__":
    main()