import pandas as pd
import json

url = "https://racing.hkjc.com/zh-hk/local/information/draw"

print("📥 正在下載馬會檔位網頁並解析所有場次...")
# 1. 抓取網頁中所有表格
tables = pd.read_html(url, encoding='utf-8')

all_races_data = {}

# 2. 自動遍歷網頁裡的所有表格
for i, df in enumerate(tables):
    has_draw_table = False
    race_title = ""
    
    # 檢查是否為雙層表頭的檔位表格
    if isinstance(df.columns, pd.MultiIndex):
        # 修正：先用 .astype(str) 安全轉換，防止非字串引發崩潰
        level_1_cols = df.columns.get_level_values(1).astype(str).str.strip()
        if '檔位' in level_1_cols:
            has_draw_table = True
            # 自動抓取第一層的文字作為場次標題
            race_title = df.columns.get_level_values(0)[0].strip()
    else:
        # 單層表頭的備用檢查
        # 修正：這裡就是原本卡死的地方，加上 .astype(str) 就安全了
        columns_str = df.columns.astype(str).str.strip()
        if '檔位' in columns_str:
            has_draw_table = True
            race_title = f"賽事場次_{i}"

    # 如果這個表格不包含「檔位」數據，就跳過
    if not has_draw_table:
        continue

    print(f"🔎 發現並正在處理：{race_title}")

    # 3. 【數據清洗】將雙層表頭拍平，只保留第二層的核心欄位名
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(1)
        
    # 修正：拍平後同樣進行安全字串轉換
    df.columns = df.columns.astype(str).str.strip()
    
    # 4. 【數據清洗】剔除類似 "Unnamed: 10_level_1" 的空垃圾欄位
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # 5. 【數據清洗】只保留純數字檔位（1-14），完美過濾掉底部的「大熱門」
    df['檔位'] = df['檔位'].astype(str).str.strip()
    df_clean = df[df['檔位'].str.isdigit()].copy()
    
    # 6. 將這一場的 DataFrame 轉成乾淨的 List of Dict
    race_records = df_clean.to_dict(orient="records")
    
    # 7. 以場次標題為 Key，塞進總資料庫
    all_races_data[race_title] = race_records

# 8. 儲存為最終的 Master JSON 檔案
output_file = "hkjc_all_races_draw.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_races_data, f, ensure_ascii=False, indent=4)

print(f"\n🎉 大功告成！全日共 {len(all_races_data)} 場賽事的檔位偏差數據已完美整合至 {output_file}")