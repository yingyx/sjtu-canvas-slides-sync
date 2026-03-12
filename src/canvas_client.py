import re

import requests

from logger import log, log_exception


REQUEST_TIMEOUT = 30


def fetch_courses(canvas_base_url: str, headers_canvas: dict[str, str]) -> list[dict]:
    url = f"{canvas_base_url}/api/v1/courses?per_page=1000"
    response = requests.get(url, headers=headers_canvas, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    courses = response.json()
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
    params = {"per_page": 1000}
    response = requests.get(
        url,
        headers=headers_canvas,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def fetch_file_by_id(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str,
    file_id: int
) -> dict:
    url = f"{canvas_base_url}/api/v1/courses/{course_id}/files/{file_id}"
    response = requests.get(url, headers=headers_canvas, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_module_files(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str
) -> list[dict]:
    modules_url = f"{canvas_base_url}/api/v1/courses/{course_id}/modules"
    modules_resp = requests.get(
        modules_url,
        headers=headers_canvas,
        params={"per_page": 1000},
        timeout=REQUEST_TIMEOUT,
    )
    modules_resp.raise_for_status()
    modules = modules_resp.json()

    module_files: list[dict] = []
    seen_file_ids: set[int] = set()

    for module in modules:
        module_id = module.get("id")
        if module_id is None:
            continue

        items_url = f"{canvas_base_url}/api/v1/courses/{course_id}/modules/{module_id}/items"
        items_resp = requests.get(
            items_url,
            headers=headers_canvas,
            params={"per_page": 1000},
            timeout=REQUEST_TIMEOUT,
        )
        items_resp.raise_for_status()
        items = items_resp.json()

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
                continue
            except ValueError as exc:
                log_exception(f"从 Modules 解析文件详情失败，file_id={file_id}", exc)
                continue

            seen_file_ids.add(file_id)
            module_files.append(file_data)

    return module_files


def collect_course_files(
    canvas_base_url: str,
    headers_canvas: dict[str, str],
    course_id: str
) -> list[dict]:
    try:
        return fetch_files(canvas_base_url, headers_canvas, course_id)
    except requests.RequestException as exc:
        log_exception(f"课程 {course_id} 无法访问 Files 页面", exc)
        log(f"课程 {course_id} 无法访问 Files 页面，尝试从 Modules 获取文件")
    except ValueError as exc:
        log_exception(f"课程 {course_id} Files 响应解析失败", exc)
        log(f"课程 {course_id} Files 响应解析失败，尝试从 Modules 获取文件")

    try:
        return fetch_module_files(canvas_base_url, headers_canvas, course_id)
    except requests.RequestException as exc:
        log_exception(f"课程 {course_id} 从 Modules 获取文件失败", exc)
        return []
    except ValueError as exc:
        log_exception(f"课程 {course_id} Modules 响应解析失败", exc)
        return []
