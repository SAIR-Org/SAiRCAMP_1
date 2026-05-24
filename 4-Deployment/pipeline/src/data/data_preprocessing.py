"""
Data preprocessing for 4-Deployment/pipeline
==============================================
CHANGES FROM pipeline_with_prefect/src/data/data_preprocessing.py:

  REMOVED: Geographic coordinate filter (lat/lon bounds check)
           WHY: Zone IDs (PULocationID/DOLocationID) are by definition
                within NYC — no bounds filtering needed. The 2019 TLC
                data contains no invalid geographic entries.

           The removed block was:
             df_clean = df_clean[
                 df_clean['pickup_latitude'].between(*config.nyc_lat_range) &
                 df_clean['pickup_longitude'].between(*config.nyc_lon_range) &
                 df_clean['dropoff_latitude'].between(*config.nyc_lat_range) &
                 df_clean['dropoff_longitude'].between(*config.nyc_lon_range)
             ]

  UNCHANGED: Everything else — duration filter, distance filter,
             passenger count filter, sample, prepare_features_target, run()
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
        self.config = config
        self.initial_rows = 0
        self.final_rows = 0

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean NYC taxi data with NO DATA LEAKAGE."""
        logger.info("🧹 Cleaning data...")
        self.initial_rows = len(df)
        df_clean = df.copy()

        # Compute target variable
        logger.info("   ✓ Calculating trip duration...")
        df_clean['tpep_pickup_datetime'] = pd.to_datetime(df_clean['tpep_pickup_datetime'])
        df_clean['tpep_dropoff_datetime'] = pd.to_datetime(df_clean['tpep_dropoff_datetime'])
        df_clean['trip_duration_minutes'] = (
            df_clean['tpep_dropoff_datetime'] - df_clean['tpep_pickup_datetime']
        ).dt.total_seconds() / 60

        # Filter unrealistic durations
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

        # NOTE: No geographic coordinate filter here.
        # Zone IDs are always valid NYC zones — no bounds check needed.

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
        df_clean = df_clean.dropna(subset=self.config.prediction_time_features)
        logger.info(f"     Removed {before - len(df_clean):,} rows with missing values")

        df_clean = df_clean.reset_index(drop=True)
        self.final_rows = len(df_clean)

        logger.info(f"✅ Cleaning complete: {self.final_rows:,} rows "
                    f"({self.final_rows/self.initial_rows*100:.1f}% retained)")
        return df_clean

    def prepare_features_target(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """Separate features and target variable."""
        logger.info("🎯 Preparing features and target...")

        X = df[self.config.prediction_time_features].copy()
        y = df['trip_duration_minutes'].values

        logger.info(f"✅ Features: {X.shape[1]} columns, {len(X):,} rows")
        logger.info(f"   Target range: [{y.min():.1f}, {y.max():.1f}] min  "
                    f"mean={y.mean():.1f}  std={y.std():.1f}")
        return X, y

    def get_statistics(self) -> dict:
        return {
            'initial_rows': self.initial_rows,
            'final_rows': self.final_rows,
            'retention_pct': (
                self.final_rows / self.initial_rows * 100
                if self.initial_rows > 0 else 0
            )
        }

    def run(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """Execute full preprocessing: clean → features/target."""
        df_clean = self.clean_data(df)
        return self.prepare_features_target(df_clean)
