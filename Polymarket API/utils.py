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