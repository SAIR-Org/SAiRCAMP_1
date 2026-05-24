"""
Retry mechanism utilities for NYC Taxi ML Pipeline
Provides decorators and functions for handling transient failures
"""
import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional


logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    delay: int = 5,
    exponential_backoff: bool = True,
    backoff_multiplier: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger_instance: Optional[logging.Logger] = None
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        exponential_backoff: Whether to use exponential backoff
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
        logger_instance: Optional logger instance for logging retry attempts
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger_instance or logger
            current_delay = delay
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    if attempt == max_retries:
                        _logger.error(
                            f"❌ {func.__name__} failed after {max_retries} attempts: {str(e)}"
                        )
                        raise
                    
                    _logger.warning(
                        f"⚠️  {func.__name__} attempt {attempt}/{max_retries} failed: {str(e)}"
                    )
                    _logger.info(f"   Retrying in {current_delay} seconds...")
                    
                    time.sleep(current_delay)
                    
                    if exponential_backoff:
                        current_delay *= backoff_multiplier
            
            return None  # Should never reach here
        
        return wrapper
    return decorator


def retry_function(
    func: Callable,
    max_retries: int = 3,
    delay: int = 5,
    exponential_backoff: bool = True,
    backoff_multiplier: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger_instance: Optional[logging.Logger] = None
) -> any:
    """
    Retry a function call with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        exponential_backoff: Whether to use exponential backoff
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
        logger_instance: Optional logger instance for logging retry attempts
        
    Returns:
        Function result
    """
    _logger = logger_instance or logger
    current_delay = delay
    
    for attempt in range(1, max_retries + 1):
        try:
            return func()
            
        except exceptions as e:
            if attempt == max_retries:
                _logger.error(
                    f"❌ Function failed after {max_retries} attempts: {str(e)}"
                )
                raise
            
            _logger.warning(
                f"⚠️  Attempt {attempt}/{max_retries} failed: {str(e)}"
            )
            _logger.info(f"   Retrying in {current_delay} seconds...")
            
            time.sleep(current_delay)
            
            if exponential_backoff:
                current_delay *= backoff_multiplier
    
    return None


class RetryableError(Exception):
    """Exception that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Exception that should not trigger a retry."""
    pass