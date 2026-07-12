# hkjc_career_history.py
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time

def build_basic_info(age, current_rating=None, season_start_rating=None):
    """🌟 根據馬齡與評分走勢，預測馬匹現時體能狀況與進步/衰退空間"""
    # 1. 年齡預測邏輯（核心信號）
    if age <= 3:
        age_phase = "目前正處於黃金上升期"
        age_detail = "年輕新銳，每跑一場都在累積經驗，評分具大幅上升空間"
    elif age in (4, 5):
        # age_phase = "正值當打巔峰期"
        # age_detail = "體能與賽事經驗兼備，處於競爭力最穩定的階段"
        age_phase = ""
        age_detail = ""
    elif age is not None and age >= 6:
        age_phase = "戰力已從巔峰下滑"
        age_detail = "競爭力主要倚賴狀態與配對，難以長期維持高水準"
    else:
        age_phase = "年齡資料不足"
        age_detail = ""

    if age is None:
        text = "年齡資料缺失，無法判斷現時所處階段。"
        return text
    else:
        text = f"年齡 {age} 歲，{age_phase}。"
        if age_detail:
            text += age_detail + "。"

    # 2. 評分走勢（輔助信號，強化「現時狀況」描述）
    if current_rating is not None and season_start_rating is not None:
        diff = current_rating - season_start_rating
        if age in [4, 5]:
            # 4-5歲中生代馬邏輯（需要精細分流）
            if diff <= -15:
                text = f"年齡 {age} 歲，雖屬當打之年，但本季評分出現崩盤式倒退（↓{abs(diff)}），季內表現嚴重走樣。目前評分已大幅超跌，需關注是否已跌至底線迎來反彈契機。"
            elif diff <= -8:
                text = f"年齡 {age} 歲，本季戰力陷入瓶頸，評分持續下滑（↓{abs(diff)}），正處於調整期，競爭力有待狀態回溫。"
            elif abs(diff) <= 7:
                text = f"年齡 {age} 歲，正值當打巔峰期。體能與賽事經驗兼備，近期評分變幅不大，處於競爭力最穩定的階段。"
            else:
                text = f"年齡 {age} 歲，正值當打巔峰期。體能與賽事經驗兼備，本季評分由 {season_start_rating} 升至 {current_rating}（↑{abs(diff)}），狀態持續向上。"
        elif age >= 6 and diff <= -10:
            text += f"本季評分大幅倒退（↓{abs(diff)}），已跌至極低檔位，本仗旨在利用班次優勢圖謀低班突襲。"
        elif diff > 0:
            text += f"本季評分由 {season_start_rating} 升至 {current_rating}（↑{diff}），狀態持續向上。"
        else:
            text += f"本季評分由 {season_start_rating} 跌至 {current_rating}（↓{abs(diff)}），近期評分受壓。"

    return text

def parse_margin_to_lengths(text):
    """🌟 將馬會「頭馬距離」欄位轉換為以「馬位(lengths)」為單位的浮點數
    支援格式：整數(5)、分數(3/4)、混合(1-1/4)、文字(頭位/頸位/短頭/鼻位)"""
    if not text:
        return None
    t = text.strip()
    # 文字距離
    if "頭位" in t: return 0.2
    if "頸位" in t: return 0.3
    if "短頭" in t: return 0.1
    if "鼻位" in t: return 0.05
    if t in ("—", "-", ""): return None
    # 混合格式 1-1/4 -> 1.25
    m = re.match(r'^(\d+)-(\d+)/(\d+)$', t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    # 純分數 3/4 -> 0.75
    m = re.match(r'^(\d+)/(\d+)$', t)
    if m:
        return int(m.group(1)) / int(m.group(2))
    # 純整數 5 -> 5.0
    m = re.match(r'^(\d+(\.\d+)?)$', t)
    if m:
        return float(m.group(1))
    return None

def build_form_restore_index(recent_runs):
    """🌟 實力還原指標 (Formline Sandboxing)：以近三仗輸給頭馬的馬位量化真實戰力
    recent_runs: list of (margin_lengths, placing)，按時間由近到遠排列（最多 3 筆）"""
    if not recent_runs:
        return "近仗資料不足，暫無法量化實力還原空間。"
    margins = [m for m, p in recent_runs]
    avg = sum(margins) / len(margins)
    wins = sum(1 for m, p in recent_runs if p == 1)
    avg_txt = f"{avg:.1f}"
    if wins == len(recent_runs):
        return f"近 {len(recent_runs)} 仗全數奪冠，實力處於頂峰，無還原必要。"
    if avg <= 1.5:
        return f"近 {len(recent_runs)} 仗平均輸給頭馬 {avg_txt} 個馬位，名次雖不顯眼但實力並未落後，極具還原價值。"
    elif avg <= 3.0:
        return f"近 {len(recent_runs)} 仗平均輸給頭馬 {avg_txt} 個馬位，與前列馬匹咬得甚緊，實力接近。"
    else:
        return f"近 {len(recent_runs)} 仗平均輸給頭馬 {avg_txt} 個馬位，與前列馬匹仍有明顯實力差距。"

def build_weight_feature(current_weight, prev_weight, golden_weight):
    """🌟 臨場體重特徵：以排位表「排位體重」欄位量化體態變化與健康訊號
    current_weight: 當仗排位體重(磅)，來自 hkjc_starters_perfect.json 的「排位體重」
    prev_weight: 上仗體重(磅)，由「排位體重 - 排位體重+/-」推算；無法推算時為 None
    golden_weight: 最近一次奪冠時體重(磅)，來自賽績表"""
    if current_weight is None:
        return "體重資料不足，無法判斷臨場體態。"
    text = f"現時體重 {current_weight} 磅"
    # 1. 對比上仗體重，偵測驟變（>20 磅視為操練失當或健康隱憂）
    if prev_weight is not None:
        delta = current_weight - prev_weight
        if delta >= 15:
            return f"{text}，較上仗急增 {delta} 磅，體重明顯驟升！反映久休收身不足，恐飽餐缺操、體態偏肥。"
        elif delta <= -15:
            return f"{text}，較上仗急跌 {abs(delta)} 磅，體重明顯驟降！需留意是否操練過度導致體能透支或走樣。"
        elif abs(delta) <= 10:
            text += f"，較上仗變動 {delta:+d} 磅，體態平穩，操練正常。"
        else:
            text += "，體重輕微波動，屬正常微調。"
    # 2. 對比歷史奪冠黃金體重
    if golden_weight is not None:
        diff = abs(current_weight - golden_weight)
        if diff <= 5:
            text += f"對比歷史奪冠時體重（{golden_weight} 磅）僅差 {diff} 磅，處於黃金體態，是強烈的大打進擊訊號。"
        else:
            text += f"對比歷史奪冠時體重（{golden_weight} 磅）相差 {diff} 磅，尚未回到最佳體態。"
    else:
        text += "暫無奪冠體重紀錄可供對比。"
    return text

def build_season_trend(season_runs):
    """🌟 季內走勢：將賽績按「馬季」切分，只統計本季表現，避免被舊輝煌歷史誤導
    season_runs: 本季所有出賽的 (margin_lengths, placing) 列表，由近到遠排列"""
    if not season_runs:
        return "本季尚無出賽紀錄，無從判斷季內走勢。"
    runs = len(season_runs)
    wins = sum(1 for m, p in season_runs if p == 1)
    # 🌟 修正：與全檔案慣例一致，「位」指非頭馬的上名次數（不含頭馬），故扣除 wins
    places = sum(1 for m, p in season_runs if p in (2, 3))
    # 近兩仗勝負距離（若有）
    recent_two = season_runs[:2]
    recent_avg = sum(m for m, p in recent_two) / len(recent_two) if recent_two else None
    # 全季平均距離
    season_avg = sum(m for m, p in season_runs) / runs
    text = f"本季出賽 {runs} 次（{wins}冠 {places}位）"
    # 狀態判斷
    if wins == runs:
        text += "，全季保持全勝，狀態處於頂峰。"
    elif recent_avg is not None and recent_avg <= 1.0:
        text += f"，近兩仗勝負距離縮短至 {recent_avg:.1f} 馬位內，狀態明顯回勇。"
    elif season_avg >= 10.0:
        text += f"，全季平均輸給頭馬 {season_avg:.1f} 個馬位，戰力已然崩潰，舊季輝煌難以為繼。"
    elif season_avg >= 5.0:
        text += f"，全季平均輸給頭馬 {season_avg:.1f} 個馬位，季內表現持續低迷。"
    else:
        text += f"，全季平均輸給頭馬 {season_avg:.1f} 個馬位，季內表現中規中矩。"
    return text

def parse_horse_career(horse_id, horse_name, current_weight=None, prev_weight=None):
    """前往馬會官網爬取單匹馬的生涯歷史，並透過動態欄位錨定進行精準量化"""
    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}&Option=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 🌟 新增：重試機制，避免因 HKJC 網站瞬間逾時/失敗而靜默漏掉馬匹
    res = None
    for attempt in range(1, 4):  # 最多重試 3 次
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            if res.status_code == 200:
                break
            print(f"⚠️ 第 {attempt} 次抓取 {horse_name}({horse_id}) 回傳狀態碼 {res.status_code}，準備重試...")
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次抓取 {horse_name}({horse_id}) 發生例外：{e}，準備重試...")
        time.sleep(2 * attempt)  # 指數退避
    if res is None or res.status_code != 200:
        print(f"❌ 抓取 {horse_name}({horse_id}) 失敗，已放棄重試，該駒將不計入生涯數據。")
        return None

    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table')
    history_table = None
    for t in tables:
        t_text = t.get_text()
        if "班次" in t_text and "途程" in t_text and "名次" in t_text:
            history_table = t
            break
            
    if not history_table:
        return {"基本信息": "年齡資料缺失，無法判斷現時所處階段。", "實力還原指標": "近仗資料不足，暫無法量化實力還原空間。", "臨場體重特徵": "體重資料不足，無法判斷臨場體態。", "季內走勢": "本季尚無出賽紀錄，無從判斷季內走勢。", "生涯總結": "無出賽紀錄", "級數與負磅": "無資料", "走位風格": "未知", "場地偏好": "未知"}

    # 🌟【新增：解析馬匹基本資料表，提取年齡與評分走勢】
    basic_age = None
    basic_cur_rating = None
    basic_season_rating = None
    for t in tables:
        t_text = t.get_text()
        if "馬齡" in t_text and "現時評分" in t_text:
            for r in t.find_all('tr'):
                cells = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
                # 每行格式為 [欄位, ':', 值] 或 [欄位 / 值] 合併
                for i, c in enumerate(cells):
                    if c == "出生地 / 馬齡" and i + 2 < len(cells):
                        age_match = re.search(r'(\d+)', cells[i + 2])
                        if age_match:
                            basic_age = int(age_match.group(1))
                    elif c == "現時評分" and i + 2 < len(cells):
                        rt = re.search(r'(\d+)', cells[i + 2])
                        if rt: basic_cur_rating = int(rt.group(1))
                    elif c == "季初評分" and i + 2 < len(cells):
                        rt = re.search(r'(\d+)', cells[i + 2])
                        if rt: basic_season_rating = int(rt.group(1))
            break

    basic_info_text = build_basic_info(basic_age, basic_cur_rating, basic_season_rating)

    # 🌟【核心升級：動態偵測表頭索引】
    header_row = history_table.find('tr')
    headers_text = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
    
    # 初始化索引字典（給予安全預設值，若找不到則動態覆蓋）
    # 🌟 修正：實際表頭為「馬場/跑道/賽道」，預設值改為正確的欄位索引 3
    idx = {"venue": 3, "class": 3, "dist": 4, "going": 5, "weight": 7, "placing": 9, "run_pos": 10, "margin": 11, "body_weight": 16}
    
    for i, h in enumerate(headers_text):
        # 🌟 修正：實際場地欄位表頭是「馬場/跑道/賽道」，而非「處境」
        if "處境" in h or "馬場" in h or "跑道" in h or "賽道" in h: idx["venue"] = i
        if "班次" in h or "級數" in h: idx["class"] = i
        if "途程" in h: idx["dist"] = i
        if "狀況" in h or "場地" in h: idx["going"] = i
        if "負磅" in h: idx["weight"] = i
        if "名次" in h: idx["placing"] = i
        if "走位" in h or "沿途" in h: idx["run_pos"] = i
        if "頭馬距離" in h or "距頭馬" in h or "輸距" in h: idx["margin"] = i
        if "排位體重" in h or "馬匹體重" in h or "體重" in h: idx["body_weight"] = i

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
    recent_runs = []      # 🌟 新增：收集近三仗 (輸給頭馬馬位, 名次)，用於實力還原指標
    golden_weight = None  # 🌟 新增：最近一次奪冠時的體重(磅)，用於臨場體重特徵對比
    season_runs = []      # 🌟 新增：收集本季 (輸給頭馬馬位, 名次)，用於季內走勢
    season_marker_count = 0  # 表格由近到遠，首個「馬季」標記起為本季，次個標記起即離開本季

    # === 以下是 for row in rows: 內部的完全體整合邏輯 ===
    for row in rows:
        cols = [td.get_text().strip() for td in row.find_all('td')]

        # 🌟 新增：偵測「馬季」分隔列（如 '25/26馬季'）
        # 必須放在長度守門之前，因分隔列只有單一儲存格會被誤判為無效列
        # 表格由近到遠：第 1 個標記起為本季，第 2 個標記起即離開本季
        if len(cols) == 1 and "馬季" in cols[0]:
            season_marker_count += 1
            continue

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

            # 🌟 新增：收集近三仗 (輸給頭馬馬位, 名次) 供實力還原指標使用
            # 表格由近到遠排列，故前 3 筆即為近三仗
            if len(recent_runs) < 3:
                margin_text = cols[idx["margin"]] if idx["margin"] < len(cols) else ""
                margin_len = parse_margin_to_lengths(margin_text)
                if margin_len is not None:
                    recent_runs.append((margin_len, p_num))

            # 🌟 新增：收集本季 (輸給頭馬馬位, 名次) 供季內走勢使用
            # 只收錄第 1 個「馬季」標記之後、第 2 個標記之前的區塊（即本季）
            if season_marker_count == 1:
                margin_text = cols[idx["margin"]] if idx["margin"] < len(cols) else ""
                margin_len = parse_margin_to_lengths(margin_text)
                if margin_len is not None:
                    season_runs.append((margin_len, p_num))

            # 🌟 新增：收集「最近一次奪冠時體重」(golden_weight)，用於臨場體重特徵對比
            # 注意：現時體重與上仗體重改由排位表 (hkjc_starters_perfect.json) 傳入，不再從賽績表讀取
            if idx["body_weight"] < len(cols):
                bw_text = cols[idx["body_weight"]]
                bw_match = re.search(r'(\d+)', bw_text)
                if bw_match and golden_weight is None and is_win:
                    golden_weight = int(bw_match.group(1))

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
        return {"基本信息": basic_info_text, "實力還原指標": "近仗資料不足，暫無法量化實力還原空間。", "臨場體重特徵": "體重資料不足，無法判斷臨場體態。", "季內走勢": "本季尚無出賽紀錄，無從判斷季內走勢。", "生涯總結": "無有效歷史紀錄", "級數與負磅": "無資料", "走位風格": "未知", "場地偏好": "未知"}

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
            # best_going = f"{g}（特種場地上名率 {round((s['places']/s['runs'])*100)}%）"
            best_going = f"{g}（特種場地上名 {s['places']} 次 / 出賽 {s['runs']} 次）"

    return {
        "基本信息": basic_info_text,
        "實力還原指標": build_form_restore_index(recent_runs),
        "臨場體重特徵": build_weight_feature(current_weight, prev_weight, golden_weight),
        "季內走勢": build_season_trend(season_runs),
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
            # print(f"👉 發現場次標籤：'{r_no}'")
            # print(f"👉 該場次第一匹馬的原始資料欄位為：\n   {list(h_list[0].keys())}")
            # print(f"👉 第一匹馬的實際內容快照：\n   {h_list[0]}")
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

            # 🌟 新增：從排位表提取「現時體重」與「上仗體重」供臨場體重特徵使用
            # 現時體重 = 排位體重；上仗體重 = 排位體重 - 排位體重+/-
            cur_w = None
            prev_w = None
            bw_raw = horse.get("排位體重")
            bw_delta_raw = horse.get("排位體重+/-")
            if bw_raw is not None:
                bw_m = re.search(r'(\d+)', str(bw_raw))
                if bw_m:
                    cur_w = int(bw_m.group(1))
                    if bw_delta_raw is not None:
                        d_m = re.search(r'(-?\d+)', str(bw_delta_raw))
                        if d_m:
                            prev_w = cur_w - int(d_m.group(1))

            # 3. 執行爬取
            if h_id and h_name:
                h_id = h_id.strip()
                if h_name not in career_big_data:
                    stats = parse_horse_career(h_id, h_name, cur_w, prev_w)
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