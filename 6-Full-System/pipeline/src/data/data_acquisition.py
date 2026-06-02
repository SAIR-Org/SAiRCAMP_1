"""Download NYC TLC parquet data directly from the official source."""
import pandas as pd
import logging
from typing import List, Optional

from config.config import DataConfig


logger = logging.getLogger(__name__)


class DataAcquisition:
    """Download NYC TLC parquet data directly by year and month."""

    def __init__(self, config: DataConfig):
        self.config = config

    def download_month(self, year: int, month: int) -> pd.DataFrame:
        """
        Download one month of TLC data directly from the official source.

        Retries are handled by Prefect @task(retries=3) in flow.py.
        """
        url = self.config.tlc_url_template.format(year=year, month=month)
        logger.info(f"   📥 {year}-{month:02d}: {url}")

        df = pd.read_parquet(url, columns=self.config.raw_columns)

        logger.info(f"   ✓ {year}-{month:02d}: {len(df):,} rows downloaded")
        return df

    def sample_month(self, df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
        """Sample rows from a single month, log what was kept."""
        n = min(self.config.samples_per_month, len(df))
        sampled = df.sample(n=n, random_state=42)
        logger.info(f"   ✓ {year}-{month:02d}: sampled {n:,} / {len(df):,} rows")
        return sampled

    def validate_data(self, df: pd.DataFrame) -> bool:
        """Validate loaded data has required columns."""
        required = set(self.config.prediction_time_features + ['tpep_dropoff_datetime'])
        missing = required - set(df.columns)

        if missing:
            logger.error(f"❌ Missing columns: {missing}")
            return False

        logger.info(f"✅ Schema valid — {len(df.columns)} columns, "
                    f"{df.isnull().sum().sum():,} missing values")
        return True

    def run(self) -> pd.DataFrame:
        """
        Download and combine all configured years and months.

        Supports multi-year retraining (e.g. train_years=[2019, 2020]).
        Peak memory = one full month + accumulated samples.
        """
        total_periods = len(self.config.train_years) * len(self.config.train_months)
        logger.info(f"📥 Downloading TLC data: years={self.config.train_years}")
        logger.info(f"   Months    : {self.config.train_months}")
        logger.info(f"   Per period: {self.config.samples_per_month:,} rows")
        logger.info(f"   Total     : ~{self.config.sample_size:,} rows "
                    f"({total_periods} periods)")

        chunks = []
        for year in self.config.train_years:
            for month in self.config.train_months:
                df_month   = self.download_month(year, month)
                df_sampled = self.sample_month(df_month, year, month)
                chunks.append(df_sampled)
                del df_month

        df = pd.concat(chunks, ignore_index=True)
        logger.info(f"✅ Combined: {len(df):,} rows from {total_periods} periods")

        if not self.validate_data(df):
            raise ValueError("Data validation failed — missing required columns")

        return df
