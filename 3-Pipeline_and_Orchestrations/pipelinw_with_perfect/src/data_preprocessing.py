"""
Data Preprocessing Module
Handles data cleaning, validation, and splitting (NO DATA LEAKAGE)
"""

import pandas as pd
import numpy as np
from typing import Tuple
from sklearn.model_selection import train_test_split
from prefect import task, get_run_logger

from config.config import config, PREDICTION_TIME_FEATURES, LEAKAGE_FEATURES


@task(name="clean_data")
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean NYC taxi data with NO DATA LEAKAGE.
    Only uses features available at pickup time.
    
    Args:
        df: Raw dataframe
        
    Returns:
        pd.DataFrame: Cleaned dataframe
    """
    logger = get_run_logger()
    logger.info("🧹 Starting data cleaning...")
    
    df_clean = df.copy()
    initial_rows = len(df_clean)
    
    # Calculate target variable (trip duration)
    df_clean['tpep_pickup_datetime'] = pd.to_datetime(df_clean['tpep_pickup_datetime'])
    df_clean['tpep_dropoff_datetime'] = pd.to_datetime(df_clean['tpep_dropoff_datetime'])
    df_clean['trip_duration_minutes'] = (
        df_clean['tpep_dropoff_datetime'] - df_clean['tpep_pickup_datetime']
    ).dt.total_seconds() / 60
    
    logger.info(f"   Initial rows: {initial_rows:,}")
    
    # Filter unrealistic trip durations
    df_clean = df_clean[
        (df_clean['trip_duration_minutes'] >= config.MIN_TRIP_DURATION / 60) &
        (df_clean['trip_duration_minutes'] <= config.MAX_TRIP_DURATION / 60)
    ]
    logger.info(f"   After duration filter: {len(df_clean):,} rows")
    
    # Filter unrealistic trip distances
    df_clean = df_clean[
        (df_clean['trip_distance'] >= config.MIN_TRIP_DISTANCE) &
        (df_clean['trip_distance'] <= config.MAX_TRIP_DISTANCE)
    ]
    logger.info(f"   After distance filter: {len(df_clean):,} rows")
    
    # Filter NYC coordinates
    df_clean = df_clean[
        df_clean['pickup_latitude'].between(config.NYC_LAT_MIN, config.NYC_LAT_MAX) &
        df_clean['pickup_longitude'].between(config.NYC_LON_MIN, config.NYC_LON_MAX) &
        df_clean['dropoff_latitude'].between(config.NYC_LAT_MIN, config.NYC_LAT_MAX) &
        df_clean['dropoff_longitude'].between(config.NYC_LON_MIN, config.NYC_LON_MAX)
    ]
    logger.info(f"   After coordinate filter: {len(df_clean):,} rows")
    
    # Filter passenger count
    df_clean = df_clean[df_clean['passenger_count'].between(1, 6)]
    logger.info(f"   After passenger filter: {len(df_clean):,} rows")
    
    # Drop missing values
    df_clean = df_clean.dropna()
    logger.info(f"   After dropna: {len(df_clean):,} rows")
    
    # Sample if needed
    if config.SAMPLE_SIZE and len(df_clean) > config.SAMPLE_SIZE:
        df_clean = df_clean.sample(n=config.SAMPLE_SIZE, random_state=config.RANDOM_STATE)
        logger.info(f"   After sampling: {len(df_clean):,} rows")
    
    df_clean = df_clean.reset_index(drop=True)
    
    # Keep only prediction-time features + target
    features_to_keep = PREDICTION_TIME_FEATURES + ['trip_duration_minutes']
    df_clean = df_clean[features_to_keep]
    
    retention_rate = len(df_clean) / initial_rows * 100
    logger.info(f"✅ Cleaning complete: {len(df_clean):,} rows ({retention_rate:.1f}% retained)")
    logger.info(f"   Columns kept: {len(features_to_keep)} (prediction features + target)")
    
    return df_clean


@task(name="validate_no_leakage")
def validate_no_leakage(df: pd.DataFrame) -> None:
    """
    Validate that we're only using features available at pickup time.
    
    Args:
        df: Cleaned dataframe
        
    Raises:
        ValueError: If leakage features are being used
    """
    logger = get_run_logger()
    logger.info("🔒 Validating data leakage prevention...")
    
    # Check for leakage features (excluding target which is expected)
    available_cols = set(df.columns)
    leakage_cols = set(LEAKAGE_FEATURES)
    
    # Target variable is allowed
    expected_cols = set(PREDICTION_TIME_FEATURES + ['trip_duration_minutes'])
    
    found_leakage = available_cols.intersection(leakage_cols)
    
    if found_leakage:
        logger.error(f"❌ LEAKAGE DETECTED: {found_leakage}")
        raise ValueError(f"Data leakage detected: {found_leakage}")
    
    # Verify we have expected columns
    missing_features = expected_cols - available_cols
    if missing_features:
        logger.warning(f"⚠️  Missing expected features: {missing_features}")
    
    unexpected_features = available_cols - expected_cols
    if unexpected_features:
        logger.warning(f"⚠️  Unexpected features found: {unexpected_features}")
    
    logger.info(f"✅ No data leakage - using {len(PREDICTION_TIME_FEATURES)} pickup-time features")
    logger.info(f"   Available columns: {sorted(available_cols)}")


@task(name="split_data")
def split_data(
    df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split data into train, validation, and test sets BEFORE feature engineering.
    
    Args:
        df: Cleaned dataframe
        
    Returns:
        Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
    """
    logger = get_run_logger()
    logger.info("🔪 Splitting data (BEFORE feature engineering)...")
    
    # Separate features and target
    X = df[PREDICTION_TIME_FEATURES]
    y = df['trip_duration_minutes'].values
    
    # First split: separate test set
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, 
        test_size=config.TEST_SIZE, 
        random_state=config.RANDOM_STATE
    )
    
    # Second split: separate train and validation
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp,
        test_size=config.VAL_SIZE,
        random_state=config.RANDOM_STATE
    )
    
    # Log split statistics
    total_samples = len(X)
    logger.info(f"   Total samples: {total_samples:,}")
    logger.info(f"   Train: {len(X_train):,} ({len(X_train)/total_samples*100:.1f}%)")
    logger.info(f"   Val:   {len(X_val):,} ({len(X_val)/total_samples*100:.1f}%)")
    logger.info(f"   Test:  {len(X_test):,} ({len(X_test)/total_samples*100:.1f}%)")
    logger.info(f"   Target mean: {y_train.mean():.2f} minutes")
    logger.info(f"   Target std:  {y_train.std():.2f} minutes")
    
    logger.info("✅ Data split complete (leakage-free)")
    
    return X_train, X_val, X_test, y_train, y_val, y_test