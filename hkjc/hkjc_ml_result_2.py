import numpy as np
import pandas as pd
import lightgbm as lgb
import optuna
import warnings

# 徹底關閉各類警告訊息（包含 LightGBM 別名與 FutureWarning）
warnings.filterwarnings('ignore')
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
    
    # 1. 防範全 0 / 常數預測（退化模型）：若標準差接近 0 則評定為 0 分
    if df_eval['pred_score'].std() < 1e-6:
        df_eval['win_prob'] = df_eval.groupby('race_id')['pred_score'].transform(lambda x: 1.0 / len(x))
        df_eval['pred_rank'] = 1.0
        return 0.0, 0.0, df_eval

    # 2. 向量化計算 Softmax 預測勝率 P_i（免用 apply 以防索引錯位）
    max_scores = df_eval.groupby('race_id')['pred_score'].transform('max')
    exp_scores = np.exp((df_eval['pred_score'] - max_scores) / temperature)
    sum_exp = exp_scores.groupby(df_eval['race_id']).transform('sum')
    df_eval['win_prob'] = exp_scores / sum_exp
    
    # 3. 計算排名（使用 method='first' 避免平手全部標註為第 1 名）
    df_eval['pred_rank'] = df_eval.groupby('race_id')['pred_score'].rank(ascending=False, method='first')
    
    # 4. 嚴謹計算 Top-1 命中率與 Top-3 上名率
    total_races = df_eval['race_id'].nunique()
    top1_correct = 0.0
    top3_correct = 0.0
    
    for r, group in df_eval.groupby('race_id'):
        max_s = group['pred_score'].max()
        top_ties = group[group['pred_score'] == max_s]
        
        # 若有 N 匹馬同為最高分，頭馬在其中則獲得 1/N 分
        if top_ties['target_won'].sum() == 1:
            top1_correct += (1.0 / len(top_ties))
            
        # 預測第 1 名馬匹的實際名次
        pred_top1_horse = group[group['pred_rank'] == 1].iloc[0]
        if pred_top1_horse['target_finish_position'] <= 3:
            top3_correct += 1.0
            
    top1_acc = top1_correct / total_races if total_races > 0 else 0.0
    top3_hit_rate = top3_correct / total_races if total_races > 0 else 0.0
    
    return top1_acc, top3_hit_rate, df_eval

# ---------------------------------------------------------
# 3. Optuna 目標函數 (Objective Function)
# ---------------------------------------------------------
def create_objective(df, feature_cols):
    def objective(trial):
        # 專為小數據集調整的優化搜尋空間
        params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'boosting_type': 'gbdt',
            'random_state': 42,
            'verbose': -1,
            'n_estimators': trial.suggest_int('n_estimators', 30, 150),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 4, 15),
            'max_depth': trial.suggest_int('max_depth', 2, 5),
            'min_child_samples': trial.suggest_int('min_child_samples', 2, 8),
            'subsample': trial.suggest_float('subsample', 0.6, 0.95),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.4, 0.85),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-5, 0.5, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-5, 1.0, log=True),
        }
        
        cv_top1_accs = []
        
        # 進行 3-Fold 賽事分組交叉驗證
        for fold_id in [1, 2, 3]:
            train_df = df[df['fold'] != fold_id].sort_values(by='race_id').reset_index(drop=True)
            val_df = df[df['fold'] == fold_id].sort_values(by='race_id').reset_index(drop=True)
            
            X_train, y_train = train_df[feature_cols], train_df['relevance']
            X_val, y_val = val_df[feature_cols], val_df['relevance']
            
            train_groups = train_df.groupby('race_id', sort=False).size().values
            val_groups = val_df.groupby('race_id', sort=False).size().values
            
            model = lgb.LGBMRanker(**params, eval_at=[1, 3])
            model.fit(
                X_train, y_train,
                group=train_groups,
                eval_set=[(X_val, y_val)],
                eval_group=[val_groups],
                callbacks=[lgb.early_stopping(stopping_rounds=20, verbose=False)]
            )
            
            val_preds = model.predict(X_val)
            top1_acc, _, _ = evaluate_predictions(val_df, val_preds)
            cv_top1_accs.append(top1_acc)
            
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
    print(f"最高平均 3-Fold 嚴格 Top-1 命中率: {study.best_value:.2%}")
    print("\n最佳超參數設定 (Best Parameters):")
    for k, v in study.best_params.items():
        print(f"  - {k}: {v}")
    print("="*50)
    
    # ---------------------------------------------------------
    # 5. 用最佳參數訓練最終模型並輸出 Softmax 勝率示範
    # ---------------------------------------------------------
    best_params = study.best_params
    best_params.update({'objective': 'lambdarank', 'metric': 'ndcg', 'random_state': 42, 'verbose': -1})
    
    df_sorted = df.sort_values(by='race_id').reset_index(drop=True)
    X_all = df_sorted[feature_cols]
    y_all = df_sorted['relevance']
    groups_all = df_sorted.groupby('race_id', sort=False).size().values
    
    final_model = lgb.LGBMRanker(**best_params, eval_at=[1, 3])
    final_model.fit(X_all, y_all, group=groups_all)
    
    df_sorted['pred_score'] = final_model.predict(X_all)
    _, _, final_result_df = evaluate_predictions(df_sorted, df_sorted['pred_score'], temperature=1.0)
    
    sample_race = final_result_df[final_result_df['race_id'] == 860].sort_values(by='win_prob', ascending=False)
    
    print("\n=== [Race 860] 模型預測勝率榜與 Softmax 結果範例 ===")
    print(sample_race[['race_id', 'horse_name', 'jockey', 'target_finish_position', 'pred_score', 'win_prob', 'pred_rank']].to_string(index=False))