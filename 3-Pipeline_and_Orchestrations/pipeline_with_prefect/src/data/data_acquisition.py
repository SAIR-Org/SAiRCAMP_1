"""
Data acquisition module for NYC Taxi ML Pipeline
==================================================
CHANGES FROM pipline_no_perfect/:

  REMOVED: @retry_with_backoff decorators on download_dataset() and load_data()
  WHY:     Prefect's @task(retries=3, retry_delay_seconds=10) in flow.py replaces
           the manual retry decorator. Retries are now visible in the Prefect UI
           with full state history — you can see which attempt failed and why.

Everything else is identical to pipline_no_perfect/src/data/data_acquisition.py.
"""
import pandas as pd
import kagglehub
from pathlib import Path
from typing import Optional
import logging

from config.config import DataConfig


logger = logging.getLogger(__name__)


class DataAcquisition:
    """Handle data acquisition from Kaggle."""

    def __init__(self, config: DataConfig):
        self.config = config
        self.dataset_path: Optional[str] = None
        self.file_path: Optional[str] = None

    def download_dataset(self) -> str:
        """
        Download NYC Taxi dataset from Kaggle.

        Retries are handled by Prefect @task(retries=3) in flow.py —
        no manual retry decorator needed here.
        """
        logger.info(f"📥 Downloading dataset: {self.config.dataset_name}")

        try:
            path = kagglehub.dataset_download(self.config.dataset_name)
            self.dataset_path = path
            self.file_path = f"{path}/{self.config.file_name}"

            logger.info(f"✅ Dataset downloaded to: {path}")

            if not Path(self.file_path).exists():
                raise FileNotFoundError(f"File not found after download: {self.file_path}")

            return self.dataset_path

        except Exception as e:
            logger.error(f"❌ Download failed: {str(e)}")
            raise

    def load_data(self) -> pd.DataFrame:
        """
        Load data from CSV in chunks.

        Retries are handled by Prefect @task(retries=3) in flow.py.
        """
        if not self.file_path:
            raise ValueError("Dataset not downloaded. Call download_dataset() first.")

        logger.info(f"📊 Loading data from: {self.file_path}")

        try:
            chunks = pd.read_csv(
                self.file_path,
                chunksize=self.config.chunk_size,
                low_memory=False
            )

            chunk_list = []
            for i, chunk in enumerate(chunks):
                if i >= self.config.num_chunks:
                    break
                chunk_list.append(chunk)
                logger.info(f"   ✓ Loaded chunk {i+1}/{self.config.num_chunks}: {len(chunk):,} rows")

            df = pd.concat(chunk_list, ignore_index=True)

            logger.info(f"✅ Data loaded: {df.shape[0]:,} rows, {df.shape[1]} columns")
            logger.info(f"   Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

            return df

        except Exception as e:
            logger.error(f"❌ Data loading failed: {str(e)}")
            raise

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate loaded data has required columns."""
        required_columns = set(
            self.config.prediction_time_features + ['tpep_dropoff_datetime']
        )
        missing_columns = required_columns - set(df.columns)

        if missing_columns:
            logger.error(f"❌ Missing columns: {missing_columns}")
            return False

        logger.info(f"✅ Schema valid — {len(df.columns)} columns, "
                    f"{df.isnull().sum().sum():,} missing values")
        return True

    def run(self) -> pd.DataFrame:
        """Execute full data acquisition: download → load → validate."""
        self.download_dataset()
        df = self.load_data()

        if not self.validate_data(df):
            raise ValueError("Data validation failed — missing required columns")

        return df
