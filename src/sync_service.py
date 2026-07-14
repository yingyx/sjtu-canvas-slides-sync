import tempfile
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from requests import RequestException

from canvas_client import collect_course_files
from config import AppConfig
from converter import convert_to_pdf, get_converted_pdf_name
from http_client import request
from logger import log, log_exception
from smh_client import ensure_folder, list_remote_dir, upload_file


REQUEST_TIMEOUT = 60
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass
class SyncResult:
    discovered_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    downloaded_bytes: int = 0
    uploaded_bytes: int = 0
    converted_count: int = 0

    @property
    def updated(self) -> bool:
        return self.updated_count > 0

    def merge(self, other: "SyncResult") -> None:
        for field in self.__dataclass_fields__:
            setattr(self, field, getattr(self, field) + getattr(other, field))


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
) -> SyncResult:
    result = SyncResult()
    try:
        files = collect_course_files(config.canvas_base_url, headers_canvas, course["course_id"])
    except (RequestException, ValueError, RuntimeError) as exc:
        log_exception(f"课程 {course['course_id']} 获取文件失败", exc)
        result.failed_count = 1
        return result
    result.discovered_count = len(files)

    remote_folder = remote_path(config.save_root, course["semester"], course["folder"])

    try:
        remote_list = list_remote_dir(config.smh_base_url, space, remote_folder)
    except RequestException as exc:
        log_exception("检查云盘目录失败", exc)
        result.failed_count = 1
        return result
    except ValueError as exc:
        log_exception("解析云盘目录响应失败", exc)
        result.failed_count = 1
        return result

    if remote_list is None:
        try:
            ensure_folder(config.smh_base_url, space, remote_folder)
        except RequestException as exc:
            log_exception("创建云盘目录失败", exc)
            result.failed_count = 1
            return result
        remote_list = []

    remote_lists: dict[str, list[dict]] = {remote_folder: remote_list}

    for file_item in files:
        canvas_filename = urllib.parse.unquote(
            str(file_item.get("display_name") or file_item.get("filename", ""))
        )
        filename_parts = safe_path_parts(canvas_filename)
        filename = filename_parts[-1] if filename_parts else f"file-{file_item.get('id', 'unknown')}"
        lower = filename.lower()

        file_ext = None
        for ext in config.file_extensions:
            if lower.endswith(ext):
                file_ext = ext
                break
        if file_ext is None:
            result.skipped_count += 1
            continue

        if (
            config.max_file_size_mb > 0
            and file_item.get("size", 0) > config.max_file_size_mb * 1024 * 1024
        ):
            log(f"跳过文件 {filename}（超过大小限制）")
            result.skipped_count += 1
            continue

        canvas_updated = datetime.fromisoformat(file_item["updated_at"].replace("Z", "+00:00"))

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_dir = Path(temp_dir)
            local_path = tmp_dir / filename
            file_remote_folder = remote_path(remote_folder, file_item.get("folder_path", ""))
            if file_remote_folder not in remote_lists:
                try:
                    ensure_folder(config.smh_base_url, space, file_remote_folder)
                except RequestException as exc:
                    log_exception(f"创建云盘子目录失败：{file_remote_folder}", exc)
                    result.failed_count += 1
                    continue
                try:
                    folder_list = list_remote_dir(config.smh_base_url, space, file_remote_folder)
                except (RequestException, ValueError) as exc:
                    log_exception(f"检查云盘子目录失败：{file_remote_folder}", exc)
                    result.failed_count += 1
                    continue
                remote_lists[file_remote_folder] = folder_list or []
            current_remote_list = remote_lists[file_remote_folder]
            should_convert = file_ext in config.convert_extensions and config.convert_ppt

            if should_convert:
                final_path = tmp_dir / get_converted_pdf_name(local_path)
            else:
                final_path = local_path

            remote_file = remote_path(file_remote_folder, final_path.name)
            matched = [
                item
                for item in current_remote_list
                if item["name"] == final_path.name
            ]

            if matched:
                remote_time = datetime.fromisoformat(
                    matched[0]["modificationTime"].replace("Z", "+00:00")
                )
            else:
                remote_time = None

            if remote_time is None or canvas_updated > remote_time:
                transfer_stage = "下载"
                try:
                    response = request(
                        "GET",
                        file_item["url"],
                        headers=headers_canvas,
                        timeout=REQUEST_TIMEOUT,
                        stream=True,
                    )
                    response.raise_for_status()
                    file_downloaded = 0
                    with local_path.open("wb") as output:
                        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                output.write(chunk)
                                file_downloaded += len(chunk)
                    expected_size = file_item.get("size")
                    if expected_size is not None and file_downloaded != int(expected_size):
                        raise RuntimeError(
                            f"下载大小不一致：预期 {expected_size}，实际 {file_downloaded}"
                        )
                    result.downloaded_bytes += file_downloaded
                    if should_convert:
                        transfer_stage = "转换"
                        final_path = convert_to_pdf(local_path, tmp_dir)
                        result.converted_count += 1
                    uploaded_size = final_path.stat().st_size
                    transfer_stage = "上传"
                    upload_file(config.smh_base_url, space, str(final_path), remote_file)
                    result.uploaded_bytes += uploaded_size
                    result.updated_count += 1
                except (RequestException, ValueError, RuntimeError) as exc:
                    log_exception(f"文件{transfer_stage}失败：{filename}", exc)
                    result.failed_count += 1
                    continue
                except OSError as exc:
                    log_exception(f"文件{transfer_stage}处理失败：{filename}", exc)
                    result.failed_count += 1
                    continue
            else:
                result.skipped_count += 1

    return result
