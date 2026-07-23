#!/usr/bin/env python
"""
Standalone Prediction Script for Future HKJC Races
===================================================
Usage: python predict_future_races.py future_races.csv [output.csv]

This script loads trained models and predicts on new race data
WITHOUT requiring target_finish_position or target_won columns.

Dual-Model Ensemble:
  Model A (LGBMRanker)  -> pred_rank  (race ranking)
  Model B (LGBMClassifier) -> win_prob (calibrated win probability)
  Fusion: Top-1 AND win_prob > 20% -> STRONG_BET
"""

import sys
import pandas as pd
import numpy as np
import joblib
import json
import lightgbm as lgb
import xgboost as xgb
from pathlib import Path

# Import from enhanced module
from hkjc_ml_enhanced import (
    prepare_future_race_data,
    predict_future_races,
    save_predictions,
    plot_prediction_distribution,
    DualEnsemblePredictor,
    DualEnsembleConfig,
)


def load_models_and_config(model_dir: str = '.'):
    """Load ensemble config, ranker models, and optional classifier (dual-model)"""
    config_path = Path(model_dir) / 'ensemble_config.json'
    if not config_path.exists():
        raise FileNotFoundError(f"Ensemble config not found at {config_path}. Run training first.")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    models = {}
    model_file_map = {
        'lightgbm': 'model_lgb.pkl',
        'xgboost': 'model_xgb.pkl'
    }
    for model_name in config['models']:
        file_name = model_file_map.get(model_name, f'model_{model_name}.pkl')
        model_path = Path(model_dir) / file_name
        if model_path.exists():
            model_data = joblib.load(model_path)
            models[model_name] = model_data['model']
            print(f"Loaded {model_name} from {model_path}")
        else:
            print(f"Warning: {model_path} not found")
    
    feature_cols = config['feature_cols']
    weights = config['weights']
    
    # Try to load dual-model classifier
    dual_predictor = None
    dual_config = None
    classifier_path = Path(model_dir) / 'model_classifier.pkl'
    if classifier_path.exists():
        print(f"\nLoaded dual-model classifier from {classifier_path}")
        clf_data = joblib.load(classifier_path)
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
            classifier_model=clf_data['model'],
            classifier_calibrator=clf_data.get('calibrator'),
            feature_cols=feature_cols,
            ranker_weights=weights,
            dual_config=dual_config,
        )
        print(f"  Dual-model active: Top-{dual_config.bet_threshold_rank} "
              f"AND win_prob > {dual_config.bet_threshold_prob:.0%}")
    else:
        print("  Note: No classifier model found. Running ranker-only mode.")
    
    return models, feature_cols, weights, dual_predictor, dual_config


def main():
    if len(sys.argv) < 2:
        print("Usage: python predict_future_races.py <future_races.csv> [output.csv]")
        print("\nExample:")
        print("  python predict_future_races.py 20260715/hkjc_all_races_draw.csv predictions.csv")
        print("\nDual-Model: Ranker (pred_rank) + Classifier (win_prob)")
        sys.exit(1)
    
    future_data_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'future_predictions.csv'
    
    print(f"Loading models...")
    models, feature_cols, weights, dual_predictor, dual_config = load_models_and_config()
    
    print(f"Loading future race data from {future_data_path}...")
    future_df, available_features = prepare_future_race_data(future_data_path, feature_cols)
    
    n_horses = len(future_df)
    n_races = future_df['race_id'].nunique()
    print(f"Predicting on {n_horses} horses across {n_races} races...")
    
    predictions = predict_future_races(
        models, future_df, available_features, weights,
        dual_predictor=dual_predictor,
        dual_config=dual_config,
    )
    
    print(f"\nSaving predictions to {output_path}...")
    save_predictions(predictions, output_path)
    
    # Plot distribution
    plot_prediction_distribution(predictions, 'future_prediction_distribution.png')
    
    print("\n✅ Prediction complete!")
    print(f"   JSON: {output_path.replace('.csv', '.json')}")
    print(f"   CSV:  {output_path}")
    print(f"   Distribution plot: future_prediction_distribution.png")


if __name__ == '__main__':
    main()