import re

import requests

from http_client import request
from logger import log, log_exception


REQUEST_TIMEOUT = 30


def fetch_paginated(url: str, headers_canvas: dict[str, str], params: dict | None = None) -> list[dict]:
    items: list[dict] = []
    next_url: str | None = url
    next_params = params

    while next_url:
        response = request(
            "GET",
            next_url,
            headers=headers_canvas,
            params=next_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Canvas 分页响应不是列表")
        items.extend(page)
        next_url = response.links.get("next", {}).get("url")
        next_params = None

    return items


def fetch_courses(canvas_base_url: str, headers_canvas: dict[str, str]) -> list[dict]:
    url = f"{canvas_base_url}/api/v1/courses"
    courses = fetch_paginated(url, headers_canvas, {"per_page": 100})
    log(f"获取课程列表成功，共 {len(courses)} 门课程")
    return courses


def parse_course(course: dict) -> dict[str, str]:
    code = course.get("course_code", "")
    semester_match = re.search(r"\((.*?)\)", code)
    semester = semester_match.group(1) if semester_match else "Unknown"

    parts = code.split("-")
    if len(parts) >= 6:
        number, name_cn = parts[4], parts[-1]
        folder = f"{number}_{name_cn}"
    else:
        folder = course.get("name", "Unknown")

    return {
        "course_id": str(course["id"]),
        "semester": semester,
        "folder": folder,
    }


def fetch_files(canvas_base_url: str, headers_canvas: dict[str, str], course_id: str) -> list[dict]:
    url = f"{canvas_base_url}/api/v1/courses/{course_id}/files"
    return fetch_paginated(url, headers_canvas, {"per_page": 100})


def fetch_folders(canvas_base_url: str, headers_canvas: dict[str, str], course_id: str) -> list[dict]:
    url = f"{canvas_base_url}/api/v1/courses/{course_id}/folders"
    return fetch_paginated(url, headers_canvas, {"per_page": 100})


def add_folder_paths(files: list[dict], folders: list[dict]) -> list[dict]:
    folder_paths: dict[int, str] = {}
    for folder in folders:
        folder_id = folder.get("id")
        full_name = str(folder.get("full_name", ""))
        if folder_id is None:
            continue
        parts = full_name.replace("\\", "/").split("/")
        folder_paths[folder_id] = "/".join(parts[1:]) if len(parts) > 1 else ""

    enriched: list[dict] = []
    for file_item in files:
        item = dict(file_item)
        folder_id = item.get("folder_id")
        if folder_id not in folder_paths:
            raise ValueError(f"找不到文件所属目录，folder_id={folder_id}")
        item["folder_path"] = folder_paths[folder_id]
        enriched.append(item)
    return enriched


def fetch_file_by_id(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str,
    file_id: int
) -> dict:
    url = f"{canvas_base_url}/api/v1/courses/{course_id}/files/{file_id}"
    response = request("GET", url, headers=headers_canvas, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_module_files(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str
) -> list[dict]:
    modules_url = f"{canvas_base_url}/api/v1/courses/{course_id}/modules"
    modules = fetch_paginated(modules_url, headers_canvas, {"per_page": 100})

    module_files: list[dict] = []
    seen_file_ids: set[int] = set()
    detail_failed = False

    for module in modules:
        module_id = module.get("id")
        if module_id is None:
            continue

        items_url = f"{canvas_base_url}/api/v1/courses/{course_id}/modules/{module_id}/items"
        items = fetch_paginated(items_url, headers_canvas, {"per_page": 100})

        for item in items:
            if item.get("type") != "File":
                continue

            file_id = item.get("content_id")
            if file_id is None or file_id in seen_file_ids:
                continue

            try:
                file_data = fetch_file_by_id(canvas_base_url, headers_canvas, course_id, file_id)
            except requests.RequestException as exc:
                log_exception(f"从 Modules 获取文件详情失败，file_id={file_id}", exc)
                detail_failed = True
                continue
            except ValueError as exc:
                log_exception(f"从 Modules 解析文件详情失败，file_id={file_id}", exc)
                detail_failed = True
                continue

            seen_file_ids.add(file_id)
            module_files.append(file_data)

    if detail_failed:
        raise RuntimeError("部分 Module 文件详情获取失败")
    return module_files


def collect_course_files(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str
) -> list[dict]:
    files: list[dict]
    try:
        files = fetch_files(canvas_base_url, headers_canvas, course_id)
    except requests.RequestException as exc:
        log_exception(f"课程 {course_id} 无法访问 Files 页面", exc)
        log(f"课程 {course_id} 无法访问 Files 页面，尝试从 Modules 获取文件")
    except ValueError as exc:
        log_exception(f"课程 {course_id} Files 响应解析失败", exc)
        log(f"课程 {course_id} Files 响应解析失败，尝试从 Modules 获取文件")
    else:
        folders = fetch_folders(canvas_base_url, headers_canvas, course_id)
        return add_folder_paths(files, folders)

    try:
        files = fetch_module_files(canvas_base_url, headers_canvas, course_id)
    except requests.RequestException as exc:
        log_exception(f"课程 {course_id} 从 Modules 获取文件失败", exc)
        raise RuntimeError(f"课程 {course_id} 无法获取文件") from exc
    except ValueError as exc:
        log_exception(f"课程 {course_id} Modules 响应解析失败", exc)
        raise RuntimeError(f"课程 {course_id} 无法解析文件") from exc

    folders = fetch_folders(canvas_base_url, headers_canvas, course_id)
    return add_folder_paths(files, folders)
