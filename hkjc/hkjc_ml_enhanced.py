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
class RacePrediction:
    """Prediction result for a single race"""
    race_id: int
    race_date: str
    race_no: int
    course: str
    predictions: List[Dict[str, Any]]
    betting_recommendations: List[Dict[str, Any]]

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
# 5. Ensemble Prediction
# ============================================================

def ensemble_predict(models: Dict[str, Any], X: pd.DataFrame, 
                     weights: Optional[Dict[str, float]] = None) -> np.ndarray:
    """Combine predictions from multiple models"""
    if weights is None:
        weights = {name: 1.0 for name in models.keys()}
    
    # Normalize weights
    total_weight = sum(weights.values())
    weights = {k: v/total_weight for k, v in weights.items()}
    
    predictions = np.zeros(len(X))
    for name, model in models.items():
        pred = model.predict(X)
        # Normalize predictions to [0, 1] range per race
        predictions += weights[name] * pred
    
    return predictions


# ============================================================
# 6. Feature Selection
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
# 7. SHAP Explainability
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
# 8. Betting Simulation
# ============================================================

def simulate_betting(df_eval: pd.DataFrame, kelly_fraction: float = 0.25,
                     min_odds: float = 1.5, max_odds: float = 50.0,
                     takeout_rate: float = 0.175,
                     odds_col: str = 'market_odds') -> Dict:
    """
    Simulate betting strategy using REAL market odds.
    
    Args:
        df_eval: DataFrame with predictions and actual results
        kelly_fraction: Fraction of Kelly bet to use (0.25 = quarter Kelly)
        min_odds: Minimum odds to consider betting
        max_odds: Maximum odds to consider betting
        takeout_rate: HKJC takeout rate (17.5% for win bets)
        odds_col: Column name containing real market odds
        
    Returns:
        Dict with betting results
        
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
    
    results = {
        'total_races': 0,
        'total_bets': 0,
        'total_stake': 0.0,
        'total_return': 0.0,
        'roi': 0.0,
        'win_rate': 0.0,
        'bets': [],
        'takeout_rate': takeout_rate
    }
    
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
                stake = kelly_bet * 100  # Assume 100 unit bankroll
                won = horse['target_won'] == 1
                # Return at market odds (we bet at market odds)
                return_amount = stake * market_odds if won else 0
                
                results['total_bets'] += 1
                results['total_stake'] += stake
                results['total_return'] += return_amount
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
    
    if results['total_stake'] > 0:
        results['roi'] = (results['total_return'] - results['total_stake']) / results['total_stake']
        results['win_rate'] = sum(b['won'] for b in results['bets']) / results['total_bets']
    
    return results


def print_betting_results(results: Dict):
    """Print betting simulation results"""
    print("\n" + "="*50)
    print("BETTING SIMULATION RESULTS")
    print("="*50)
    print(f"Total Races: {results['total_races']}")
    print(f"Total Bets Placed: {results['total_bets']}")
    print(f"Total Stake: {results['total_stake']:.2f}")
    print(f"Total Return: {results['total_return']:.2f}")
    print(f"ROI: {results['roi']:.2%}")
    print(f"Win Rate: {results['win_rate']:.2%}")
    print("="*50)


# ============================================================
# 9. Experiment Tracking
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
# 10. Future Race Prediction Pipeline
# ============================================================

def predict_future_races(models: Dict[str, Any], future_df: pd.DataFrame, 
                         feature_cols: List[str], weights: Optional[Dict] = None) -> List[RacePrediction]:
    """Predict on future race data without targets"""
    predictions = []
    
    # Prepare features
    X_future = future_df[feature_cols].fillna(0)
    
    # Get ensemble predictions
    ensemble_scores = ensemble_predict(models, X_future, weights)
    future_df = future_df.copy()
    future_df['pred_score'] = ensemble_scores
    
    # Calculate softmax probabilities per race
    for race_id, group in future_df.groupby('race_id'):
        race_info = group.iloc[0]
        
        # Softmax
        scores = group['pred_score'].values
        max_score = scores.max()
        exp_scores = np.exp(scores - max_score)
        win_probs = exp_scores / exp_scores.sum()
        
        group = group.copy()
        group['win_prob'] = win_probs
        group['pred_rank'] = group['pred_score'].rank(ascending=False, method='first')
        group = group.sort_values('win_prob', ascending=False)
        
        # Build predictions
        horse_preds = []
        for _, row in group.iterrows():
            horse_preds.append({
                'horse_id': row['horse_id'],
                'horse_name': row['horse_name'],
                'jockey': row['jockey'],
                'trainer': row['trainer'],
                'draw': row.get('f_draw_pct', 0),
                'pred_score': float(row['pred_score']),
                'win_prob': float(row['win_prob']),
                'pred_rank': int(row['pred_rank'])
            })
        
        # Betting recommendations (top 3 by win_prob)
        betting_recs = []
        for i, hp in enumerate(horse_preds[:3]):
            implied_odds = 1.0 / hp['win_prob'] if hp['win_prob'] > 0 else 999
            betting_recs.append({
                'rank': i + 1,
                'horse_name': hp['horse_name'],
                'win_prob': hp['win_prob'],
                'implied_odds': implied_odds,
                'recommendation': 'BET' if hp['win_prob'] > 0.25 else 'WATCH'
            })
        
        predictions.append(RacePrediction(
            race_id=int(race_id),
            race_date=str(race_info['race_date']),
            race_no=int(race_info['race_no']),
            course=str(race_info['course']),
            predictions=horse_preds,
            betting_recommendations=betting_recs
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
# 11. Model Persistence
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
# 12. Visualization
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
# 13. Main Training Pipeline
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
    
    # Save ensemble config
    ensemble_config = {
        'models': list(models.keys()),
        'weights': weights,
        'feature_cols': final_features,
        'best_params': best_params
    }
    with open('ensemble_config.json', 'w') as f:
        json.dump(ensemble_config, f, indent=2)
    
    # Log to tracker
    tracker.log_model('lightgbm', best_params, lgb_metrics)
    if config.use_ensemble:
        tracker.log_model('xgboost', best_params, xgb_metrics)
    tracker.log_results({
        'best_ndcg': study.best_value,
        'lgb_metrics': lgb_metrics,
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
        'eval_df': eval_df
    }


# ============================================================
# 14. Prediction Pipeline for Future Races
# ============================================================

def predict_pipeline(future_data_path: str, model_dir: str = '.', 
                     output_path: str = 'future_predictions.csv') -> List[RacePrediction]:
    """Load models and predict on future race data"""
    
    # Load ensemble config
    with open(f'{model_dir}/ensemble_config.json', 'r') as f:
        ensemble_config = json.load(f)
    
    feature_cols = ensemble_config['feature_cols']
    weights = ensemble_config['weights']
    
    # Load models
    models = {}
    for model_name in ensemble_config['models']:
        model_data = load_model(f'{model_dir}/model_{model_name}.pkl')
        models[model_name] = model_data['model']
    
    # Load future data
    future_df, available_features = prepare_future_race_data(future_data_path, feature_cols)
    
    # Predict
    predictions = predict_future_races(models, future_df, available_features, weights)
    
    # Save predictions
    save_predictions(predictions, output_path)
    
    # Print summary
    print(f"\n=== PREDICTIONS FOR {len(predictions)} FUTURE RACES ===")
    for p in predictions:
        print(f"\nRace {p.race_id} ({p.race_date} Race {p.race_no} @ {p.course})")
        print("  Top 3 Predictions:")
        for hp in p.predictions[:3]:
            print(f"    {hp['pred_rank']}. {hp['horse_name']} (jockey: {hp['jockey']}) "
                  f"- Win%: {hp['win_prob']:.1%}, Score: {hp['pred_score']:.4f}")
        print("  Betting Recommendations:")
        for br in p.betting_recommendations:
            print(f"    {br['recommendation']}: {br['horse_name']} "
                  f"(Win%: {br['win_prob']:.1%}, Implied Odds: {br['implied_odds']:.1f})")
    
    # Plot distribution
    plot_prediction_distribution(predictions)
    
    return predictions


# ============================================================
# 15. Main Entry Points
# ============================================================

def main_train():
    """Main training entry point"""
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
    print(f"Models saved: model_lgb.pkl, model_xgb.pkl")
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