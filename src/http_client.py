from urllib3.util.retry import Retry

import requests
from requests.adapters import HTTPAdapter


RETRY_STATUS_CODES = (429, 502, 503, 504)


def make_retry_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=frozenset(("GET", "PUT")),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = make_retry_session()


def request(method: str, url: str, **kwargs) -> requests.Response:
    return SESSION.request(method, url, **kwargs)
