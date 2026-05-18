"""
Data preprocessing module for NYC Taxi ML Pipeline
Handles data cleaning, filtering, and validation
"""
import pandas as pd
import numpy as np
import logging
from typing import Tuple

from config.config import DataConfig


logger = logging.getLogger(__name__)


class DataPreprocessor:
    """Handle data cleaning and preprocessing."""
    
    def __init__(self, config: DataConfig):
        """
        Initialize data preprocessor.
        
        Args:
            config: Data configuration
        """
        self.config = config
        self.initial_rows = 0
        self.final_rows = 0
    
    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean NYC taxi data with NO DATA LEAKAGE.
        
        Args:
            df: Raw dataframe
            
        Returns:
            Cleaned dataframe
        """
        logger.info("🧹 Cleaning data...")
        self.initial_rows = len(df)
        df_clean = df.copy()
        
        # Calculate target variable
        logger.info("   ✓ Calculating trip duration...")
        df_clean['tpep_pickup_datetime'] = pd.to_datetime(df_clean['tpep_pickup_datetime'])
        df_clean['tpep_dropoff_datetime'] = pd.to_datetime(df_clean['tpep_dropoff_datetime'])
        df_clean['trip_duration_minutes'] = (
            df_clean['tpep_dropoff_datetime'] - df_clean['tpep_pickup_datetime']
        ).dt.total_seconds() / 60
        
        # Filter unrealistic trip durations
        logger.info("   ✓ Filtering trip duration...")
        before = len(df_clean)
        df_clean = df_clean[
            (df_clean['trip_duration_minutes'] >= self.config.min_trip_duration / 60) &
            (df_clean['trip_duration_minutes'] <= self.config.max_trip_duration / 60)
        ]
        logger.info(f"     Removed {before - len(df_clean):,} rows with invalid duration")
        
        # Filter unrealistic distances
        logger.info("   ✓ Filtering trip distance...")
        before = len(df_clean)
        df_clean = df_clean[
            (df_clean['trip_distance'] >= self.config.min_trip_distance) &
            (df_clean['trip_distance'] <= self.config.max_trip_distance)
        ]
        logger.info(f"     Removed {before - len(df_clean):,} rows with invalid distance")
        
        # Filter NYC coordinates
        logger.info("   ✓ Filtering geographic coordinates...")
        before = len(df_clean)
        df_clean = df_clean[
            df_clean['pickup_latitude'].between(*self.config.nyc_lat_range) &
            df_clean['pickup_longitude'].between(*self.config.nyc_lon_range) &
            df_clean['dropoff_latitude'].between(*self.config.nyc_lat_range) &
            df_clean['dropoff_longitude'].between(*self.config.nyc_lon_range)
        ]
        logger.info(f"     Removed {before - len(df_clean):,} rows outside NYC bounds")
        
        # Filter passenger count
        logger.info("   ✓ Filtering passenger count...")
        before = len(df_clean)
        df_clean = df_clean[
            df_clean['passenger_count'].between(
                self.config.min_passenger_count,
                self.config.max_passenger_count
            )
        ]
        logger.info(f"     Removed {before - len(df_clean):,} rows with invalid passenger count")
        
        # Drop missing values
        logger.info("   ✓ Removing missing values...")
        before = len(df_clean)
        df_clean = df_clean.dropna()
        logger.info(f"     Removed {before - len(df_clean):,} rows with missing values")
        
        # Sample if needed
        if self.config.sample_size and len(df_clean) > self.config.sample_size:
            logger.info(f"   ✓ Sampling {self.config.sample_size:,} rows...")
            df_clean = df_clean.sample(
                n=self.config.sample_size,
                random_state=42
            )
        
        df_clean = df_clean.reset_index(drop=True)
        
        self.final_rows = len(df_clean)
        retention_pct = (self.final_rows / self.initial_rows) * 100
        
        logger.info(f"✅ Cleaning complete:")
        logger.info(f"   Initial rows: {self.initial_rows:,}")
        logger.info(f"   Final rows: {self.final_rows:,}")
        logger.info(f"   Retention: {retention_pct:.1f}%")
        
        return df_clean
    
    def prepare_features_target(
        self, 
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        Separate features and target variable.
        
        Args:
            df: Cleaned dataframe
            
        Returns:
            Tuple of (features, target)
        """
        logger.info("🎯 Preparing features and target...")
        
        # Extract features (only prediction-time features)
        X = df[self.config.prediction_time_features].copy()
        
        # Extract target
        y = df['trip_duration_minutes'].values
        
        logger.info(f"✅ Features prepared:")
        logger.info(f"   Features: {len(self.config.prediction_time_features)}")
        logger.info(f"   Samples: {len(X):,}")
        logger.info(f"   Target range: [{y.min():.2f}, {y.max():.2f}] minutes")
        logger.info(f"   Target mean: {y.mean():.2f} minutes")
        logger.info(f"   Target std: {y.std():.2f} minutes")
        
        # Log excluded features
        logger.info(f"🚫 Excluded post-trip features: {len(self.config.leakage_features)}")
        
        return X, y
    
    def get_statistics(self) -> dict:
        """
        Get preprocessing statistics.
        
        Returns:
            Dictionary of statistics
        """
        return {
            'initial_rows': self.initial_rows,
            'final_rows': self.final_rows,
            'retention_pct': (self.final_rows / self.initial_rows * 100) if self.initial_rows > 0 else 0
        }
    
    def run(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        Execute full preprocessing pipeline.
        
        Args:
            df: Raw dataframe
            
        Returns:
            Tuple of (features, target)
        """
        logger.info("=" * 70)
        logger.info("STARTING DATA PREPROCESSING".center(70))
        logger.info("=" * 70)
        
        # Clean data
        df_clean = self.clean_data(df)
        
        # Prepare features and target
        X, y = self.prepare_features_target(df_clean)
        
        logger.info("✅ Data preprocessing completed successfully")
        
        return X, y