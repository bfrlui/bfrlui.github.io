import pandas as pd
from sklearn.model_selection import GroupKFold

# 1. 讀取原始特徵檔案
df = pd.read_csv('hkjc_features.csv')

# 2. 定義需要保留與剔除的欄位
metadata_cols = ['race_date', 'race_id', 'race_no', 'horse_id', 'horse_name', 'jockey', 'trainer', 'course']
target_cols = ['target_finish_position', 'target_won']

# 需要剔除的冗餘/零方差特徵
drop_feature_cols = [
    'f_incident_gear_lost_flag',   # 零方差 (std=0)
    'f_declared_weight_z',         # 完全重複 (與 f_current_rating_z 相同)
    'f_draw',                       # 高度相關，保留 f_draw_pct
    'f_weight_change',              # 高度相關，保留 f_weight_change_pct
    'f_incident_count_last_5',      # 高度相關，保留 f_incident_last_days
    'f_vet_total_incidents_count',  # 高度相關，保留 f_vet_days_since_injury
    'f_career_avg_rank_last5',      # 高度相關，保留 f_career_avg_rank_last3
    'f_import_PPG'                  # 避免虛擬變數陷阱 (Dummy Trap)
]

# 3. 確定精選特徵欄位名稱 (共 45 個)
selected_features = [
    col for col in df.columns 
    if col not in metadata_cols + target_cols + drop_feature_cols
]

# 4. 組成新的資料表 (保留元數據 + 目標變數 + 45 個精選特徵)
cleaned_df = df[metadata_cols + target_cols + selected_features].copy()

# 5. 使用 GroupKFold 產生 Fold 標籤並新增至表格
gkf = GroupKFold(n_splits=3)
cleaned_df['fold'] = 0

for fold_num, (_, val_idx) in enumerate(gkf.split(cleaned_df, groups=cleaned_df['race_id']), start=1):
    cleaned_df.loc[val_idx, 'fold'] = fold_num

# 6. 匯出全新 CSV 檔案
output_filename = 'hkjc_features_selected.csv'
cleaned_df.to_csv(output_filename, index=False, encoding='utf-8-sig')

print(f"寫入成功！檔案已儲存為: {output_filename}")
print(f"新檔案總欄位數: {cleaned_df.shape[1]}（包含 8 個元數據 + 2 個目標 + 45 個精選特徵 + 1 個 Fold 標籤）")
print(f"總筆數: {cleaned_df.shape[0]} 筆")