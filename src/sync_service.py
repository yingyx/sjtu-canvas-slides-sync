import tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from requests import RequestException

from canvas_client import collect_course_files
from config import AppConfig
from converter import convert_to_pdf, get_converted_pdf_name
from logger import log, log_exception
from smh_client import ensure_folder, list_remote_dir, upload_file


REQUEST_TIMEOUT = 60


def safe_path_parts(path: str) -> list[str]:
    parts: list[str] = []
    for raw_part in path.replace("\\", "/").split("/"):
        part = "".join(char for char in raw_part if ord(char) >= 32).strip()
        if not part or part in (".", ".."):
            continue
        parts.append(part.replace("/", "_").replace("\\", "_"))
    return parts


def remote_path(*parts: str) -> str:
    safe_parts: list[str] = []
    for part in parts:
        safe_parts.extend(safe_path_parts(part))
    return "/".join(safe_parts)


def sync_course(
    config: AppConfig,
    headers_canvas: dict[str, str],
    space: dict[str, str],
    course: dict[str, str],
) -> bool:
    files = collect_course_files(config.canvas_base_url, headers_canvas, course["course_id"])

    remote_folder = remote_path(config.save_root, course["semester"], course["folder"])

    try:
        remote_list = list_remote_dir(config.smh_base_url, space, remote_folder)
    except RequestException as exc:
        log_exception("检查云盘目录失败", exc)
        return False
    except ValueError as exc:
        log_exception("解析云盘目录响应失败", exc)
        return False

    if remote_list is None:
        try:
            ensure_folder(config.smh_base_url, space, remote_folder)
        except RequestException as exc:
            log_exception("创建云盘目录失败", exc)
            return False
        remote_list = []

    updated = False
    downloaded_bytes = 0
    uploaded_bytes = 0
    converted_count = 0

    for file_item in files:
        filename = Path(str(file_item["filename"]).replace("\\", "/")).name
        lower = filename.lower()

        file_ext = None
        for ext in config.file_extensions:
            if lower.endswith(ext):
                file_ext = ext
                break
        if file_ext is None:
            continue

        if (
            config.max_file_size_mb > 0
            and file_item.get("size", 0) > config.max_file_size_mb * 1024 * 1024
        ):
            log(f"跳过文件 {filename}（超过大小限制）")
            continue

        canvas_updated = datetime.fromisoformat(file_item["updated_at"].replace("Z", "+00:00"))

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_dir = Path(temp_dir)
            local_path = tmp_dir / filename
            file_remote_folder = remote_path(remote_folder, file_item.get("folder_path", ""))
            if file_remote_folder != remote_folder:
                try:
                    ensure_folder(config.smh_base_url, space, file_remote_folder)
                except RequestException as exc:
                    log_exception(f"创建云盘子目录失败：{file_remote_folder}", exc)
                    continue
                try:
                    folder_list = list_remote_dir(config.smh_base_url, space, file_remote_folder)
                except (RequestException, ValueError) as exc:
                    log_exception(f"检查云盘子目录失败：{file_remote_folder}", exc)
                    continue
                current_remote_list = folder_list or []
            else:
                current_remote_list = remote_list
            should_convert = file_ext in config.convert_extensions and config.convert_ppt

            if should_convert:
                final_path = tmp_dir / get_converted_pdf_name(local_path)
            else:
                final_path = local_path

            remote_file = remote_path(file_remote_folder, final_path.name)
            matched = [
                item
                for item in current_remote_list
                if item["name"] == urllib.parse.unquote(final_path.name)
            ]

            if matched:
                remote_time = datetime.fromisoformat(
                    matched[0]["modificationTime"].replace("Z", "+00:00")
                )
            else:
                remote_time = None

            if remote_time is None or canvas_updated > remote_time:
                try:
                    response = requests.get(
                        file_item["url"],
                        headers=headers_canvas,
                        timeout=REQUEST_TIMEOUT,
                    )
                    response.raise_for_status()
                    local_path.write_bytes(response.content)
                    downloaded_bytes += len(response.content)
                    if should_convert:
                        final_path = convert_to_pdf(local_path, tmp_dir)
                        converted_count += 1
                    uploaded_bytes += final_path.stat().st_size
                    upload_file(config.smh_base_url, space, str(final_path), remote_file)
                    updated = True
                except RequestException as exc:
                    log_exception(f"文件传输失败：{filename}", exc)
                    continue
                except OSError as exc:
                    log_exception(f"文件写入失败：{filename}", exc)
                    continue
                except RuntimeError as exc:
                    log_exception(f"文件转换失败：{filename}", exc)
                    continue

    return {
        "updated": updated,
        "downloaded_bytes": downloaded_bytes,
        "uploaded_bytes": uploaded_bytes,
        "converted_count": converted_count,
    }
