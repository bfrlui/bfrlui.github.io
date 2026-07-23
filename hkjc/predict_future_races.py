#!/usr/bin/env python
"""
Standalone Prediction Script for Future HKJC Races
===================================================
Usage: python predict_future_races.py future_races.csv [output.csv]

This script loads trained models and predicts on new race data
WITHOUT requiring target_finish_position or target_won columns.
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
    ensemble_predict,
    predict_future_races,
    save_predictions,
    plot_prediction_distribution
)


def load_models_and_config(model_dir: str = '.'):
    """Load ensemble config and all models"""
    config_path = Path(model_dir) / 'ensemble_config.json'
    if not config_path.exists():
        raise FileNotFoundError(f"Ensemble config not found at {config_path}. Run training first.")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    models = {}
    # Map model names to actual file names
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
    
    return models, config['feature_cols'], config['weights']


def main():
    if len(sys.argv) < 2:
        print("Usage: python predict_future_races.py <future_races.csv> [output.csv]")
        print("\nExample:")
        print("  python predict_future_races.py 20260715/hkjc_all_races_draw.csv predictions.csv")
        sys.exit(1)
    
    future_data_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'future_predictions.csv'
    
    print(f"Loading models...")
    models, feature_cols, weights = load_models_and_config()
    
    print(f"Loading future race data from {future_data_path}...")
    future_df, available_features = prepare_future_race_data(future_data_path, feature_cols)
    
    print(f"Predicting on {len(future_df)} horses across {future_df['race_id'].nunique()} races...")
    predictions = predict_future_races(models, future_df, available_features, weights)
    
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