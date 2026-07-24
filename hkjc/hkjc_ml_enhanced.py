"""
Enhanced HKJC Horse Racing ML Pipeline
=======================================
Comprehensive enhancements:
- Model persistence (joblib)
- GroupKFold CV with NDCG/MRR
- SHAP explainability
- Ensemble (LightGBM + XGBoost Ranker)
- Automated feature selection
- Betting simulation (Kelly/ROI)
- Optuna with pruning
- Experiment tracking
- Future race prediction (no targets needed)
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
import xgboost as xgb
import optuna
import joblib
import warnings
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

# Visualization
import matplotlib.pyplot as plt
import seaborn as sns

# Calibration
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import CalibratedClassifierCV

# SHAP
try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    print("SHAP not available. Install with: pip install shap")

# Metrics
from sklearn.metrics import ndcg_score
from sklearn.model_selection import GroupKFold
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

# Suppress warnings
warnings.filterwarnings('ignore')
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ============================================================
# Configuration & Data Classes
# ============================================================

@dataclass
class ModelConfig:
    """Configuration for model training"""
    n_trials: int = 100
    cv_folds: int = 5
    random_state: int = 42
    early_stopping_rounds: int = 30
    n_estimators_max: int = 500
    use_shap: bool = True
    use_ensemble: bool = True
    feature_selection_threshold: float = 0.01
    kelly_fraction: float = 0.25
    min_odds: float = 1.5
    max_odds: float = 50.0


@dataclass
class DualEnsembleConfig:
    """
    雙軌目標函數架構 (Dual-Model Ensemble: Ranker + Classifier)
    
    Model A (LGBMRanker): 負責輸出比賽的排序 (pred_rank)
    Model B (LGBMClassifier): 負責輸出馬匹的校準勝率 (win_prob)
    
    融合策略: 綜合兩者進行投注決策
    (例如: 當排序為 Top-1 且二元勝率 > 20% 時才下注)
    """
    use_ranker: bool = True
    use_classifier: bool = True
    classifier_type: str = 'lgbm'            # 'lgbm' or 'xgb'
    fusion_method: str = 'rank_then_prob'    # 'rank_then_prob', 'multiplicative', 'weighted'
    bet_threshold_rank: int = 1              # Top-N 排名門檻
    bet_threshold_prob: float = 0.20         # 勝率最低門檻
    calibrate_classifier: bool = True        # 對分類器輸出進行 Platt 校準
    ranker_weight: float = 1.0              # Multiplicative fusion 權重
    classifier_weight: float = 1.0          # Multiplicative fusion 權重
    classifier_n_trials: int = 50            # 分類器 Optuna 搜尋次數
    classifier_early_stopping: int = 30     # 分類器 Early Stopping
    min_race_confidence: float = 0.30       # 最低場次信心度：race_prob_sum 低於此值時
                                             # 表示分類器對該場整體不確定，縮減 Kelly 注碼


@dataclass
class RacePrediction:
    """Prediction result for a single race"""
    race_id: int
    race_date: str
    race_no: int
    course: str
    predictions: List[Dict[str, Any]]
    betting_recommendations: List[Dict[str, Any]]
    race_confidence_sum: Optional[float] = None

# ============================================================
# 1. Data Loading & Preparation
# ============================================================

def load_and_prepare_data(csv_path: str = 'hkjc_features_selected.csv') -> Tuple[pd.DataFrame, List[str]]:
    """Load data and prepare features/targets"""
    df = pd.read_csv(csv_path)
    
    metadata_cols = ['race_date', 'race_id', 'race_no', 'horse_id', 'horse_name', 
                     'jockey', 'trainer', 'course']
    target_cols = ['target_finish_position', 'target_won']
    fold_col = ['fold']
    
    feature_cols = [c for c in df.columns if c not in metadata_cols + target_cols + fold_col]
    
    # Convert rank to relevance grade
    def rank_to_relevance(rank):
        if rank == 1: return 3
        elif rank == 2: return 2
        elif rank == 3: return 1
        return 0
    
    df['relevance'] = df['target_finish_position'].apply(rank_to_relevance)
    
    print(f"Loaded {len(df)} records, {len(feature_cols)} features")
    print(f"Features: {feature_cols}")
    
    return df, feature_cols


def prepare_future_race_data(csv_path: str, feature_cols: List[str]) -> pd.DataFrame:
    """Prepare future race data (without target columns) for prediction"""
    df = pd.read_csv(csv_path)
    
    # Check if target columns exist
    has_targets = 'target_finish_position' in df.columns and 'target_won' in df.columns
    
    metadata_cols = ['race_date', 'race_id', 'race_no', 'horse_id', 'horse_name', 
                     'jockey', 'trainer', 'course']
    target_cols = ['target_finish_position', 'target_won']
    fold_col = ['fold']
    
    # Get available feature columns
    available_features = [c for c in feature_cols if c in df.columns]
    missing_features = [c for c in feature_cols if c not in df.columns]
    
    if missing_features:
        print(f"Warning: Missing features in future data: {missing_features}")
        # Fill missing with 0 or median
        for feat in missing_features:
            df[feat] = 0
    
    if has_targets:
        df['relevance'] = df['target_finish_position'].apply(
            lambda x: 3 if x == 1 else (2 if x == 2 else (1 if x == 3 else 0))
        )
    else:
        df['relevance'] = 0  # Placeholder for prediction
    
    return df, available_features


# ============================================================
# 2. Evaluation Metrics
# ============================================================

def evaluate_predictions(df_val: pd.DataFrame, pred_scores: np.ndarray, 
                         temperature: float = 1.0) -> Tuple[float, float, pd.DataFrame]:
    """Evaluate predictions with Top-1 accuracy, Top-3 hit rate, and softmax probabilities"""
    df_eval = df_val.copy()
    df_eval['pred_score'] = pred_scores
    
    if df_eval['pred_score'].std() < 1e-6:
        df_eval['win_prob'] = df_eval.groupby('race_id')['pred_score'].transform(
            lambda x: 1.0 / len(x))
        df_eval['pred_rank'] = 1.0
        return 0.0, 0.0, df_eval

    # Softmax probabilities
    max_scores = df_eval.groupby('race_id')['pred_score'].transform('max')
    exp_scores = np.exp((df_eval['pred_score'] - max_scores) / temperature)
    sum_exp = exp_scores.groupby(df_eval['race_id']).transform('sum')
    df_eval['win_prob'] = exp_scores / sum_exp
    
    # Rankings
    df_eval['pred_rank'] = df_eval.groupby('race_id')['pred_score'].rank(
        ascending=False, method='first')
    
    # Metrics
    total_races = df_eval['race_id'].nunique()
    top1_correct = 0.0
    top3_correct = 0.0
    
    for r, group in df_eval.groupby('race_id'):
        max_s = group['pred_score'].max()
        top_ties = group[group['pred_score'] == max_s]
        
        if top_ties['target_won'].sum() == 1:
            top1_correct += (1.0 / len(top_ties))
            
        pred_top1_horse = group[group['pred_rank'] == 1].iloc[0]
        if pred_top1_horse['target_finish_position'] <= 3:
            top3_correct += 1.0
            
    top1_acc = top1_correct / total_races if total_races > 0 else 0.0
    top3_hit_rate = top3_correct / total_races if total_races > 0 else 0.0
    
    return top1_acc, top3_hit_rate, df_eval


def calculate_ndcg_at_k(df_val: pd.DataFrame, pred_scores: np.ndarray, k: int = 3) -> float:
    """Calculate NDCG@K for ranking evaluation"""
    df_eval = df_val.copy()
    df_eval['pred_score'] = pred_scores
    
    ndcg_scores = []
    for race_id, group in df_eval.groupby('race_id'):
        y_true = group['relevance'].values
        y_pred = group['pred_score'].values
        
        if len(y_true) >= k:
            # Pad to same length for ndcg_score
            ndcg = ndcg_score([y_true], [y_pred], k=k)
            ndcg_scores.append(ndcg)
    
    return np.mean(ndcg_scores) if ndcg_scores else 0.0


def calculate_mrr(df_val: pd.DataFrame, pred_scores: np.ndarray) -> float:
    """Calculate Mean Reciprocal Rank"""
    df_eval = df_val.copy()
    df_eval['pred_score'] = pred_scores
    df_eval['pred_rank'] = df_eval.groupby('race_id')['pred_score'].rank(
        ascending=False, method='first')
    
    mrr_scores = []
    for race_id, group in df_eval.groupby('race_id'):
        winner = group[group['target_won'] == 1]
        if len(winner) > 0:
            rank = winner['pred_rank'].values[0]
            mrr_scores.append(1.0 / rank)
    
    return np.mean(mrr_scores) if mrr_scores else 0.0


# ============================================================
# Probability Calibration (Converts Ranking Scores to True Probabilities)
# ============================================================

class ProbabilityCalibrator:
    """
    Calibrates LambdaMART ranking scores to true win probabilities.
    
    Uses Platt Scaling (Logistic Regression) or Isotonic Regression
    to convert relative ranking scores into calibrated P(Win) probabilities
    suitable for Kelly betting.
    """
    
    def __init__(self, method: str = 'platt', cv_folds: int = 3):
        """
        Args:
            method: 'platt' (LogisticRegression) or 'isotonic' (IsotonicRegression)
            cv_folds: Number of CV folds for calibration training
        """
        self.method = method
        self.cv_folds = cv_folds
        self.calibrators = {}  # One calibrator per race context
        self.global_calibrator = None
    
    def _get_calibrator(self):
        """Create a new calibrator instance"""
        if self.method == 'platt':
            return LogisticRegression(solver='lbfgs', max_iter=1000, C=1.0)
        elif self.method == 'isotonic':
            return IsotonicRegression(out_of_bounds='clip')
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")
    
    def fit(self, df: pd.DataFrame, pred_scores: np.ndarray):
        """
        Fit calibrator using cross-validation to avoid overfitting.
        
        Args:
            df: DataFrame with race_id, target_won, and features
            pred_scores: Raw ranking scores from LambdaMART
        """
        df = df.copy()
        df['pred_score'] = pred_scores
        
        # Prepare calibration data: for each horse, we have (score, won)
        # We'll fit a global calibrator that maps score -> P(win)
        X_cal = df[['pred_score']].values
        y_cal = df['target_won'].values
        
        if self.method == 'platt':
            # Use CalibratedClassifierCV for Platt scaling
            base_clf = self._get_calibrator()
            self.global_calibrator = CalibratedClassifierCV(
                base_clf, method='sigmoid', cv=self.cv_folds
            )
            self.global_calibrator.fit(X_cal, y_cal)
        elif self.method == 'isotonic':
            # For isotonic, we fit directly (no CV wrapper needed for IsotonicRegression)
            # But we should use CV to avoid overfitting
            from sklearn.model_selection import cross_val_predict
            self.global_calibrator = self._get_calibrator()
            # Use cross_val_predict to get out-of-fold predictions for calibration
            # Actually, IsotonicRegression doesn't have predict_proba, so we use it directly
            self.global_calibrator.fit(X_cal.ravel(), y_cal)
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")
        
        print(f"  Calibrator fitted ({self.method}) on {len(df)} samples")
        return self
    
    def predict_proba(self, pred_scores: np.ndarray) -> np.ndarray:
        """
        Convert raw ranking scores to calibrated win probabilities.
        
        Args:
            pred_scores: Raw LambdaMART scores
            
        Returns:
            Calibrated P(Win) probabilities
        """
        if self.global_calibrator is None:
            raise ValueError("Calibrator not fitted. Call fit() first.")
        
        X = pred_scores.reshape(-1, 1)
        
        if self.method == 'platt':
            # Get probability of positive class (win)
            proba = self.global_calibrator.predict_proba(X)[:, 1]
        elif self.method == 'isotonic':
            # IsotonicRegression returns calibrated values directly
            proba = self.global_calibrator.predict(X.ravel())
            # Clip to [0, 1]
            proba = np.clip(proba, 0, 1)
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")
        
        return proba
    
    def predict_proba_per_race(self, df: pd.DataFrame, pred_scores: np.ndarray) -> np.ndarray:
        """
        Predict calibrated probabilities, then renormalize per race via softmax.
        
        This ensures probabilities sum to 1 within each race while being
        calibrated to true win rates.
        """
        df = df.copy()
        df['pred_score'] = pred_scores
        
        # Get calibrated probabilities
        calibrated = self.predict_proba(pred_scores)
        df['calibrated_prob'] = calibrated
        
        # Renormalize per race (softmax on calibrated probs)
        df['win_prob'] = df.groupby('race_id')['calibrated_prob'].transform(
            lambda x: x / x.sum() if x.sum() > 0 else 1.0 / len(x)
        )
        
        return df['win_prob'].values


def evaluate_calibration(df: pd.DataFrame, pred_scores: np.ndarray, 
                         n_bins: int = 10) -> Dict:
    """
    Evaluate calibration quality using reliability diagram metrics.
    
    Returns:
        Dict with ECE (Expected Calibration Error), MCE (Max Calibration Error)
    """
    df = df.copy()
    df['pred_score'] = pred_scores
    
    # Bin predictions
    df['bin'] = pd.qcut(df['pred_score'], q=n_bins, duplicates='drop')
    
    ece = 0.0
    mce = 0.0
    total = len(df)
    
    for bin_name, group in df.groupby('bin'):
        if len(group) == 0:
            continue
        bin_weight = len(group) / total
        avg_pred = group['pred_score'].mean()
        avg_true = group['target_won'].mean()
        bin_ece = abs(avg_pred - avg_true) * bin_weight
        ece += bin_ece
        mce = max(mce, abs(avg_pred - avg_true))
    
    return {
        'ece': ece,
        'mce': mce,
        'n_bins': n_bins
    }


# ============================================================
# Time-Based Cross-Validation (Prevents Data Leakage)
# ============================================================

class TimeSeriesGroupKFold:
    """
    Time-series aware GroupKFold that ensures training data is always 
    chronologically before validation data.
    
    This prevents data leakage where future race information could 
    leak into training when predicting past races.
    
    Falls back to GroupKFold if there's only one unique date.
    """
    
    def __init__(self, n_splits: int = 5, date_col: str = 'race_date', 
                 group_col: str = 'race_id', date_format: str = '%d/%m/%Y'):
        self.n_splits = n_splits
        self.date_col = date_col
        self.group_col = group_col
        self.date_format = date_format
    
    def split(self, X, y=None, groups=None):
        """
        Generate indices to split data into training and validation sets.
        
        Yields:
            train_idx, val_idx: Indices for training and validation sets
        """
        # Convert to DataFrame if needed
        if isinstance(X, pd.DataFrame):
            df = X.copy()
        else:
            df = pd.DataFrame(X)
        
        # Parse dates
        df['_parsed_date'] = pd.to_datetime(df[self.date_col], format=self.date_format, errors='coerce')
        
        # Get unique race dates sorted chronologically
        race_dates = df.groupby(self.group_col)['_parsed_date'].first().sort_values()
        unique_dates = race_dates.unique()
        
        # If only one unique date, fall back to GroupKFold by race_id
        if len(unique_dates) < 2:
            if not getattr(self, '_fallback_warned', False):
                print(f"Warning: Only {len(unique_dates)} unique date(s) found. Falling back to GroupKFold by race_id.")
                self._fallback_warned = True
            gkf = GroupKFold(n_splits=min(self.n_splits, df[self.group_col].nunique()))
            for train_idx, val_idx in gkf.split(df, groups=df[self.group_col]):
                yield train_idx, val_idx
            return
        
        if len(unique_dates) < self.n_splits:
            raise ValueError(f"Not enough unique dates ({len(unique_dates)}) for {self.n_splits} splits")
        
        # Create time-based splits: each fold uses earlier dates for training, later for validation
        # We split the timeline into n_splits + 1 segments, using expanding window
        n_dates = len(unique_dates)
        split_points = np.linspace(0, n_dates, self.n_splits + 1, dtype=int)[1:-1]
        
        for i, split_point in enumerate(split_points):
            # Training: all dates up to split_point
            # Validation: dates from split_point to next split_point (or end)
            train_dates = unique_dates[:split_point]
            
            if i < len(split_points) - 1:
                val_dates = unique_dates[split_point:split_points[i + 1]]
            else:
                val_dates = unique_dates[split_point:]
            
            # Get race_ids for train and validation
            train_race_ids = race_dates[race_dates.isin(train_dates)].index.values
            val_race_ids = race_dates[race_dates.isin(val_dates)].index.values
            
            # Get indices
            train_idx = df[df[self.group_col].isin(train_race_ids)].index.values
            val_idx = df[df[self.group_col].isin(val_race_ids)].index.values
            
            if len(train_idx) > 0 and len(val_idx) > 0:
                yield train_idx, val_idx
    
    def get_n_splits(self, X=None, y=None, groups=None):
        return self.n_splits


# ============================================================
# 3. Optuna Objective with Pruning (Time-Aware CV + In-Fold Feature Selection)
# ============================================================

def create_objective(df: pd.DataFrame, feature_cols: List[str], config: ModelConfig):
    """Create Optuna objective function with time-aware cross-validation
    
    Feature selection is performed INSIDE each CV fold using only training data
    to prevent data leakage.
    """
    
    def objective(trial: optuna.Trial) -> float:
        params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'boosting_type': 'gbdt',
            'random_state': config.random_state,
            'verbose': -1,
            'n_estimators': trial.suggest_int('n_estimators', 50, config.n_estimators_max),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.2, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 4, 16),
            'max_depth': trial.suggest_int('max_depth', 2, 5),
            'min_child_samples': trial.suggest_int('min_child_samples', 10, 30),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.4, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-6, 1.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-6, 2.0, log=True),
            'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 0.5),
            'min_child_weight': trial.suggest_float('min_child_weight', 1e-3, 10.0, log=True),
        }
        
        cv_scores = []
        
        # Use TimeSeriesGroupKFold for proper time-aware CV (prevents data leakage)
        tscv = TimeSeriesGroupKFold(n_splits=config.cv_folds)
        
        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(df)):
            train_df = df.iloc[train_idx].sort_values('race_id').reset_index(drop=True)
            val_df = df.iloc[val_idx].sort_values('race_id').reset_index(drop=True)
            
            # ===== FEATURE SELECTION INSIDE CV FOLD (NO LEAKAGE) =====
            # Train a quick model on training fold only to get feature importance
            quick_model = lgb.LGBMRanker(
                objective='lambdarank', metric='ndcg', random_state=42, verbose=-1,
                n_estimators=100, learning_rate=0.05, num_leaves=16, max_depth=5, min_child_samples=10
            )
            train_groups = train_df.groupby('race_id', sort=False).size().values
            quick_model.fit(
                train_df[feature_cols], train_df['relevance'],
                group=train_groups
            )
            # Select features based on training fold importance only
            fold_features = select_features_by_importance(quick_model, feature_cols, 
                                                          config.feature_selection_threshold)
            
            if len(fold_features) == 0:
                fold_features = feature_cols  # fallback
            
            X_train, y_train = train_df[fold_features], train_df['relevance']
            X_val, y_val = val_df[fold_features], val_df['relevance']
            
            val_groups = val_df.groupby('race_id', sort=False).size().values
            
            model = lgb.LGBMRanker(**params, eval_at=[1, 3, 5])
            model.fit(
                X_train, y_train,
                group=train_groups,
                eval_set=[(X_val, y_val)],
                eval_group=[val_groups],
                callbacks=[
                    lgb.early_stopping(stopping_rounds=config.early_stopping_rounds, verbose=False),
                    lgb.log_evaluation(period=0)
                ]
            )
            
            val_preds = model.predict(X_val)
            
            # Use NDCG@3 as optimization metric
            ndcg3 = calculate_ndcg_at_k(val_df, val_preds, k=3)
            cv_scores.append(ndcg3)
            
            # Report intermediate value for pruning
            trial.report(np.mean(cv_scores), fold_idx)
            
            # Prune if trial is unpromising
            if trial.should_prune():
                raise optuna.TrialPruned()
        
        return np.mean(cv_scores)
    
    return objective


# ============================================================
# 4. XGBoost Ranker Model
# ============================================================

def create_xgb_ranker(params: Dict) -> xgb.XGBRanker:
    """Create XGBoost Ranker model"""
    return xgb.XGBRanker(
        objective='rank:ndcg',
        eval_metric='ndcg@3',
        tree_method='hist',
        random_state=42,
        verbosity=0,
        **params
    )


def train_xgb_model(df: pd.DataFrame, feature_cols: List[str], 
                    best_params: Dict) -> xgb.XGBRanker:
    """Train XGBoost Ranker on full dataset"""
    df_sorted = df.sort_values('race_id').reset_index(drop=True)
    X = df_sorted[feature_cols]
    y = df_sorted['relevance']
    groups = df_sorted.groupby('race_id', sort=False).size().values
    
    params = {
        'n_estimators': best_params.get('n_estimators', 200),
        'learning_rate': best_params.get('learning_rate', 0.05),
        'max_depth': best_params.get('max_depth', 5),
        'min_child_weight': best_params.get('min_child_weight', 1),
        'subsample': best_params.get('subsample', 0.8),
        'colsample_bytree': best_params.get('colsample_bytree', 0.8),
        'reg_alpha': best_params.get('reg_alpha', 0.1),
        'reg_lambda': best_params.get('reg_lambda', 1.0),
        'gamma': best_params.get('gamma', 0),
    }
    
    model = create_xgb_ranker(params)
    model.fit(X, y, group=groups, verbose=False)
    
    return model


# ============================================================
# 5. Binary Classifier Model (Dual-Model Ensemble Part B)
# ============================================================
# 
# Model B: LGBMClassifier / XGBClassifier
# Trained on `target_won` (0/1) to output calibrated win probabilities.
# Unlike the Ranker (optimised for NDCG/ordering), the Classifier
# uses Binary Logloss to estimate precise P(Win) probabilities.

def optimize_classifier_optuna(df: pd.DataFrame, feature_cols: List[str],
                                dual_config: DualEnsembleConfig,
                                model_config: ModelConfig) -> Dict:
    """Optuna hyper-parameter search for the binary classifier (Model B)
    
    ⚠️ Feature selection is performed INSIDE each CV fold using ONLY the
    training fold to prevent data leakage — identical to the ranker's approach.
    """
    feat_threshold = model_config.feature_selection_threshold
    
    def objective(trial: optuna.Trial) -> float:
        params = {
            'learning_rate': trial.suggest_float('lr', 0.005, 0.15, log=True),
            'n_estimators': trial.suggest_int('n_est', 50, model_config.n_estimators_max),
            'num_leaves': trial.suggest_int('num_leaves', 4, 20),
            'max_depth': trial.suggest_int('max_depth', 2, 6),
            'min_child_samples': trial.suggest_int('min_child_samples', 10, 40),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.4, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-6, 1.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-6, 2.0, log=True),
            'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 0.5),
        }
        
        cv_scores = []
        tscv = TimeSeriesGroupKFold(n_splits=model_config.cv_folds)
        
        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(df)):
            train_df = df.iloc[train_idx].reset_index(drop=True)
            val_df = df.iloc[val_idx].reset_index(drop=True)
            
            # ===== IN-FOLD FEATURE SELECTION (NO LEAKAGE) =====
            # Train a quick classifier on training fold only to get feature importance
            quick_clf = lgb.LGBMClassifier(
                objective='binary', metric='binary_logloss',
                random_state=model_config.random_state, verbose=-1,
                n_estimators=100, learning_rate=0.05, num_leaves=12,
                max_depth=4, min_child_samples=10
            )
            quick_clf.fit(train_df[feature_cols], train_df['target_won'])
            
            # Select features based on training-fold importance only
            fold_features = _select_clf_features(quick_clf, feature_cols, feat_threshold)
            if len(fold_features) == 0:
                fold_features = feature_cols  # fallback
            
            X_tr, y_tr = train_df[fold_features], train_df['target_won']
            X_val, y_val = val_df[fold_features], val_df['target_won']
            
            if dual_config.classifier_type == 'lgbm':
                model = lgb.LGBMClassifier(
                    objective='binary', metric='binary_logloss',
                    random_state=model_config.random_state, verbose=-1,
                    **params
                )
                model.fit(
                    X_tr, y_tr,
                    eval_set=[(X_val, y_val)],
                    callbacks=[
                        lgb.early_stopping(dual_config.classifier_early_stopping, verbose=False),
                        lgb.log_evaluation(period=0)
                    ]
                )
            else:  # xgb
                model = xgb.XGBClassifier(
                    objective='binary:logistic', eval_metric='logloss',
                    random_state=model_config.random_state, verbosity=0,
                    n_estimators=params.get('n_est', 200),
                    learning_rate=params.get('lr', 0.05),
                    max_depth=params.get('max_depth', 4),
                    subsample=params.get('subsample', 0.8),
                    colsample_bytree=params.get('colsample_bytree', 0.8),
                    reg_alpha=params.get('reg_alpha', 0.1),
                    reg_lambda=params.get('reg_lambda', 1.0),
                    min_child_weight=params.get('min_child_weight', 1.0),
                )
                model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
            
            # Use AUC as optimisation metric (threshold-independent)
            from sklearn.metrics import roc_auc_score
            val_proba = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, val_proba)
            cv_scores.append(auc)
            
            trial.report(np.mean(cv_scores), fold_idx)
            if trial.should_prune():
                raise optuna.TrialPruned()
        
        return np.mean(cv_scores)
    
    study = optuna.create_study(
        direction='maximize',
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=3)
    )
    study.optimize(objective, n_trials=dual_config.classifier_n_trials)
    
    print(f"Classifier Optuna best AUC: {study.best_value:.4f}")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")
    
    return study.best_params


def _select_clf_features(model: lgb.LGBMClassifier, feature_cols: List[str],
                          threshold: float = 0.01) -> List[str]:
    """Select features from a trained LGBMClassifier based on gain importance"""
    importance = model.booster_.feature_importance(importance_type='gain')
    total = importance.sum()
    if total == 0:
        return feature_cols
    selected = [f for f, imp in zip(feature_cols, importance) if imp / total >= threshold]
    print(f"    [CV fold] Feature selection: {len(feature_cols)} -> {len(selected)} features")
    return selected


def train_binary_classifier(df: pd.DataFrame, feature_cols: List[str],
                             best_params: Dict,
                             dual_config: DualEnsembleConfig,
                             model_config: ModelConfig):
    """Train the binary classifier (Model B) on full dataset"""
    df_sorted = df.sort_values('race_id').reset_index(drop=True)
    X = df_sorted[feature_cols]
    y = df_sorted['target_won']
    
    if dual_config.classifier_type == 'lgbm':
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'random_state': model_config.random_state,
            'verbose': -1,
            'n_estimators': best_params.get('n_est', 200),
            'learning_rate': best_params.get('lr', 0.05),
            'num_leaves': best_params.get('num_leaves', 12),
            'max_depth': best_params.get('max_depth', 4),
            'min_child_samples': best_params.get('min_child_samples', 20),
            'subsample': best_params.get('subsample', 0.8),
            'colsample_bytree': best_params.get('colsample_bytree', 0.8),
            'reg_alpha': best_params.get('reg_alpha', 0.1),
            'reg_lambda': best_params.get('reg_lambda', 1.0),
            'min_split_gain': best_params.get('min_split_gain', 0.0),
        }
        model = lgb.LGBMClassifier(**params)
        model.fit(X, y)
    else:  # xgb
        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'logloss',
            'random_state': model_config.random_state,
            'verbosity': 0,
            'n_estimators': best_params.get('n_est', 200),
            'learning_rate': best_params.get('lr', 0.05),
            'max_depth': best_params.get('max_depth', 4),
            'subsample': best_params.get('subsample', 0.8),
            'colsample_bytree': best_params.get('colsample_bytree', 0.8),
            'reg_alpha': best_params.get('reg_alpha', 0.1),
            'reg_lambda': best_params.get('reg_lambda', 1.0),
        }
        model = xgb.XGBClassifier(**params)
        model.fit(X, y)
    
    # Apply probability calibration if requested
    calibrator_clf = None
    if dual_config.calibrate_classifier:
        calibrator_clf = CalibratedClassifierCV(
            model, method='sigmoid', cv=min(3, model_config.cv_folds)
        )
        calibrator_clf.fit(X, y)
        print(f"  Classifier calibrated with Platt scaling (CV={min(3, model_config.cv_folds)})")
    
    return model, calibrator_clf


def evaluate_classifier(model, calibrator_clf, df: pd.DataFrame,
                         feature_cols: List[str]) -> Dict:
    """Evaluate classifier performance"""
    from sklearn.metrics import (roc_auc_score, average_precision_score,
                                  brier_score_loss, log_loss)
    
    df_sorted = df.sort_values('race_id').reset_index(drop=True)
    X = df_sorted[feature_cols]
    y_true = df_sorted['target_won']
    
    if calibrator_clf is not None:
        y_prob = calibrator_clf.predict_proba(X)[:, 1]
    else:
        y_prob = model.predict_proba(X)[:, 1]
    
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    brier = brier_score_loss(y_true, y_prob)
    ll = log_loss(y_true, y_prob)
    
    # Per-race calibration: sort by prob within each race
    df_eval = df_sorted.copy()
    df_eval['clf_prob'] = y_prob
    # Win rate by probability decile
    df_eval['prob_decile'] = pd.qcut(df_eval['clf_prob'], q=10, duplicates='drop', labels=False)
    calib_data = df_eval.groupby('prob_decile').agg(
        mean_pred=('clf_prob', 'mean'),
        mean_actual=('target_won', 'mean'),
        count=('target_won', 'count')
    ).reset_index()
    
    metrics = {
        'auc': auc,
        'avg_precision': ap,
        'brier_score': brier,
        'log_loss': ll,
        'n_winners': int(y_true.sum()),
        'n_horses': len(y_true),
        'baseline_acc': max(y_true.mean(), 1 - y_true.mean()),
    }
    
    print(f"\nClassifier Evaluation:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    
    return metrics


# ============================================================
# 6. Dual Ensemble Fusion (Ranker + Classifier)
# ============================================================
#
# Combines Model A (Ranker -> pred_rank) and Model B (Classifier -> win_prob)
# to produce a single fused decision for betting.

class DualEnsemblePredictor:
    """
    雙軌目標函數 (Dual-Model Ensemble) 預測器
    
    Model A - Ranker: 提供場內相對排序 (pred_rank)
    Model B - Classifier: 提供絕對校準勝率 (win_prob)
    
    融合策略:
      - 'rank_then_prob': 先用 Ranker 選出 Top-N，再用 Classifier 的 win_prob 做門檻篩選
      - 'multiplicative': fused_score = (ranker_score^ranker_weight) * (clf_prob^clf_weight)
      - 'weighted': fused_score = ranker_weight * norm_ranker_score + clf_weight * clf_prob
    """
    
    def __init__(self, ranker_models: Dict[str, Any],
                 classifier_model,
                 classifier_calibrator,
                 feature_cols: List[str],
                 ranker_weights: Optional[Dict[str, float]] = None,
                 dual_config: Optional[DualEnsembleConfig] = None):
        self.ranker_models = ranker_models
        self.classifier_model = classifier_model
        self.classifier_calibrator = classifier_calibrator
        self.feature_cols = feature_cols
        self.ranker_weights = ranker_weights
        self.dual_config = dual_config or DualEnsembleConfig()
    
    def predict(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Predict using both Ranker and Classifier.
        
        Returns:
            ranker_scores: Raw scores from Ranker ensemble
            clf_probs: Win probabilities from Classifier
            fused_scores: Combined scores (depends on fusion_method)
        """
        X_use = X[self.feature_cols].fillna(0)
        
        # Model A: Ranker scores
        if self.ranker_models and self.dual_config.use_ranker:
            ranker_scores = ensemble_predict(self.ranker_models, X_use, self.ranker_weights)
        else:
            ranker_scores = np.zeros(len(X_use))
        
        # Model B: Classifier probabilities
        if self.classifier_model is not None and self.dual_config.use_classifier:
            if self.classifier_calibrator is not None:
                clf_probs = self.classifier_calibrator.predict_proba(X_use)[:, 1]
            else:
                clf_probs = self.classifier_model.predict_proba(X_use)[:, 1]
        else:
            clf_probs = np.ones(len(X_use)) * 0.5
        
        # Fuse
        fused_scores = self._fuse(ranker_scores, clf_probs)
        
        return ranker_scores, clf_probs, fused_scores
    
    def _fuse(self, ranker_scores: np.ndarray, clf_probs: np.ndarray) -> np.ndarray:
        """Apply the configured fusion method"""
        method = self.dual_config.fusion_method
        rw = self.dual_config.ranker_weight
        cw = self.dual_config.classifier_weight
        
        if method == 'rank_then_prob':
            # Use ranker for ordering, classifier for confidence
            # Normalise ranker scores to [0, 1] for compatibility
            r_min, r_max = ranker_scores.min(), ranker_scores.max()
            if r_max > r_min:
                norm_ranker = (ranker_scores - r_min) / (r_max - r_min)
            else:
                norm_ranker = np.ones_like(ranker_scores)
            fused = norm_ranker * clf_probs
        
        elif method == 'multiplicative':
            # Geometric mean weighted: (ranker^rw) * (clf^cw)
            ranker_pos = ranker_scores - ranker_scores.min() + 1e-8
            fused = (ranker_pos ** rw) * (clf_probs ** cw)
        
        elif method == 'weighted':
            # Linear weighted sum
            r_min, r_max = ranker_scores.min(), ranker_scores.max()
            if r_max > r_min:
                norm_ranker = (ranker_scores - r_min) / (r_max - r_min)
            else:
                norm_ranker = np.ones_like(ranker_scores)
            fused = rw * norm_ranker + cw * clf_probs
            total = rw + cw
            if total > 0:
                fused = fused / total
        
        else:
            # Default: just clf prob
            fused = clf_probs
        
        return fused
    
    def predict_per_race(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Full per-race prediction with both models.
        Returns DataFrame with pred_rank (from Ranker), win_prob (from Classifier),
        and race_prob_sum (total raw classifier confidence per race — see Trap 2).
        """
        result = df.copy()
        
        ranker_scores, clf_probs, fused_scores = self.predict(df)
        result['ranker_score'] = ranker_scores
        result['clf_win_prob'] = clf_probs
        result['fused_score'] = fused_scores
        
        # Per-race ranking from Ranker scores
        result['pred_rank'] = result.groupby('race_id')['ranker_score'].rank(
            ascending=False, method='first')
        
        # ⚠️ Trap 2: Per-race normalised win probability from Classifier.
        #   LGBMClassifier outputs independent binary probabilities (each in [0,1]).
        #   Forcing x / x.sum() is standard but can inflate probabilities in "cold"
        #   races where all horses have low raw scores (sum << 1).
        #   We carry race_prob_sum alongside as a confidence signal.
        result['race_prob_sum'] = result.groupby('race_id')['clf_win_prob'].transform('sum')
        result['win_prob'] = result.groupby('race_id')['clf_win_prob'].transform(
            lambda x: x / x.sum() if x.sum() > 0 else 1.0 / len(x)
        )
        
        # Fused rank (for combined ordering)
        result['fused_rank'] = result.groupby('race_id')['fused_score'].rank(
            ascending=False, method='first')
        
        return result


def make_fusion_betting_decisions(df_eval: pd.DataFrame,
                                   dual_config: DualEnsembleConfig,
                                   kelly_fraction: float = 0.25,
                                   min_odds: float = 1.5,
                                   max_odds: float = 50.0,
                                   odds_col: str = 'market_odds',
                                   initial_bankroll: float = 100.0) -> Dict:
    """
    Fusion betting strategy using Dual-Model Ensemble with dynamic bankroll.
    
    Rule: Bet only when Ranker says Top-N AND Classifier says win_prob > threshold.
    Combines the ranking power of LambdaMART with the calibrated
    probability estimation of the binary classifier.
    
    ⚠️ Trap 2 — Race-Confidence Gate:
        LGBMClassifier outputs independent binary probabilities. After per-race
        normalisation (x / x.sum()), a "cold" race where all horses have low raw
        probabilities (sum << 1) gets artificially inflated. We use race_prob_sum
        as a confidence signal:
          - If race_prob_sum < min_race_confidence → skip the race entirely
            (classifier has no conviction about any horse)
          - Otherwise, scale down Kelly fraction by race_prob_sum as an
            additional conservative factor.
    
    ⚠️ Trap 3 — Dynamic Bankroll (已修復):
        過去固定使用 stake = kelly_bet × 100，忽略資金動態。
        現改為 current_bankroll 隨每場結果滾動更新，實現 Kelly 複利效果。
    """
    min_confidence = dual_config.min_race_confidence
    has_confidence_col = 'race_prob_sum' in df_eval.columns
    current_bankroll = initial_bankroll
    peak_bankroll = initial_bankroll
    max_drawdown = 0.0
    
    results = {
        'total_races': 0,
        'total_bets': 0,
        'total_stake': 0.0,
        'total_return': 0.0,
        'roi': 0.0,
        'win_rate': 0.0,
        'fusion_bets': [],
        'takeout_rate': 0.175,
        'bet_threshold_rank': dual_config.bet_threshold_rank,
        'bet_threshold_prob': dual_config.bet_threshold_prob,
        'min_race_confidence': min_confidence,
        'races_skipped_low_confidence': 0,
        'initial_bankroll': initial_bankroll,
        'final_bankroll': initial_bankroll,
        'max_drawdown': 0.0,
        'bankroll_history': [],
    }
    
    # Ensure chronological order (race_date + race_no) for dynamic bankroll
    df_eval = df_eval.sort_values(['race_date', 'race_no']).reset_index(drop=True)
    
    for race_id, group in df_eval.groupby('race_id'):
        results['total_races'] += 1
        
        # ── Race-Confidence Gate ──
        race_confidence = group['race_prob_sum'].iloc[0] if has_confidence_col else 1.0
        if has_confidence_col and race_confidence < min_confidence:
            results['races_skipped_low_confidence'] += 1
            continue
        
        # Confidence-adjusted Kelly multiplier: when raw sum is low but above min,
        # reduce bet size proportionally (e.g. sum=0.5 → half the usual Kelly)
        confidence_mult = min(1.0, race_confidence / min_confidence) if has_confidence_col else 1.0
        
        group = group.sort_values('pred_rank', ascending=True)
        
        # Top-N by Ranker
        top_n_horses = group[group['pred_rank'] <= dual_config.bet_threshold_rank]
        
        for _, horse in top_n_horses.iterrows():
            prob = horse.get('win_prob', horse.get('clf_win_prob', 0))
            
            # Classifier probability threshold
            if prob < dual_config.bet_threshold_prob:
                continue
            
            market_odds = horse.get(odds_col, np.nan)
            if pd.isna(market_odds) or market_odds < min_odds or market_odds > max_odds:
                continue
            
            implied_prob = 1.0 / market_odds
            edge = prob - implied_prob
            
            if edge <= 0:
                continue
            
            b = market_odds - 1
            kelly_bet = edge / b if b > 0 else 0
            kelly_bet = max(0, kelly_bet * kelly_fraction * confidence_mult)
            
            if kelly_bet > 0.01:
                stake = kelly_bet * current_bankroll  # Dynamic bankroll
                won = horse['target_won'] == 1
                return_amount = stake * market_odds if won else 0
                
                # Update bankroll
                current_bankroll += return_amount - stake
                peak_bankroll = max(peak_bankroll, current_bankroll)
                max_drawdown = max(max_drawdown, (peak_bankroll - current_bankroll) / peak_bankroll)
                
                results['total_bets'] += 1
                results['total_stake'] += stake
                results['total_return'] += return_amount
                results['bankroll_history'].append({
                    'race_id': race_id,
                    'bankroll_before': current_bankroll - (return_amount - stake),
                    'bankroll_after': current_bankroll,
                })
                results['fusion_bets'].append({
                    'race_id': race_id,
                    'horse': horse['horse_name'],
                    'pred_rank': int(horse['pred_rank']),
                    'clf_win_prob': float(prob),
                    'race_confidence': float(race_confidence),
                    'confidence_mult': float(confidence_mult),
                    'implied_prob': float(implied_prob),
                    'edge': float(edge),
                    'market_odds': float(market_odds),
                    'kelly_fraction': float(kelly_bet),
                    'kelly_stake_pct': float(kelly_bet),
                    'stake': float(stake),
                    'won': bool(won),
                    'return': float(return_amount),
                })
                break  # One bet per race
    
    results['final_bankroll'] = current_bankroll
    results['max_drawdown'] = max_drawdown
    results['bankroll_change_pct'] = (current_bankroll - initial_bankroll) / initial_bankroll
    
    if results['total_stake'] > 0:
        results['roi'] = (results['total_return'] - results['total_stake']) / results['total_stake']
        results['win_rate'] = sum(b['won'] for b in results['fusion_bets']) / results['total_bets']
    
    return results


def print_fusion_results(results: Dict):
    """Print dual-model fusion betting results (with dynamic bankroll)"""
    min_conf = results.get('min_race_confidence', 'N/A')
    races_skipped = results.get('races_skipped_low_confidence', 0)
    init_bankroll = results.get('initial_bankroll', results['total_stake'] / 20 if results['total_bets'] > 0 else 100)
    final_bankroll = results.get('final_bankroll', init_bankroll)
    max_dd = results.get('max_drawdown', 0.0)
    bankroll_chg = results.get('bankroll_change_pct', (final_bankroll - init_bankroll) / init_bankroll)
    
    print("\n" + "="*55)
    print("DUAL-MODEL FUSION BETTING RESULTS")
    print(f"  Rule: Top-{results['bet_threshold_rank']} AND win_prob > {results['bet_threshold_prob']:.0%}")
    if races_skipped:
        print(f"  ⚠️  Races skipped (low confidence < {min_conf}): {races_skipped}")
    print("="*55)
    print(f"Total Races: {results['total_races']}")
    print(f"Total Bets Placed: {results['total_bets']}")
    print(f"Total Stake: {results['total_stake']:.2f}")
    print(f"Total Return: {results['total_return']:.2f}")
    print(f"ROI: {results['roi']:.2%}")
    print(f"Win Rate: {results['win_rate']:.2%}")
    print(f"── Dynamic Bankroll ──")
    print(f"Initial Bankroll: {init_bankroll:.2f}")
    print(f"Final Bankroll:   {final_bankroll:.2f}")
    print(f"Bankroll Change:  {bankroll_chg:+.2%}")
    print(f"Max Drawdown:     {max_dd:.2%}")
    print("="*55)


# ============================================================
# 7. Ensemble Prediction (Ranker Model Averaging)
# ============================================================

def ensemble_predict(models: Dict[str, Any], X: pd.DataFrame, 
                     weights: Optional[Dict[str, float]] = None) -> np.ndarray:
    """Combine predictions from multiple ranker models"""
    if weights is None:
        weights = {name: 1.0 for name in models.keys()}
    
    # Normalize weights
    total_weight = sum(weights.values())
    weights = {k: v/total_weight for k, v in weights.items()}
    
    predictions = np.zeros(len(X))
    for name, model in models.items():
        pred = model.predict(X)
        predictions += weights[name] * pred
    
    return predictions


# ============================================================
# 8. Feature Selection
# ============================================================

def select_features_by_importance(model: lgb.LGBMRanker, feature_cols: List[str], 
                                   threshold: float = 0.01) -> List[str]:
    """Select features based on importance threshold"""
    importance = model.booster_.feature_importance(importance_type='gain')
    total_importance = importance.sum()
    
    selected = []
    for feat, imp in zip(feature_cols, importance):
        if imp / total_importance >= threshold:
            selected.append(feat)
    
    print(f"Feature selection: {len(feature_cols)} -> {len(selected)} features "
          f"(threshold: {threshold:.1%})")
    return selected


def recursive_feature_elimination(df: pd.DataFrame, feature_cols: List[str], 
                                   config: ModelConfig, n_iterations: int = 3) -> List[str]:
    """Recursive feature elimination based on CV performance"""
    current_features = feature_cols.copy()
    best_score = 0
    
    for iteration in range(n_iterations):
        print(f"\nRFE Iteration {iteration + 1}/{n_iterations}: {len(current_features)} features")
        
        # Quick CV with current features (time-aware)
        tscv = TimeSeriesGroupKFold(n_splits=3)
        scores = []
        
        for train_idx, val_idx in tscv.split(df):
            train_df = df.iloc[train_idx]
            val_df = df.iloc[val_idx]
            
            model = lgb.LGBMRanker(
                objective='lambdarank', metric='ndcg', random_state=42, verbose=-1,
                n_estimators=100, learning_rate=0.05, num_leaves=16, max_depth=5, min_child_samples=10
            )
            model.fit(
                train_df[current_features], train_df['relevance'],
                group=train_df.groupby('race_id').size().values,
                eval_set=[(val_df[current_features], val_df['relevance'])],
                eval_group=[val_df.groupby('race_id').size().values],
                callbacks=[lgb.early_stopping(20, verbose=False)]
            )
            
            preds = model.predict(val_df[current_features])
            scores.append(calculate_ndcg_at_k(val_df, preds, k=3))
        
        mean_score = np.mean(scores)
        print(f"  CV NDCG@3: {mean_score:.4f}")
        
        if mean_score > best_score:
            best_score = mean_score
            best_features = current_features.copy()
        
        # Remove bottom 20% features by importance
        if len(current_features) > 10:
            model = lgb.LGBMRanker(
                objective='lambdarank', metric='ndcg', random_state=42, verbose=-1,
                n_estimators=100, learning_rate=0.05, num_leaves=16, max_depth=5, min_child_samples=10
            )
            model.fit(
                df[current_features], df['relevance'],
                group=df.groupby('race_id').size().values
            )
            current_features = select_features_by_importance(model, current_features, 0.005)
    
    return best_features


# ============================================================
# 9. SHAP Explainability
# ============================================================

def compute_shap_values(model: lgb.LGBMRanker, X: pd.DataFrame, 
                        feature_cols: List[str], sample_size: int = 500) -> np.ndarray:
    """Compute SHAP values for model explanations"""
    if not SHAP_AVAILABLE:
        print("SHAP not available, skipping...")
        return None
    
    # Sample data for faster computation
    if len(X) > sample_size:
        X_sample = X.sample(n=sample_size, random_state=42)
    else:
        X_sample = X
    
    explainer = shap.TreeExplainer(model.booster_)
    shap_values = explainer.shap_values(X_sample[feature_cols])
    
    return shap_values


def plot_shap_summary(shap_values: np.ndarray, X: pd.DataFrame, 
                      feature_cols: List[str], save_path: str = 'shap_summary.png'):
    """Plot SHAP summary"""
    if not SHAP_AVAILABLE or shap_values is None:
        return
    
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X[feature_cols], plot_type="bar", show=False)
    plt.title('SHAP Feature Importance (Mean |SHAP Value|)', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"SHAP summary saved to {save_path}")


def plot_shap_dependence(shap_values: np.ndarray, X: pd.DataFrame, 
                         feature_cols: List[str], top_n: int = 5, 
                         save_dir: str = 'shap_plots'):
    """Plot SHAP dependence plots for top features"""
    if not SHAP_AVAILABLE or shap_values is None:
        return
    
    os.makedirs(save_dir, exist_ok=True)
    
    # Get mean absolute SHAP values per feature
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    top_features_idx = np.argsort(mean_abs_shap)[-top_n:]
    
    for idx in top_features_idx:
        feat_name = feature_cols[idx]
        plt.figure(figsize=(8, 6))
        shap.dependence_plot(idx, shap_values, X[feature_cols], show=False)
        plt.title(f'SHAP Dependence: {feat_name}', fontsize=12)
        plt.tight_layout()
        plt.savefig(f'{save_dir}/shap_dependence_{feat_name}.png', dpi=300)
        plt.close()
    
    print(f"SHAP dependence plots saved to {save_dir}/")


# ============================================================
# 10. Betting Simulation
# ============================================================

def simulate_betting(df_eval: pd.DataFrame, kelly_fraction: float = 0.25,
                     min_odds: float = 1.5, max_odds: float = 50.0,
                     takeout_rate: float = 0.175,
                     odds_col: str = 'market_odds',
                     initial_bankroll: float = 100.0) -> Dict:
    """
    Simulate betting strategy using REAL market odds with dynamic bankroll.
    
    ⚠️ Trap 3 — Static Bankroll 已修復：
        過去版本固定使用 stake = kelly_bet × 100，忽略資金動態變化。
        現改為 current_bankroll 隨每場結果滾動更新，實現 Kelly 複利效果，
        並提供最大回撤 (max_drawdown) 作為風險指標。
    
    Args:
        df_eval: DataFrame with predictions and actual results
        kelly_fraction: Fraction of Kelly bet to use (0.25 = quarter Kelly)
        min_odds: Minimum odds to consider betting
        max_odds: Maximum odds to consider betting
        takeout_rate: HKJC takeout rate (17.5% for win bets)
        odds_col: Column name containing real market odds
        initial_bankroll: Starting bankroll (default 100 units)
        
    Returns:
        Dict with betting results including bankroll tracking
        
    Note: This function REQUIRES real market odds in the data.
    Without real odds, the simulation is NOT valid for real betting.
    """
    # Check for real odds
    if odds_col not in df_eval.columns:
        raise ValueError(
            f"Real market odds required! Column '{odds_col}' not found in data. "
            f"Please add live market odds (e.g., from HKJC live odds feed) "
            f"before running betting simulation."
        )
    
    current_bankroll = initial_bankroll
    peak_bankroll = initial_bankroll
    max_drawdown = 0.0
    
    results = {
        'total_races': 0,
        'total_bets': 0,
        'total_stake': 0.0,
        'total_return': 0.0,
        'roi': 0.0,
        'win_rate': 0.0,
        'bets': [],
        'takeout_rate': takeout_rate,
        'initial_bankroll': initial_bankroll,
        'final_bankroll': initial_bankroll,
        'max_drawdown': 0.0,
        'bankroll_history': [],
    }
    
    # Ensure chronological order (race_date + race_no) for dynamic bankroll
    df_eval = df_eval.sort_values(['race_date', 'race_no']).reset_index(drop=True)
    
    for race_id, group in df_eval.groupby('race_id'):
        results['total_races'] += 1
        
        # Sort by win probability (model's predicted win prob)
        group = group.sort_values('win_prob', ascending=False)
        
        # Get real market odds for each horse
        # Apply takeout: true odds = market_odds * (1 - takeout_rate)
        # But we bet at market_odds, so our edge is based on true probability
        for _, horse in group.iterrows():
            market_odds = horse.get(odds_col, np.nan)
            
            if pd.isna(market_odds) or market_odds < min_odds or market_odds > max_odds:
                continue
            
            # True probability after takeout
            # Market implied prob = 1/market_odds
            # True prob = implied_prob / (1 - takeout_rate)  [roughly]
            # But simpler: our edge = model_prob - (1/market_odds)
            model_prob = horse['win_prob']
            implied_prob = 1.0 / market_odds
            
            # Edge = model_prob - implied_prob
            edge = model_prob - implied_prob
            
            if edge <= 0:
                continue  # No edge, don't bet
            
            # Kelly: f = edge / (odds - 1)
            b = market_odds - 1
            kelly_bet = edge / b if b > 0 else 0
            kelly_bet = max(0, kelly_bet * kelly_fraction)
            
            if kelly_bet > 0.01:  # Minimum bet threshold
                stake = kelly_bet * current_bankroll  # Dynamic bankroll
                won = horse['target_won'] == 1
                # Return at market odds (we bet at market odds)
                return_amount = stake * market_odds if won else 0
                
                # Update bankroll
                current_bankroll += return_amount - stake
                peak_bankroll = max(peak_bankroll, current_bankroll)
                max_drawdown = max(max_drawdown, (peak_bankroll - current_bankroll) / peak_bankroll)
                
                results['total_bets'] += 1
                results['total_stake'] += stake
                results['total_return'] += return_amount
                results['bankroll_history'].append({
                    'race_id': race_id,
                    'bankroll_before': current_bankroll - (return_amount - stake),
                    'bankroll_after': current_bankroll,
                })
                results['bets'].append({
                    'race_id': race_id,
                    'horse': horse['horse_name'],
                    'model_prob': model_prob,
                    'implied_prob': implied_prob,
                    'edge': edge,
                    'market_odds': market_odds,
                    'kelly_fraction': kelly_bet,
                    'stake': stake,
                    'won': won,
                    'return': return_amount
                })
                break  # Only bet on top edge horse per race
    
    results['final_bankroll'] = current_bankroll
    results['max_drawdown'] = max_drawdown
    results['bankroll_change_pct'] = (current_bankroll - initial_bankroll) / initial_bankroll
    
    if results['total_stake'] > 0:
        results['roi'] = (results['total_return'] - results['total_stake']) / results['total_stake']
        results['win_rate'] = sum(b['won'] for b in results['bets']) / results['total_bets']
    
    return results


def print_betting_results(results: Dict):
    """Print betting simulation results (with dynamic bankroll tracking)"""
    init_bankroll = results.get('initial_bankroll', results['total_stake'] / 20 if results['total_bets'] > 0 else 100)
    final_bankroll = results.get('final_bankroll', init_bankroll)
    max_dd = results.get('max_drawdown', 0.0)
    bankroll_chg = results.get('bankroll_change_pct', (final_bankroll - init_bankroll) / init_bankroll)
    
    print("\n" + "="*50)
    print("BETTING SIMULATION RESULTS")
    print("="*50)
    print(f"Total Races: {results['total_races']}")
    print(f"Total Bets Placed: {results['total_bets']}")
    print(f"Total Stake: {results['total_stake']:.2f}")
    print(f"Total Return: {results['total_return']:.2f}")
    print(f"ROI: {results['roi']:.2%}")
    print(f"Win Rate: {results['win_rate']:.2%}")
    print(f"── Dynamic Bankroll ──")
    print(f"Initial Bankroll: {init_bankroll:.2f}")
    print(f"Final Bankroll:   {final_bankroll:.2f}")
    print(f"Bankroll Change:  {bankroll_chg:+.2%}")
    print(f"Max Drawdown:     {max_dd:.2%}")
    print("="*50)


# ============================================================
# 11. Experiment Tracking
# ============================================================

class ExperimentTracker:
    """Simple experiment tracking"""
    
    def __init__(self, log_dir: str = 'experiments'):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.experiment_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = self.log_dir / f'experiment_{self.experiment_id}.json'
        self.data = {
            'experiment_id': self.experiment_id,
            'timestamp': datetime.now().isoformat(),
            'config': {},
            'results': {},
            'models': {}
        }
    
    def log_config(self, config: ModelConfig):
        self.data['config'] = asdict(config)
        self._save()
    
    def log_results(self, results: Dict):
        self.data['results'] = results
        self._save()
    
    def log_model(self, name: str, params: Dict, metrics: Dict):
        self.data['models'][name] = {
            'params': params,
            'metrics': metrics,
            'timestamp': datetime.now().isoformat()
        }
        self._save()
    
    def _save(self):
        with open(self.log_file, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
    
    def get_best_model(self) -> Optional[str]:
        if not self.data['models']:
            return None
        return max(self.data['models'].items(), 
                   key=lambda x: x[1]['metrics'].get('ndcg@3', 0))[0]


# ============================================================
# 12. Future Race Prediction Pipeline
# ============================================================

def predict_future_races(models: Dict[str, Any], future_df: pd.DataFrame, 
                         feature_cols: List[str], weights: Optional[Dict] = None,
                         dual_predictor: Optional['DualEnsemblePredictor'] = None,
                         dual_config: Optional[DualEnsembleConfig] = None) -> List[RacePrediction]:
    """Predict on future race data without targets
    
    Args:
        models: Dict of ranker models
        future_df: DataFrame with future race features
        feature_cols: List of feature column names
        weights: Optional weights for ranker ensemble
        dual_predictor: Optional DualEnsemblePredictor for dual-model fusion
        dual_config: Optional DualEnsembleConfig for fusion betting rules
    
    Returns:
        List of RacePrediction objects
    """
    predictions = []
    
    # Prepare features
    X_future = future_df[feature_cols].fillna(0)
    
    if dual_predictor is not None:
        # === DUAL-MODEL PREDICTION PATH ===
        # Use Ranker for ranking AND Classifier for calibrated win probabilities
        ranker_scores, clf_probs, fused_scores = dual_predictor.predict(X_future)
        future_df = future_df.copy()
        future_df['ranker_score'] = ranker_scores
        future_df['clf_win_prob'] = clf_probs
        future_df['fused_score'] = fused_scores
        
        # Per-race ranking from Ranker
        future_df['pred_rank'] = future_df.groupby('race_id')['ranker_score'].rank(
            ascending=False, method='first')
        
        # Per-race win probability from Classifier (renormalised)
        future_df['win_prob'] = future_df.groupby('race_id')['clf_win_prob'].transform(
            lambda x: x / x.sum() if x.sum() > 0 else 1.0 / len(x)
        )
        
        # ⚠️ Trap 2 — Race-confidence signal: carry raw sum alongside normalised prob
        future_df['race_prob_sum'] = future_df.groupby('race_id')['clf_win_prob'].transform('sum')
        
        # Also keep ranker-based softmax for comparison
        for race_id, group in future_df.groupby('race_id'):
            scores = group['ranker_score'].values
            max_score = scores.max()
            exp_scores = np.exp(scores - max_score)
            ranker_win_probs = exp_scores / exp_scores.sum()
            future_df.loc[group.index, 'ranker_win_prob'] = ranker_win_probs
        
        sort_col = 'win_prob'  # Sort by classifier probability for final output
    else:
        # === ORIGINAL RANKER-ONLY PATH ===
        ensemble_scores = ensemble_predict(models, X_future, weights)
        future_df = future_df.copy()
        future_df['ranker_score'] = ensemble_scores
        future_df['clf_win_prob'] = np.nan  # No classifier available
        future_df['fused_score'] = ensemble_scores
        
        # Softmax per race
        for race_id, group in future_df.groupby('race_id'):
            scores = group['ranker_score'].values
            max_score = scores.max()
            exp_scores = np.exp(scores - max_score)
            win_probs = exp_scores / exp_scores.sum()
            future_df.loc[group.index, 'win_prob'] = win_probs
        
        future_df['pred_rank'] = future_df.groupby('race_id')['ranker_score'].rank(
            ascending=False, method='first')
        
        sort_col = 'win_prob'
    
    # Build prediction outputs per race
    for race_id, group in future_df.groupby('race_id'):
        race_info = group.iloc[0]
        group = group.sort_values(sort_col, ascending=False)
        
        horse_preds = []
        for _, row in group.iterrows():
            pred = {
                'horse_id': row['horse_id'],
                'horse_name': row['horse_name'],
                'jockey': row['jockey'],
                'trainer': row['trainer'],
                'draw': row.get('f_draw_pct', 0),
                'pred_score': float(row['ranker_score']),
                'win_prob': float(row['win_prob']),
                'pred_rank': int(row['pred_rank']),
                'clf_win_prob': float(row['clf_win_prob']) if not pd.isna(row['clf_win_prob']) else None,
            }
            horse_preds.append(pred)
        
        # ⚠️ Trap 2 — Race confidence (raw classifier probability sum)
        race_confidence_sum = float(group['race_prob_sum'].iloc[0]) \
            if 'race_prob_sum' in group.columns else 1.0
        
        # Dual-model fusion betting recommendations
        dc = dual_config or DualEnsembleConfig()
        min_conf = getattr(dc, 'min_race_confidence', 0.30)
        low_confidence_race = dual_predictor is not None and race_confidence_sum < min_conf
        
        betting_recs = []
        for i, hp in enumerate(horse_preds[:5]):
            prob = hp['clf_win_prob'] if hp['clf_win_prob'] is not None else hp['win_prob']
            implied_odds = 1.0 / prob if prob and prob > 0 else 999
            
            # Dual fusion rule: Top-N by Ranker AND prob > threshold
            rank_ok = hp['pred_rank'] <= dc.bet_threshold_rank
            prob_ok = (hp['clf_win_prob'] is not None and hp['clf_win_prob'] >= dc.bet_threshold_prob) \
                      if dual_predictor is not None else (hp['win_prob'] >= dc.bet_threshold_prob)
            
            if low_confidence_race:
                # Low race confidence → downgrade recommendation
                rec = 'WATCH' if rank_ok and prob_ok else 'PASS'
            elif rank_ok and prob_ok and dual_predictor is not None:
                rec = 'STRONG_BET'
            elif hp['win_prob'] > 0.20:
                rec = 'BET'
            elif hp['win_prob'] > 0.10:
                rec = 'WATCH'
            else:
                rec = 'PASS'
            
            betting_recs.append({
                'rank': i + 1,
                'horse_name': hp['horse_name'],
                'win_prob': hp['win_prob'],
                'clf_win_prob': hp['clf_win_prob'],
                'pred_rank': hp['pred_rank'],
                'implied_odds': implied_odds,
                'recommendation': rec,
                'fusion_trigger': rank_ok and prob_ok and dual_predictor is not None,
                'race_confidence_sum': race_confidence_sum,
            })
        
        predictions.append(RacePrediction(
            race_id=int(race_id),
            race_date=str(race_info['race_date']),
            race_no=int(race_info['race_no']),
            course=str(race_info['course']),
            predictions=horse_preds,
            betting_recommendations=betting_recs,
            race_confidence_sum=race_confidence_sum
        ))
    
    return predictions


def save_predictions(predictions: List[RacePrediction], output_path: str):
    """Save predictions to JSON and CSV"""
    # JSON
    json_data = [asdict(p) for p in predictions]
    with open(output_path.replace('.csv', '.json'), 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # CSV (flattened)
    rows = []
    for p in predictions:
        for hp in p.predictions:
            rows.append({
                'race_id': p.race_id,
                'race_date': p.race_date,
                'race_no': p.race_no,
                'course': p.course,
                **hp
            })
    
    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"Predictions saved to {output_path} and {output_path.replace('.csv', '.json')}")


# ============================================================
# 13. Model Persistence
# ============================================================

def save_model(model: Any, feature_cols: List[str], params: Dict, 
               metrics: Dict, path: str):
    """Save model with metadata"""
    model_data = {
        'model': model,
        'feature_cols': feature_cols,
        'params': params,
        'metrics': metrics,
        'timestamp': datetime.now().isoformat()
    }
    joblib.dump(model_data, path)
    print(f"Model saved to {path}")


def load_model(path: str) -> Dict:
    """Load model with metadata"""
    model_data = joblib.load(path)
    print(f"Model loaded from {path}")
    print(f"  Features: {len(model_data['feature_cols'])}")
    print(f"  Metrics: {model_data['metrics']}")
    return model_data


# ============================================================
# 14. Visualization
# ============================================================

def plot_feature_importance(model: lgb.LGBMRanker, feature_cols: List[str], 
                            top_n: int = 20, save_path: str = 'feature_importance.png'):
    """Plot feature importance"""
    importance = model.booster_.feature_importance(importance_type='gain')
    
    imp_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False).head(top_n)
    
    plt.figure(figsize=(10, 8))
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    
    sns.barplot(x='importance', y='feature', data=imp_df, palette='viridis')
    plt.title(f'LightGBM Feature Importance (Top {top_n} Gain)', fontsize=14, fontweight='bold')
    plt.xlabel('Importance Gain', fontsize=12)
    plt.ylabel('Features', fontsize=12)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"Feature importance saved to {save_path}")


def plot_cv_results(study: optuna.Study, save_path: str = 'optuna_history.png'):
    """Plot Optuna optimization history"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Optimization history
    optuna.visualization.matplotlib.plot_optimization_history(study)
    plt.sca(axes[0])
    axes[0].set_title('Optimization History')
    
    # Parameter importance
    optuna.visualization.matplotlib.plot_param_importances(study)
    plt.sca(axes[1])
    axes[1].set_title('Parameter Importances')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"Optuna plots saved to {save_path}")


def plot_prediction_distribution(predictions: List[RacePrediction], 
                                  save_path: str = 'prediction_distribution.png'):
    """Plot distribution of win probabilities"""
    all_probs = []
    for p in predictions:
        for hp in p.predictions:
            all_probs.append(hp['win_prob'])
    
    plt.figure(figsize=(10, 6))
    plt.hist(all_probs, bins=50, edgecolor='black', alpha=0.7)
    plt.xlabel('Win Probability')
    plt.ylabel('Frequency')
    plt.title('Distribution of Predicted Win Probabilities')
    plt.axvline(np.mean(all_probs), color='red', linestyle='--', label=f'Mean: {np.mean(all_probs):.3f}')
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"Prediction distribution saved to {save_path}")


# ============================================================
# 15. Main Training Pipeline
# ============================================================

def train_pipeline(config: ModelConfig, data_path: str = 'hkjc_features_selected.csv') -> Dict:
    """Complete training pipeline"""
    
    # Initialize tracker
    tracker = ExperimentTracker()
    tracker.log_config(config)
    
    # Load data
    df, feature_cols = load_and_prepare_data(data_path)
    
    # NOTE: Feature selection is now done INSIDE each CV fold to prevent data leakage
    # We no longer do feature selection on the full dataset before CV
    if config.feature_selection_threshold > 0:
        print(f"\n=== Feature Selection (threshold: {config.feature_selection_threshold:.1%}) ===")
        print("Feature selection will be performed inside each CV fold using only training data")
    
    # Optuna optimization with time-aware CV
    print(f"\n=== Optuna Optimization ({config.n_trials} trials) ===")
    print("Using TimeSeriesGroupKFold to prevent data leakage...")
    study = optuna.create_study(
        direction='maximize',
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=3)
    )
    study.optimize(create_objective(df, feature_cols, config), n_trials=config.n_trials)
    
    print(f"\nBest NDCG@3: {study.best_value:.4f}")
    print("Best params:")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")
    
    # Train final LightGBM model
    best_params = study.best_params.copy()
    best_params.update({
        'objective': 'lambdarank',
        'metric': 'ndcg',
        'random_state': config.random_state,
        'verbose': -1,
        'eval_at': [1, 3, 5]
    })
    
    df_sorted = df.sort_values('race_id').reset_index(drop=True)
    
    # ===== FINAL FEATURE SELECTION ON FULL DATASET =====
    # For final model, we can use all data since there's no holdout set
    print("\n=== Final Feature Selection (on full dataset) ===")
    quick_model = lgb.LGBMRanker(
        objective='lambdarank', metric='ndcg', random_state=42, verbose=-1,
        n_estimators=100, learning_rate=0.05, num_leaves=16, max_depth=5, min_child_samples=10
    )
    quick_model.fit(
        df_sorted[feature_cols], df_sorted['relevance'],
        group=df_sorted.groupby('race_id', sort=False).size().values
    )
    final_features = select_features_by_importance(quick_model, feature_cols, 
                                                    config.feature_selection_threshold)
    
    if len(final_features) == 0:
        final_features = feature_cols
    
    # ── Classifier-specific feature selection (full dataset) ──
    print("\n=== Classifier Feature Selection (on full dataset) ===")
    quick_clf = lgb.LGBMClassifier(
        objective='binary', metric='binary_logloss', random_state=42, verbose=-1,
        n_estimators=100, learning_rate=0.05, num_leaves=16, max_depth=5,
        min_child_samples=10, class_weight='balanced'
    )
    quick_clf.fit(df_sorted[feature_cols], df_sorted['target_won'])
    clf_final_features = _select_clf_features(
        quick_clf, feature_cols, config.feature_selection_threshold
    )
    if len(clf_final_features) == 0:
        clf_final_features = feature_cols
    
    # Combined feature set: union of Ranker and Classifier selections
    # Both models need their respective features accessible at prediction time.
    union_features = list(dict.fromkeys(final_features + clf_final_features))
    print(f"  Ranker features: {len(final_features)} | Clf features: {len(clf_final_features)} | Union: {len(union_features)}")
    
    X_all = df_sorted[final_features]
    y_all = df_sorted['relevance']
    groups_all = df_sorted.groupby('race_id', sort=False).size().values
    
    lgb_model = lgb.LGBMRanker(**best_params)
    lgb_model.fit(X_all, y_all, group=groups_all)
    
    # Evaluate on full data
    all_preds = lgb_model.predict(X_all)
    top1_acc, top3_hit, eval_df = evaluate_predictions(df_sorted, all_preds)
    ndcg3 = calculate_ndcg_at_k(df_sorted, all_preds, k=3)
    mrr = calculate_mrr(df_sorted, all_preds)
    
    lgb_metrics = {
        'top1_acc': top1_acc,
        'top3_hit_rate': top3_hit,
        'ndcg@3': ndcg3,
        'mrr': mrr
    }
    
    print(f"\nLightGBM Final Metrics:")
    for k, v in lgb_metrics.items():
        print(f"  {k}: {v:.4f}")
    
    # Train XGBoost model (ensemble)
    models = {'lightgbm': lgb_model}
    weights = {'lightgbm': 1.0}
    
    if config.use_ensemble:
        print("\n=== Training XGBoost Ranker ===")
        xgb_model = train_xgb_model(df, final_features, best_params)
        models['xgboost'] = xgb_model
        weights['xgboost'] = 1.0
        
        # Ensemble evaluation
        ensemble_preds = ensemble_predict(models, X_all, weights)
        top1_acc_e, top3_hit_e, _ = evaluate_predictions(df_sorted, ensemble_preds)
        ndcg3_e = calculate_ndcg_at_k(df_sorted, ensemble_preds, k=3)
        mrr_e = calculate_mrr(df_sorted, ensemble_preds)
        
        xgb_metrics = {
            'top1_acc': top1_acc_e,
            'top3_hit_rate': top3_hit_e,
            'ndcg@3': ndcg3_e,
            'mrr': mrr_e
        }
        
        print(f"\nEnsemble Metrics:")
        for k, v in xgb_metrics.items():
            print(f"  {k}: {v:.4f}")
    
    # ===== DUAL-MODEL ENSEMBLE: BINARY CLASSIFIER (Model B) =====
    dual_config = DualEnsembleConfig(
        classifier_type='lgbm',
        fusion_method='rank_then_prob',
        bet_threshold_rank=1,
        bet_threshold_prob=0.20,
        calibrate_classifier=True,
        classifier_n_trials=min(50, config.n_trials // 2),
        classifier_early_stopping=config.early_stopping_rounds,
    )
    
    print("\n" + "="*60)
    print("DUAL-MODEL ENSEMBLE: Training Binary Classifier (Model B)")
    print("="*60)
    print(f"  Classifier type: {dual_config.classifier_type}")
    print(f"  Fusion method: {dual_config.fusion_method}")
    print(f"  Bet rule: Top-{dual_config.bet_threshold_rank} AND win_prob > {dual_config.bet_threshold_prob:.0%}")
    
    # Optuna optimisation for classifier
    # NOTE: We pass raw feature_cols (NOT final_features) to prevent data leakage.
    # Feature selection happens INSIDE each CV fold using only training data.
    print(f"\n--- Classifier Optuna ({dual_config.classifier_n_trials} trials) ---")
    print("  Feature selection performed inside each CV fold to prevent leakage.")
    clf_best_params = optimize_classifier_optuna(df, feature_cols, dual_config, config)
    
    # Train final classifier on full dataset
    print("\n--- Training Final Classifier ---")
    print(f"  Using classifier-specific features ({len(clf_final_features)} features)")
    clf_model, clf_calibrator = train_binary_classifier(
        df, clf_final_features, clf_best_params, dual_config, config
    )
    
    # Evaluate classifier
    clf_metrics = evaluate_classifier(clf_model, clf_calibrator, df, clf_final_features)
    
    # Create dual ensemble predictor (uses union of Ranker + Classifier features)
    dual_predictor = DualEnsemblePredictor(
        ranker_models=models,
        classifier_model=clf_model,
        classifier_calibrator=clf_calibrator,
        feature_cols=union_features,
        ranker_weights=weights,
        dual_config=dual_config,
    )
    
    # Evaluate dual fusion on full data
    df_dual = dual_predictor.predict_per_race(df_sorted)
    
    # Compare Ranker-only vs Dual-fusion Top-1 accuracy
    ranker_top1 = df_dual[df_dual['pred_rank'] == 1]
    dual_top1 = df_dual[
        (df_dual['pred_rank'] <= dual_config.bet_threshold_rank) &
        (df_dual['win_prob'] >= dual_config.bet_threshold_prob)
    ]
    
    # Dual fusion betting simulation
    print("\n=== Dual-Model Fusion Betting Simulation ===")
    odds_cols = [c for c in df_dual.columns if 'odds' in c.lower() or 'win_odds' in c.lower()]
    if odds_cols:
        print(f"Using real market odds from columns: {odds_cols}")
        fusion_results = make_fusion_betting_decisions(
            df_dual, dual_config, config.kelly_fraction,
            config.min_odds, config.max_odds, odds_cols[0]
        )
        print_fusion_results(fusion_results)
    else:
        print("WARNING: No market odds columns found - fusion betting simulation skipped.")
        fusion_results = {
            'total_races': 0, 'total_bets': 0,
            'total_stake': 0.0, 'total_return': 0.0,
            'roi': 0.0, 'win_rate': 0.0, 'fusion_bets': [],
            'note': 'No real odds available - simulation skipped'
        }
    
    # Save classifier model
    clf_save_data = {
        'model': clf_model,
        'calibrator': clf_calibrator,
        'feature_cols': clf_final_features,
        'params': clf_best_params,
        'metrics': clf_metrics,
        'dual_config': asdict(dual_config),
        'timestamp': datetime.now().isoformat()
    }
    joblib.dump(clf_save_data, 'model_classifier.pkl')
    print("Classifier saved to model_classifier.pkl")
    
    # SHAP analysis
    if config.use_shap and SHAP_AVAILABLE:
        print("\n=== Computing SHAP Values ===")
        shap_values = compute_shap_values(lgb_model, X_all, final_features)
        if shap_values is not None:
            plot_shap_summary(shap_values, X_all, final_features)
            plot_shap_dependence(shap_values, X_all, final_features)
    
    # Feature importance plot
    plot_feature_importance(lgb_model, final_features)
    
    # Optuna plots
    plot_cv_results(study)
    
    # ===== PROBABILITY CALIBRATION =====
    print("\n=== Probability Calibration ===")
    calibrator = ProbabilityCalibrator(method='isotonic', cv_folds=3)
    calibrator.fit(df_sorted, all_preds)
    
    # Get calibrated probabilities
    calibrated_probs = calibrator.predict_proba_per_race(df_sorted, all_preds)
    df_sorted['win_prob_calibrated'] = calibrated_probs
    
    # Evaluate calibration
    cal_metrics = evaluate_calibration(df_sorted, all_preds)
    print(f"  Calibration ECE: {cal_metrics['ece']:.4f}, MCE: {cal_metrics['mce']:.4f}")
    
    # Use calibrated probabilities for evaluation
    eval_df_calibrated = df_sorted.copy()
    eval_df_calibrated['win_prob'] = calibrated_probs
    eval_df_calibrated['pred_rank'] = eval_df_calibrated.groupby('race_id')['win_prob'].rank(
        ascending=False, method='first')
    
    # Betting simulation with calibrated probabilities
    print("\n=== Betting Simulation (Calibrated) ===")
    # Check if odds columns exist
    odds_cols = [c for c in eval_df_calibrated.columns if 'odds' in c.lower() or 'win_odds' in c.lower()]
    if odds_cols:
        print(f"Using real market odds from columns: {odds_cols}")
        betting_results = simulate_betting(eval_df_calibrated, config.kelly_fraction, 
                                           config.min_odds, config.max_odds)
        print_betting_results(betting_results)
    else:
        print("WARNING: No market odds columns found in data!")
        print("Betting simulation requires real market odds (win_odds, live_odds, etc.)")
        print("Skipping simulation - cannot validate against real market with 17.5% takeout.")
        betting_results = {
            'total_races': 0,
            'total_bets': 0,
            'total_stake': 0.0,
            'total_return': 0.0,
            'roi': 0.0,
            'win_rate': 0.0,
            'bets': [],
            'note': 'No real odds available - simulation skipped'
        }
    
    # Save models
    save_model(lgb_model, final_features, best_params, lgb_metrics, 'model_lgb.pkl')
    if config.use_ensemble:
        save_model(xgb_model, final_features, best_params, xgb_metrics, 'model_xgb.pkl')
    
    # Save calibrator
    joblib.dump(calibrator, 'calibrator.pkl')
    print("Calibrator saved to calibrator.pkl")
    
    # Save ensemble config (now includes dual-model info)
    ensemble_config = {
        'models': list(models.keys()),
        'weights': weights,
        'feature_cols': final_features,
        'best_params': best_params,
        'dual_ensemble': {
            'use_classifier': dual_config.use_classifier,
            'classifier_type': dual_config.classifier_type,
            'fusion_method': dual_config.fusion_method,
            'bet_threshold_rank': dual_config.bet_threshold_rank,
            'bet_threshold_prob': dual_config.bet_threshold_prob,
        }
    }
    with open('ensemble_config.json', 'w') as f:
        json.dump(ensemble_config, f, indent=2)
    print("Ensemble config saved (with dual-model settings)")
    
    # Log to tracker
    tracker.log_model('lightgbm', best_params, lgb_metrics)
    if config.use_ensemble:
        tracker.log_model('xgboost', best_params, xgb_metrics)
    tracker.log_model('classifier', clf_best_params, clf_metrics)
    tracker.log_results({
        'best_ndcg': study.best_value,
        'lgb_metrics': lgb_metrics,
        'clf_metrics': clf_metrics,
        'fusion_roi': fusion_results.get('roi', 0),
        'fusion_win_rate': fusion_results.get('win_rate', 0),
        'betting': betting_results,
        'calibration': cal_metrics
    })
    
    return {
        'models': models,
        'weights': weights,
        'feature_cols': feature_cols,
        'best_params': best_params,
        'metrics': lgb_metrics,
        'study': study,
        'eval_df': eval_df,
        'dual_predictor': dual_predictor,
        'clf_model': clf_model,
        'clf_calibrator': clf_calibrator,
        'clf_metrics': clf_metrics,
        'fusion_results': fusion_results,
        'dual_config': dual_config,
    }


# ============================================================
# 16. Prediction Pipeline for Future Races
# ============================================================

def predict_pipeline(future_data_path: str, model_dir: str = '.', 
                     output_path: str = 'future_predictions.csv') -> List[RacePrediction]:
    """Load models and predict on future race data (supports dual-model ensemble)"""
    
    # Load ensemble config
    with open(f'{model_dir}/ensemble_config.json', 'r') as f:
        ensemble_config = json.load(f)
    
    feature_cols = ensemble_config['feature_cols']
    weights = ensemble_config['weights']
    
    # Load ranker models
    models = {}
    for model_name in ensemble_config['models']:
        model_data = load_model(f'{model_dir}/model_{model_name}.pkl')
        models[model_name] = model_data['model']
    
    # Try to load classifier model (optional – dual-model enhancement)
    dual_predictor = None
    dual_config = None
    classifier_path = Path(model_dir) / 'model_classifier.pkl'
    if classifier_path.exists():
        print("\n=== Loading Dual-Model Classifier ===")
        clf_data = joblib.load(classifier_path)
        clf_model = clf_data['model']
        clf_calibrator = clf_data.get('calibrator', None)
        
        # Restore DualEnsembleConfig from saved data
        saved_dual = clf_data.get('dual_config', {})
        dual_config = DualEnsembleConfig(
            classifier_type=saved_dual.get('classifier_type', 'lgbm'),
            fusion_method=saved_dual.get('fusion_method', 'rank_then_prob'),
            bet_threshold_rank=saved_dual.get('bet_threshold_rank', 1),
            bet_threshold_prob=saved_dual.get('bet_threshold_prob', 0.20),
            calibrate_classifier=saved_dual.get('calibrate_classifier', True),
        )
        
        dual_predictor = DualEnsemblePredictor(
            ranker_models=models,
            classifier_model=clf_model,
            classifier_calibrator=clf_calibrator,
            feature_cols=feature_cols,
            ranker_weights=weights,
            dual_config=dual_config,
        )
        print(f"  Dual-model active: fusion={dual_config.fusion_method}, "
              f"bet=Top-{dual_config.bet_threshold_rank} AND prob>{dual_config.bet_threshold_prob:.0%}")
    else:
        print("  Note: No classifier model found. Running ranker-only mode.")
        print("  Run training with `use_classifier=True` to enable dual-model.")
    
    # Load future data
    future_df, available_features = prepare_future_race_data(future_data_path, feature_cols)
    
    # Predict (dual-model if available, else ranker-only)
    predictions = predict_future_races(
        models, future_df, available_features, weights,
        dual_predictor=dual_predictor,
        dual_config=dual_config,
    )
    
    # Save predictions
    save_predictions(predictions, output_path)
    
    # Print summary
    print(f"\n=== PREDICTIONS FOR {len(predictions)} FUTURE RACES ===")
    for p in predictions:
        print(f"\nRace {p.race_id} ({p.race_date} Race {p.race_no} @ {p.course})")
        print("  Top 3 Predictions:")
        for hp in p.predictions[:3]:
            extra = ""
            if hp.get('clf_win_prob') is not None:
                extra = f", ClfWin%: {hp['clf_win_prob']:.1%}"
            print(f"    {hp['pred_rank']}. {hp['horse_name']} (jockey: {hp['jockey']}) "
                  f"- Win%: {hp['win_prob']:.1%}{extra}, Score: {hp['pred_score']:.4f}")
        print("  Betting Recommendations:")
        for br in p.betting_recommendations:
            fusion_tag = " [FUSION]" if br.get('fusion_trigger') else ""
            print(f"    {br['recommendation']}{fusion_tag}: {br['horse_name']} "
                  f"(Win%: {br['win_prob']:.1%}, Implied Odds: {br['implied_odds']:.1f})")
    
    # Plot distribution
    plot_prediction_distribution(predictions)
    
    return predictions


# ============================================================
# 17. Main Entry Points
# ============================================================

def main_train():
    """Main training entry point (trains Ranker + Classifier dual-model)"""
    config = ModelConfig(
        n_trials=100,
        cv_folds=5,
        n_estimators_max=500,
        use_shap=True,
        use_ensemble=True,
        feature_selection_threshold=0.005,
        kelly_fraction=0.25
    )
    
    results = train_pipeline(config)
    print("\n=== TRAINING COMPLETE ===")
    print(f"Models saved: model_lgb.pkl, model_xgb.pkl, model_classifier.pkl")
    print(f"  Ranker (Model A): LGBMRanker / XGBRanker -> pred_rank")
    print(f"  Classifier (Model B): LGBMClassifier -> win_prob")
    print(f"  Fusion rule: Top-{results.get('dual_config', DualEnsembleConfig()).bet_threshold_rank} "
          f"AND win_prob > {results.get('dual_config', DualEnsembleConfig()).bet_threshold_prob:.0%}")
    print(f"Config saved: ensemble_config.json")
    print(f"Experiment logged: experiments/")
    
    return results


def main_predict(future_data_path: str, output_path: str = 'future_predictions.csv'):
    """Main prediction entry point"""
    predictions = predict_pipeline(future_data_path, '.', output_path)
    return predictions


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'predict':
        # Prediction mode: python hkjc_ml_enhanced.py predict future_races.csv
        future_path = sys.argv[2] if len(sys.argv) > 2 else 'future_races.csv'
        main_predict(future_path)
    else:
        # Training mode
        main_train()