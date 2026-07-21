import numpy as np
import pandas as pd
import lightgbm as lgb
import optuna
import warnings

# Suppress LightGBM alias warnings (eval_at/ndcg_eval_at)
warnings.filterwarnings('ignore', message="Found 'eval_at' in params")
warnings.filterwarnings('ignore', message="Found 'ndcg_eval_at' in params")
warnings.filterwarnings('ignore', category=DeprecationWarning, message="The argument 'eval_set' is deprecated")

# 關閉 Optuna 的冗長日誌，只顯示精簡資訊
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ---------------------------------------------------------
# 1. 資料讀取與標籤建構
# ---------------------------------------------------------
def load_and_prepare_data(csv_path='hkjc_features_selected.csv'):
    df = pd.read_csv(csv_path)
    
    # 欄位類別定義
    metadata_cols = ['race_date', 'race_id', 'race_no', 'horse_id', 'horse_name', 'jockey', 'trainer', 'course']
    target_cols = ['target_finish_position', 'target_won']
    fold_col = ['fold']
    
    # 提取特徵欄位名稱 (45 個)
    feature_cols = [c for c in df.columns if c not in metadata_cols + target_cols + fold_col]
    
    # 轉換排名為 Relevance Grade (1名->3, 2名->2, 3名->1, 其他->0)
    def rank_to_relevance(rank):
        if rank == 1:
            return 3
        elif rank == 2:
            return 2
        elif rank == 3:
            return 1
        return 0
    
    df['relevance'] = df['target_finish_position'].apply(rank_to_relevance)
    
    return df, feature_cols

# ---------------------------------------------------------
# 2. 評估指標：Top-1 獨贏命中率 & Top-3 上名率 & Softmax 勝率
# ---------------------------------------------------------
def evaluate_predictions(df_val, pred_scores, temperature=1.0):
    df_eval = df_val.copy()
    df_eval['pred_score'] = pred_scores
    
    # 同場賽事做 Softmax 轉換為預測勝率 P_i
    def calc_softmax(group):
        scores = group['pred_score'].values / temperature
        exp_s = np.exp(scores - np.max(scores)) # 減去最大值防止數值溢位
        group['win_prob'] = exp_s / exp_s.sum()
        return group

    # groupby().apply() drops the grouping column; preserve race_id by resetting index after apply
    df_eval = df_eval.groupby('race_id', group_keys=False).apply(calc_softmax).reset_index(drop=True)
    # Ensure race_id column exists (it may have been dropped during groupby.apply)
    if 'race_id' not in df_eval.columns:
        df_eval['race_id'] = df_val.loc[df_eval.index, 'race_id'].values
    
    # 計算同場預測名次 (分數最高為 1)
    df_eval['pred_rank'] = df_eval.groupby('race_id')['pred_score'].rank(ascending=False, method='min')
    
    # 計算 Top-1 命中（預測第 1 名是否為實際頭馬）
    top1_correct = df_eval[df_eval['pred_rank'] == 1]['target_won'].sum()
    total_races = df_eval['race_id'].nunique()
    top1_acc = top1_correct / total_races if total_races > 0 else 0
    
    # 計算 Top-3 命中（預測第 1 名是否跑進實際前 3 名）
    top3_hits = df_eval[df_eval['pred_rank'] == 1]['target_finish_position'].apply(lambda r: 1 if r <= 3 else 0).sum()
    top3_hit_rate = top3_hits / total_races if total_races > 0 else 0
    
    return top1_acc, top3_hit_rate, df_eval

# ---------------------------------------------------------
# 3. Optuna 目標函數 (Objective Function)
# ---------------------------------------------------------
def create_objective(df, feature_cols):
    def objective(trial):
        # 定義搜尋空間 (eval_at passed separately to avoid alias warning)
        params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'boosting_type': 'gbdt',
            'random_state': 42,
            'verbose': -1,
            'n_estimators': trial.suggest_int('n_estimators', 100, 500),  # Increased range
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 15, 63),
            'max_depth': trial.suggest_int('max_depth', 3, 8),
            'min_child_samples': trial.suggest_int('min_child_samples', 5, 20),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 10.0, log=True),
        }
        
        cv_top1_accs = []
        
        # 進行 3-Fold 賽事分組交叉驗證
        for fold_id in [1, 2, 3]:
            # 分割訓練與驗證集
            train_df = df[df['fold'] != fold_id].sort_values(by='race_id').reset_index(drop=True)
            val_df = df[df['fold'] == fold_id].sort_values(by='race_id').reset_index(drop=True)
            
            X_train, y_train = train_df[feature_cols], train_df['relevance']
            X_val, y_val = val_df[feature_cols], val_df['relevance']
            
            # 計算 Group Array (每場比賽的馬匹數)
            train_groups = train_df.groupby('race_id', sort=False).size().values
            val_groups = val_df.groupby('race_id', sort=False).size().values
            
            # 建立並訓練 LGBMRanker (pass eval_at as separate arg to avoid alias warning)
            model = lgb.LGBMRanker(**params, eval_at=[1, 3])
            model.fit(
                X_train, y_train,
                group=train_groups,
                eval_X=X_val,
                eval_y=y_val,
                eval_group=[val_groups],
                callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]  # Increased patience
            )
            
            # 預測驗證集
            val_preds = model.predict(X_val)
            top1_acc, _, _ = evaluate_predictions(val_df, val_preds)
            cv_top1_accs.append(top1_acc)
            
        # 以 3 個 Fold 的平均 Top-1 獨贏命中率作為優化目標
        return np.mean(cv_top1_accs)
    
    return objective

# ---------------------------------------------------------
# 4. 主執行流程
# ---------------------------------------------------------
if __name__ == '__main__':
    df, feature_cols = load_and_prepare_data('hkjc_features_selected.csv')
    print(f"成功載入資料，共 {len(df)} 筆記錄，{len(feature_cols)} 個精選特徵。")
    
    print("\n=== 開始啟動 Optuna 超參數自動調校 (50 次試驗) ===")
    study = optuna.create_study(direction='maximize')
    study.optimize(create_objective(df, feature_cols), n_trials=50)
    
    print("\n" + "="*50)
    print("★ 最優化調參完成！")
    print(f"最高平均 3-Fold Top-1 命中率: {study.best_value:.2%}")
    print("\n最佳超參數設定 (Best Parameters):")
    for k, v in study.best_params.items():
        print(f"  - {k}: {v}")
    print("="*50)
    
    # ---------------------------------------------------------
    # 5. 用最佳參數訓練最終模型並輸出 Softmax 勝率示範
    # ---------------------------------------------------------
    best_params = study.best_params
    best_params.update({'objective': 'lambdarank', 'metric': 'ndcg', 'random_state': 42, 'verbose': -1})
    
    # 排序全量數據
    df_sorted = df.sort_values(by='race_id').reset_index(drop=True)
    X_all = df_sorted[feature_cols]
    y_all = df_sorted['relevance']
    groups_all = df_sorted.groupby('race_id', sort=False).size().values
    
    final_model = lgb.LGBMRanker(**best_params, eval_at=[1, 3])
    final_model.fit(X_all, y_all, group=groups_all)
    
    # 對全量數據進行評估與 Softmax 機率轉換
    df_sorted['pred_score'] = final_model.predict(X_all)
    _, _, final_result_df = evaluate_predictions(df_sorted, df_sorted['pred_score'], temperature=1.0)
    
    # 印出第一場比賽 (Race 858) 的預測勝率榜
    sample_race = final_result_df[final_result_df['race_id'] == 858].sort_values(by='win_prob', ascending=False)
    
    print("\n=== [Race 858] 模型預測勝率榜與 Softmax 結果範例 ===")
    print(sample_race[['race_id', 'horse_name', 'jockey', 'target_finish_position', 'pred_score', 'win_prob', 'pred_rank']].to_string(index=False))