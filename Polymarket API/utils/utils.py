import asyncio
from typing import Any, Callable

def shorten_id(id_string: str, length: int = 6) -> str:
    """
    Shortens an identifier string for easier readability in logs.

    :param id_string: The original identifier string.
    :param length: The number of characters to retain from the start and end.
    :return: The shortened identifier.
    """
    if len(id_string) <= length * 2:
        return id_string
    return f"{id_string[:length]}...{id_string[-length:]}"



async def run_sync_in_thread(func: Callable, *args, **kwargs) -> Any:
    """
    Runs a synchronous function in a separate thread and returns its result.

    :param func: The synchronous function to run.
    :param args: Positional arguments for the function.
    :param kwargs: Keyword arguments for the function.
    :return: The result of the function.
    """
    return await asyncio.to_thread(func, *args, **kwargs)