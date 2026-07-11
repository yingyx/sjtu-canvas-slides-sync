import re
import urllib.parse

import requests

from http_client import request
from logger import log, log_exception


REQUEST_TIMEOUT = 30


def login_with_jaccount(smh_base_url: str, jaauth_cookie: str) -> str | None:
    try:
        cookies = {"JAAuthCookie": jaauth_cookie}
        sso_login_url = (
            f"{smh_base_url}/user/v1/sign-in/sso-login-redirect/xpw8ou8y"
            "?auto_redirect=true&from=web&custom_state=4ycSqbzfqM9mPuzOKmvTUQ%25253D%25253D"
        )

        session = requests.Session()
        session.cookies.update(cookies)

        log("正在执行 JAAuthCookie 登录...")

        response = session.get(
            sso_login_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        if "jaccount" in response.url:
            log("JAAuthCookie 认证失败")
            return None

        code_match = re.search(r"code=(.+?)&state=", response.url)
        if not code_match:
            log("未能从回调URL中找到 code")
            return None

        code = code_match.group(1)
        log("成功获取认证 code")

        verify_url = (
            f"{smh_base_url}/user/v1/sign-in/verify-account-login/xpw8ou8y"
            f"?device_id=Chrome+116.0.0.0&type=sso&credential={code}"
        )

        verify_resp = session.post(verify_url, timeout=REQUEST_TIMEOUT)
        verify_resp.raise_for_status()

        response_data = verify_resp.json()
        user_token = response_data.get("userToken", "")
        if len(user_token) != 128:
            log("获取到的 UserToken 无效")
            return None

        log("成功通过 JAAuthCookie 获取 SMH_USER_TOKEN")
        return user_token
    except requests.RequestException as exc:
        log_exception("JAAuthCookie 登录网络请求失败", exc)
        return None
    except ValueError as exc:
        log_exception("JAAuthCookie 登录响应解析失败", exc)
        return None
    except Exception as exc:
        log_exception("JAAuthCookie 登录过程出错", exc)
        return None


def get_space_info(smh_base_url: str, smh_user_token: str) -> dict[str, str]:
    url = f"{smh_base_url}/user/v1/space/1/personal"
    params = {"user_token": smh_user_token}
    response = request("POST", url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    log("获取空间信息成功")
    return {
        "libraryId": data["libraryId"],
        "spaceId": data["spaceId"],
        "accessToken": data["accessToken"],
    }


def ensure_folder(smh_base_url: str, space: dict[str, str], dir_path: str) -> None:
    encoded_path = urllib.parse.quote(dir_path, safe="/")
    url = f"{smh_base_url}/api/v1/directory/{space['libraryId']}/{space['spaceId']}/{encoded_path}"
    params = {"access_token": space["accessToken"]}

    response = request("PUT", url, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code not in (200, 201):
        response.raise_for_status()


def list_remote_dir(smh_base_url: str, space: dict[str, str], dir_path: str) -> list[dict] | None:
    encoded_path = urllib.parse.quote(dir_path, safe="/")
    url = f"{smh_base_url}/api/v1/directory/{space['libraryId']}/{space['spaceId']}/{encoded_path}"
    params = {
        "access_token": space["accessToken"],
        "with_path": "true",
        "filter": "onlyFile",
    }

    response = request("GET", url, params=params, timeout=REQUEST_TIMEOUT)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json().get("contents", [])


def upload_file(smh_base_url: str, space: dict[str, str], local_path: str, remote_path: str) -> None:
    import os

    size = os.path.getsize(local_path)

    encoded_path = urllib.parse.quote(remote_path, safe="/")
    url = f"{smh_base_url}/api/v1/file/{space['libraryId']}/{space['spaceId']}/{encoded_path}"
    params = {
        "access_token": space["accessToken"],
        "filesize": size,
        "conflict_resolution_strategy": "overwrite",
    }

    response = request("PUT", url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    resp = response.json()

    domain = resp.get("domain")
    path = resp.get("path")
    headers = resp.get("headers")
    confirm_key = resp.get("confirmKey")

    if not all([domain, path, headers, confirm_key]):
        raise ValueError("获取上传地址失败：响应缺少必要字段")

    upload_url = f"https://{domain}/{path.lstrip('/')}"
    with open(local_path, "rb") as file_obj:
        upload_resp = requests.put(
            upload_url,
            headers=headers,
            data=file_obj,
            timeout=REQUEST_TIMEOUT,
        )
        upload_resp.raise_for_status()

    confirm_url = f"{smh_base_url}/api/v1/file/{space['libraryId']}/{space['spaceId']}/{confirm_key}"
    confirm_params = (
        f"confirm&access_token={space['accessToken']}&conflict_resolution_strategy=overwrite"
    )
    confirm_resp = requests.post(confirm_url, params=confirm_params, timeout=REQUEST_TIMEOUT)
    confirm_resp.raise_for_status()
