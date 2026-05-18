"""
Data acquisition module for NYC Taxi ML Pipeline
Handles data download, loading, and initial validation
"""
import pandas as pd
import kagglehub
from pathlib import Path
from typing import Optional
import logging

from src.utils.retry_utils import retry_with_backoff, RetryableError
from config.config import DataConfig


logger = logging.getLogger(__name__)


class DataAcquisition:
    """Handle data acquisition from Kaggle."""
    
    def __init__(self, config: DataConfig):
        """
        Initialize data acquisition.
        
        Args:
            config: Data configuration
        """
        self.config = config
        self.dataset_path: Optional[str] = None
        self.file_path: Optional[str] = None
    
    @retry_with_backoff(
        max_retries=3,
        delay=10,
        exceptions=(Exception,)
    )
    def download_dataset(self) -> str:
        """
        Download NYC Taxi dataset from Kaggle.
        
        Returns:
            Path to downloaded dataset
            
        Raises:
            RetryableError: If download fails
        """
        logger.info(f"📥 Downloading dataset: {self.config.dataset_name}")
        
        try:
            path = kagglehub.dataset_download(self.config.dataset_name)
            self.dataset_path = path
            self.file_path = f"{path}/{self.config.file_name}"
            
            logger.info(f"✅ Dataset downloaded to: {path}")
            logger.info(f"✅ Target file: {self.file_path}")
            
            # Validate file exists
            if not Path(self.file_path).exists():
                raise RetryableError(f"File not found: {self.file_path}")
            
            return self.dataset_path
            
        except Exception as e:
            logger.error(f"❌ Download failed: {str(e)}")
            raise RetryableError(f"Failed to download dataset: {str(e)}")
    
    @retry_with_backoff(
        max_retries=2,
        delay=5,
        exceptions=(pd.errors.EmptyDataError, FileNotFoundError)
    )
    def load_data(self) -> pd.DataFrame:
        """
        Load data from CSV in chunks.
        
        Returns:
            Concatenated DataFrame
            
        Raises:
            RetryableError: If loading fails
        """
        if not self.file_path:
            raise ValueError("Dataset not downloaded. Call download_dataset() first.")
        
        logger.info(f"📊 Loading data from: {self.file_path}")
        logger.info(f"   Chunk size: {self.config.chunk_size:,}")
        logger.info(f"   Number of chunks: {self.config.num_chunks}")
        
        try:
            chunks = pd.read_csv(
                self.file_path,
                chunksize=self.config.chunk_size,
                low_memory=False
            )
            
            # Load specified number of chunks
            chunk_list = []
            for i, chunk in enumerate(chunks):
                if i >= self.config.num_chunks:
                    break
                chunk_list.append(chunk)
                logger.info(f"   ✓ Loaded chunk {i+1}/{self.config.num_chunks}: {len(chunk):,} rows")
            
            # Concatenate chunks
            df = pd.concat(chunk_list, ignore_index=True)
            
            logger.info(f"✅ Data loaded: {df.shape[0]:,} rows, {df.shape[1]} columns")
            logger.info(f"   Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Data loading failed: {str(e)}")
            raise RetryableError(f"Failed to load data: {str(e)}")
    
    def validate_data(self, df: pd.DataFrame) -> bool:
        """
        Validate loaded data has required columns.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            True if valid, False otherwise
        """
        logger.info("🔍 Validating data schema...")
        
        required_columns = set(
            self.config.prediction_time_features + 
            ['tpep_dropoff_datetime']
        )
        
        missing_columns = required_columns - set(df.columns)
        
        if missing_columns:
            logger.error(f"❌ Missing columns: {missing_columns}")
            return False
        
        logger.info(f"✅ All required columns present")
        logger.info(f"   Total columns: {len(df.columns)}")
        logger.info(f"   Missing values: {df.isnull().sum().sum():,}")
        
        return True
    
    def run(self) -> pd.DataFrame:
        """
        Execute full data acquisition pipeline.
        
        Returns:
            Loaded and validated DataFrame
        """
        logger.info("=" * 70)
        logger.info("STARTING DATA ACQUISITION".center(70))
        logger.info("=" * 70)
        
        # Download
        self.download_dataset()
        
        # Load
        df = self.load_data()
        
        # Validate
        if not self.validate_data(df):
            raise ValueError("Data validation failed")
        
        logger.info("✅ Data acquisition completed successfully")
        
        return df