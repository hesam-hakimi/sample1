class HTTPError(Exception):
    pass


def get(url, **kwargs):
    raise NotImplementedError("Network access is disabled in this environment")
