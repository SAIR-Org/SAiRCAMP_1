"""
Feature engineering module for NYC Taxi ML Pipeline
Handles feature creation and transformation
"""
import numpy as np
import pandas as pd
import logging
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline


logger = logging.getLogger(__name__)


class NYCTaxiFeatureEngineer(BaseEstimator, TransformerMixin):
    """Feature engineering with NO DATA LEAKAGE."""
    
    def __init__(self):
        """Initialize feature engineer."""
        self.feature_names_ = []
    
    def fit(self, X, y=None):
        """Fit (no-op for this transformer)."""
        return self
    
    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        """
        Calculate haversine distance between two points.
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            Distance in miles
        """
        R = 3958.8  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        return 2 * R * np.arcsin(np.sqrt(a))
    
    def transform(self, X):
        """
        Transform features.
        
        Args:
            X: Input features
            
        Returns:
            Engineered features
        """
        X_df = X.copy()
        X_df['tpep_pickup_datetime'] = pd.to_datetime(X_df['tpep_pickup_datetime'])
        
        # Distance features
        X_df['haversine_distance'] = self.haversine_distance(
            X_df['pickup_latitude'], X_df['pickup_longitude'],
            X_df['dropoff_latitude'], X_df['dropoff_longitude']
        )
        
        delta_lat = X_df['dropoff_latitude'] - X_df['pickup_latitude']
        delta_lon = X_df['dropoff_longitude'] - X_df['pickup_longitude']
        X_df['manhattan_distance'] = np.abs(delta_lat) * 69.0 + np.abs(delta_lon) * 53.0
        X_df['direction_sin'] = np.sin(np.arctan2(delta_lat, delta_lon))
        X_df['direction_cos'] = np.cos(np.arctan2(delta_lat, delta_lon))
        
        # Temporal features
        X_df['pickup_hour'] = X_df['tpep_pickup_datetime'].dt.hour
        X_df['pickup_dayofweek'] = X_df['tpep_pickup_datetime'].dt.dayofweek
        X_df['pickup_month'] = X_df['tpep_pickup_datetime'].dt.month
        
        # Cyclical encoding
        X_df['hour_sin'] = np.sin(2 * np.pi * X_df['pickup_hour'] / 24)
        X_df['hour_cos'] = np.cos(2 * np.pi * X_df['pickup_hour'] / 24)
        X_df['dayofweek_sin'] = np.sin(2 * np.pi * X_df['pickup_dayofweek'] / 7)
        X_df['dayofweek_cos'] = np.cos(2 * np.pi * X_df['pickup_dayofweek'] / 7)
        
        # Time flags
        X_df['is_rush_hour'] = (
            (X_df['pickup_hour'].between(7, 9)) |
            (X_df['pickup_hour'].between(16, 18))
        ).astype(int)
        X_df['is_weekend'] = X_df['pickup_dayofweek'].isin([5, 6]).astype(int)
        
        # Airport features
        X_df['pickup_from_jfk'] = self.haversine_distance(
            X_df['pickup_latitude'], X_df['pickup_longitude'], 40.6413, -73.7781
        )
        X_df['pickup_from_lga'] = self.haversine_distance(
            X_df['pickup_latitude'], X_df['pickup_longitude'], 40.7769, -73.8740
        )
        X_df['is_jfk_trip'] = (X_df['pickup_from_jfk'] < 2).astype(int)
        X_df['is_lga_trip'] = (X_df['pickup_from_lga'] < 2).astype(int)
        
        # Efficiency metrics
        X_df['efficiency_ratio'] = X_df['haversine_distance'] / (X_df['trip_distance'] + 1e-8)
        X_df['distance_per_passenger'] = X_df['trip_distance'] / (X_df['passenger_count'] + 1e-8)
        
        # Categorical encoding
        X_df['is_vendor_2'] = (X_df['VendorID'] == 2).astype(int)
        X_df['is_credit_card'] = (X_df['payment_type'] == 1).astype(int)
        
        # Interaction features
        X_df['distance_times_passengers'] = X_df['trip_distance'] * X_df['passenger_count']
        X_df['haversine_times_hour'] = X_df['haversine_distance'] * X_df['pickup_hour']
        
        # Drop original columns
        cols_to_drop = ['tpep_pickup_datetime', 'VendorID', 'RatecodeID', 'payment_type']
        X_df = X_df.drop(columns=cols_to_drop, errors='ignore')
        
        # Select numeric columns
        numeric_cols = X_df.select_dtypes(include=[np.number]).columns.tolist()
        self.feature_names_ = numeric_cols
        
        return X_df[numeric_cols].values
    
    def get_feature_names(self):
        """Get feature names."""
        return self.feature_names_


class OutlierHandler(BaseEstimator, TransformerMixin):
    """IQR-based outlier handling."""
    
    def __init__(self, factor=1.5):
        """
        Initialize outlier handler.
        
        Args:
            factor: IQR multiplier for bounds
        """
        self.factor = factor
        self.lower_bounds_ = None
        self.upper_bounds_ = None
    
    def fit(self, X, y=None):
        """
        Fit outlier bounds on training data.
        
        Args:
            X: Training features
            y: Ignored
            
        Returns:
            self
        """
        self.lower_bounds_ = []
        self.upper_bounds_ = []
        for i in range(X.shape[1]):
            Q1 = np.percentile(X[:, i], 25)
            Q3 = np.percentile(X[:, i], 75)
            IQR = Q3 - Q1
            self.lower_bounds_.append(Q1 - self.factor * IQR)
            self.upper_bounds_.append(Q3 + self.factor * IQR)
        return self
    
    def transform(self, X):
        """
        Transform by clipping outliers.
        
        Args:
            X: Input features
            
        Returns:
            Clipped features
        """
        X_transformed = X.copy()
        for i in range(X.shape[1]):
            X_transformed[:, i] = np.clip(
                X_transformed[:, i],
                self.lower_bounds_[i],
                self.upper_bounds_[i]
            )
        return X_transformed


def build_preprocessor(iqr_factor: float = 1.5) -> Pipeline:
    """
    Build preprocessing pipeline.
    
    Args:
        iqr_factor: IQR multiplier for outlier handling
        
    Returns:
        Preprocessing pipeline
    """
    logger.info("🔧 Building preprocessing pipeline...")
    
    pipeline = Pipeline([
        ('feature_engineer', NYCTaxiFeatureEngineer()),
        ('outlier_handler', OutlierHandler(factor=iqr_factor)),
        ('scaler', RobustScaler())
    ])
    
    logger.info("✅ Preprocessing pipeline created")
    logger.info("   Steps:")
    logger.info("   1. Feature Engineering (distance, temporal, airport, etc.)")
    logger.info("   2. Outlier Handling (IQR-based clipping)")
    logger.info("   3. Robust Scaling")
    
    return pipeline