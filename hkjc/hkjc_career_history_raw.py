# hkjc_career_history_raw.py
# 與 hkjc_career_history.py 抓取同一個馬會官網來源頁面，
# 但本程式「不做任何語意/人類可讀文字轉換」，直接把網頁表格的
# 原始數據（基本資料表 + 賽績表每一列的原始儲存格文字）原樣輸出成 JSON。
import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import time

def parse_horse_career_raw(horse_id, horse_name):
    """前往馬會官網爬取單匹馬的生涯歷史，原樣保留表格原始數據，不做任何語意轉換"""
    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}&Option=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 重試機制，避免因 HKJC 網站瞬間逾時/失敗而靜默漏掉馬匹
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

    # ===== 1. 解析基本資料表（原樣保留每一列的 欄位 -> 原始值）=====
    basic_info = {}
    for t in tables:
        t_text = t.get_text()
        if "馬齡" in t_text and "現時評分" in t_text:
            for r in t.find_all('tr'):
                cells = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
                # 原樣保留：以第一個非空白儲存格為 key，最後一個非空白儲存格為 value
                # 可同時兼容 [欄位, ':', 值] 與 [欄位 / 值] 兩種版面
                non_empty = [c for c in cells if c]
                if len(non_empty) >= 2:
                    key = non_empty[0]
                    value = non_empty[-1]
                    # 跳過頁面頂端的導覽列（一整列超連結，如「往績紀錄…其他馬匹」）
                    if "往績紀錄" in key or "其他馬匹" in key:
                        continue
                    basic_info[key] = value
            break

    # ===== 2. 定位賽績表 =====
    history_table = None
    for t in tables:
        t_text = t.get_text()
        if "班次" in t_text and "途程" in t_text and "名次" in t_text:
            history_table = t
            break

    if not history_table:
        return {
            "basic_info": basic_info,
            "career_records": []
        }

    # ===== 3. 取得表頭（原樣保留欄位名稱，例如「馬場/跑道/賽道」「頭馬距離」等）=====
    header_row = history_table.find('tr')
    headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]

    # ===== 4. 逐列解析，原樣保留每一格的原始文字 =====
    career_records = []
    current_season = None
    for row in history_table.find_all('tr')[1:]:
        cols = [td.get_text().strip() for td in row.find_all('td')]

        # 偵測「馬季」分隔列（如 '25/26馬季'），記錄後續紀錄所屬馬季
        if len(cols) == 1 and "馬季" in cols[0]:
            current_season = cols[0]
            continue

        # 跳過明顯無效的短列
        if len(cols) < 2:
            continue

        record = {}
        for i, h in enumerate(headers):
            if i < len(cols):
                record[h] = cols[i]
        record["所屬馬季"] = current_season
        career_records.append(record)

    return {
        "basic_info": basic_info,
        "career_records": career_records
    }

def main():
    # 支援透過命令列參數指定單一場次，例如 python hkjc_career_history_raw.py 1
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

    # 若指定了場次，則只保留該場次的資料
    if target_race is not None:
        race_key = f"第 {target_race} 場"
        if race_key not in starters_data or not isinstance(starters_data[race_key], list):
            available = [k for k, v in starters_data.items() if isinstance(v, list)]
            print(f"❌ 錯誤：找不到場次 '{race_key}'！")
            print(f"👉 目前檔案中可用的場次標籤為：{available}")
            return
        starters_data = {race_key: starters_data[race_key]}
        print(f"🎯 已鎖定單一場次：{race_key}，僅處理該場次馬匹。\n")

    career_raw_data = {}
    success_count = 0

    print("🚀 開始提取所有馬匹的生涯原始數據（不做人類可讀轉換）...")
    for race_no, horses in starters_data.items():
        if not isinstance(horses, list):
            continue
        for horse in horses:
            # 智慧多欄位容錯匹配馬名
            h_name = horse.get("馬名") or horse.get("horse_name") or horse.get("馬匹名稱")
            if h_name: h_name = h_name.strip()

            # 智慧多欄位容錯匹配馬匹烙印碼 (如 L148)
            h_id = (
                horse.get("馬匹編號") or
                horse.get("horse_code") or
                horse.get("horse_id") or
                horse.get("烙印編號") or
                horse.get("烙印碼") or
                horse.get("編號")
            )

            # 若 starters 裡沒有獨立編號欄位，檢查是否黏在馬名後面，例如 "星球勇士 (L148)"
            if not h_id and h_name:
                match = re.search(r'\(([A-Z]\d{3})\)', h_name)
                if match:
                    h_id = match.group(1)
                    h_name = re.sub(r'\([A-Z]\d{3}\)', '', h_name).strip()  # 清洗馬名

            # 執行爬取
            if h_id and h_name:
                h_id = h_id.strip()
                if h_name not in career_raw_data:
                    stats = parse_horse_career_raw(h_id, h_name)
                    if stats:
                        career_raw_data[h_name] = stats
                        success_count += 1
                    time.sleep(1.5)  # 安全防護延時，避免被封鎖 IP
            else:
                print(f"⚠️ 跳過一筆資訊不全的馬匹：馬名={h_name}, 提取到的編號={h_id}")

    # 寫出原始數據 JSON
    if target_race is not None:
        out_file = f"hkjc_career_history_raw_race_{target_race}.json"
    else:
        out_file = "hkjc_career_history_raw.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(career_raw_data, f, ensure_ascii=False, indent=4)

    print("\n" + "="*50)
    print(f"🎉 執行完畢！共成功建立 {success_count} 匹馬的生涯原始數據。")
    print(f"💾 檔案已儲存至: '{out_file}'")
    if success_count == 0:
        print("🚨 警告：最終輸出仍為空！請確認 hkjc_starters_perfect.json 中代表馬匹烙印碼（如 L148）的欄位名稱。")

if __name__ == "__main__":
    main()
