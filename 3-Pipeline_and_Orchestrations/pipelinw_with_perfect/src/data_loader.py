"""
Data Loading Module
Handles downloading and initial loading of NYC Taxi dataset
"""

import pandas as pd
from pathlib import Path
from prefect import task, get_run_logger
import kagglehub


@task(name="download_dataset", retries=2, retry_delay_seconds=10)
def download_dataset() -> str:
    """
    Download NYC Yellow Taxi dataset from Kaggle.
    
    Returns:
        str: Path to the downloaded dataset directory
    """
    logger = get_run_logger()
    
    logger.info("📥 Downloading NYC Yellow Taxi dataset from Kaggle...")
    
    try:
        path = kagglehub.dataset_download("elemento/nyc-yellow-taxi-trip-data")
        logger.info(f"✅ Dataset downloaded to: {path}")
        return path
    except Exception as e:
        logger.error(f"❌ Failed to download dataset: {str(e)}")
        raise


@task(name="load_data_chunks")
def load_data_chunks(dataset_path: str, sample_size: int = 1000000) -> pd.DataFrame:
    """
    Load data from CSV in chunks and combine.
    
    Args:
        dataset_path: Path to the dataset directory
        sample_size: Number of rows to load (loads in chunks of 500k)
        
    Returns:
        pd.DataFrame: Combined dataframe
    """
    logger = get_run_logger()
    
    csv_file = Path(dataset_path) / "yellow_tripdata_2016-01.csv"
    
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")
    
    logger.info(f"📊 Loading data from: {csv_file}")
    logger.info(f"   Target sample size: {sample_size:,} rows")
    
    try:
        # Load in chunks
        chunks = []
        chunk_size = 500_000
        rows_loaded = 0
        
        for chunk in pd.read_csv(csv_file, chunksize=chunk_size, low_memory=False):
            chunks.append(chunk)
            rows_loaded += len(chunk)
            
            logger.info(f"   Loaded chunk: {len(chunk):,} rows (Total: {rows_loaded:,})")
            
            if rows_loaded >= sample_size:
                break
        
        # Combine chunks
        df = pd.concat(chunks, ignore_index=True)
        
        logger.info(f"✅ Data loaded: {df.shape[0]:,} rows, {df.shape[1]} columns")
        logger.info(f"   Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        return df
        
    except Exception as e:
        logger.error(f"❌ Failed to load data: {str(e)}")
        raise