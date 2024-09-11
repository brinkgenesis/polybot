def shorten_id(id_string):
    if len(id_string) <= 8:
        return id_string
    return f"{id_string[:4]}...{id_string[-4:]}"
