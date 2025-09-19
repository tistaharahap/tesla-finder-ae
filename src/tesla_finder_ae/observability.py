"""
Logfire observability configuration for Tesla Finder AE.

Provides comprehensive tracing and spans for LLM operations, graph execution,
and CLI interactions.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import logfire


def configure_logfire(
    service_name: str = "tesla-finder-ae",
    service_version: str = "0.1.0",
    environment: Optional[str] = None
) -> None:
    """
    Configure Logfire for Tesla Finder AE with comprehensive instrumentation.
    
    Args:
        service_name: Service identifier for traces
        service_version: Version for service identification
        environment: Deployment environment (dev, prod, etc.)
    """
    # Determine environment from ENV var or default to development
    env = environment or os.getenv("TESLA_FINDER_ENV", "development")
    
    try:
        # Configure Logfire with service metadata
        logfire.configure(
            service_name=service_name,
            service_version=service_version,
            environment=env,
            send_to_logfire=False  # Disable sending to cloud in development
        )
        
        # Instrument Pydantic AI automatically - this captures:
        # - Agent creation and configuration
        # - Tool calls and responses
        # - LLM requests and responses  
        # - Model interactions and tokens
        # - Error handling and retries
        logfire.instrument_pydantic_ai()
        
        # Instrument Pydantic models for validation tracing
        logfire.instrument_pydantic()
        
        # Log successful configuration
        logfire.info(
            "🔥 Logfire configured for Tesla Finder AE",
            service_name=service_name,
            service_version=service_version,
            environment=env
        )
        
    except Exception as e:
        # Fallback to basic configuration if Logfire setup fails
        print(f"⚠️  Logfire configuration failed, using basic setup: {e}")
        try:
            logfire.configure(send_to_logfire=False)
            logfire.instrument_pydantic_ai()
            logfire.instrument_pydantic()
            print("✅ Basic Logfire setup successful")
        except Exception as fallback_error:
            print(f"❌ Logfire setup completely failed: {fallback_error}")
            print("📊 Continuing without observability")


def get_logfire_tags() -> dict[str, Any]:
    """Get consistent tags for Tesla Finder operations."""
    return {
        "component": "tesla-finder-ae",
        "operation_type": "tesla_analysis"
    }


class TeslaObservabilityMixin:
    """Mixin to add observability helpers to Tesla operations."""
    
    @staticmethod
    def log_url_processing_start(url: str, operation: str) -> None:
        """Log the start of URL processing with context."""
        logfire.info(
            "🚗 Starting Tesla {operation} for URL",
            operation=operation,
            url=url,
            **get_logfire_tags()
        )
    
    @staticmethod
    def log_url_processing_success(url: str, operation: str, metrics: dict[str, Any]) -> None:
        """Log successful URL processing with metrics."""
        logfire.info(
            "✅ Tesla {operation} completed successfully",
            operation=operation,
            url=url,
            metrics=metrics,
            **get_logfire_tags()
        )
    
    @staticmethod 
    def log_url_processing_error(url: str, operation: str, error: Exception) -> None:
        """Log URL processing errors with context."""
        logfire.error(
            "❌ Tesla {operation} failed",
            operation=operation,
            url=url,
            error_type=type(error).__name__,
            error_message=str(error),
            **get_logfire_tags()
        )
    
    @staticmethod
    def log_batch_processing_start(urls: list[str]) -> None:
        """Log the start of batch processing."""
        logfire.info(
            "📊 Starting Tesla batch processing",
            url_count=len(urls),
            urls=urls,
            **get_logfire_tags()
        )
    
    @staticmethod
    def log_batch_processing_complete(
        total_urls: int, 
        successful: int, 
        failed: int,
        processing_time_seconds: float
    ) -> None:
        """Log batch processing completion with summary metrics."""
        logfire.info(
            "🎯 Tesla batch processing completed",
            total_urls=total_urls,
            successful_urls=successful,
            failed_urls=failed,
            processing_time_seconds=processing_time_seconds,
            success_rate=successful / total_urls if total_urls > 0 else 0,
            **get_logfire_tags()
        )


# Span decorators for common operations
def tesla_operation_span(operation_name: str):
    """Decorator to add spans to Tesla operations with consistent naming."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with logfire.span(
                f"Tesla {operation_name}",
                operation=operation_name,
                **get_logfire_tags()
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.set_attribute("error_type", type(e).__name__)
                    span.set_attribute("error_message", str(e))
                    raise
        return wrapper
    return decorator


def async_tesla_operation_span(operation_name: str):
    """Async version of tesla_operation_span decorator."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with logfire.span(
                f"Tesla {operation_name}",
                operation=operation_name,
                **get_logfire_tags()
            ) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.set_attribute("error_type", type(e).__name__)
                    span.set_attribute("error_message", str(e))
                    raise
        return wrapper
    return decorator