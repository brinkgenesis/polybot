import logging
import sys

def setup_logger():
    # Configure root logger
    logging.basicConfig(level=logging.INFO, format='%(message)s', force=True)

    # Create a logger
    logger = logging.getLogger('main_logger')

    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create a single StreamHandler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter('%(message)s'))

    # Add the StreamHandler to the logger
    logger.addHandler(stream_handler)

    # Set the logger to not propagate messages to avoid duplication
    logger.propagate = False

    # Set the level for the logger
    logger.setLevel(logging.INFO)

    return logger

# Create a single instance of the logger
main_logger = setup_logger()
