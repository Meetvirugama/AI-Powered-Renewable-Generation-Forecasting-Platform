import logging
import json
from datetime import datetime

class JsonFormatter(logging.Formatter):
    """Structured JSON-like logging formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configures structured JSON-like logging and returns the main logger."""
    logger = logging.getLogger("renewable_platform")
    
    # Avoid duplicating handlers if setup_logging is called multiple times
    if not logger.handlers:
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(numeric_level)
        
        handler = logging.StreamHandler()
        handler.setLevel(numeric_level)
        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Prevent propagation to the root logger
        logger.propagate = False
        
    return logger

def get_logger(name: str) -> logging.Logger:
    """Convenience function to get a child logger."""
    return logging.getLogger(f"renewable_platform.{name}")
