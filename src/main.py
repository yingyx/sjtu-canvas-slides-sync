import os
import re
import requests
import subprocess
import tempfile
import sys
from pathlib import Path
from datetime import datetime
import urllib.parse
import argparse

# ==============================
# 日志函数
# ==============================

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# ==============================
# 基础配置
# ==============================

CANVAS_BASE_URL = "https://oc.sjtu.edu.cn"
CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN", "")

SMH_BASE_URL = "https://pan.sjtu.edu.cn"
SMH_USER_TOKEN = os.environ.get("SMH_USER_TOKEN", "")
SAVE_ROOT = os.environ.get("SAVE_ROOT", "Canvas Files")

CONVERT_PPT = os.getenv("CONVERT_PPT_TO_PDF", "false").lower() == "true"

HEADERS_CANVAS = {"Authorization": f"Bearer {CANVAS_TOKEN}"}

# 全局更新标志
updated = False

# ==========================
# 获取 space 信息
# ==========================

def get_space_info():
    url = f"{SMH_BASE_URL}/user/v1/space/1/personal"
    params = {"user_token": SMH_USER_TOKEN}
    r = requests.post(url, params=params)
    r.raise_for_status()
    data = r.json()
    
    log(f"获取空间信息成功")
    return {
        "libraryId": data["libraryId"],
        "spaceId": data["spaceId"],
        "accessToken": data["accessToken"]
    }


# ==========================
# Canvas API
# ==========================

def fetch_courses():
    url = f"{CANVAS_BASE_URL}/api/v1/courses?per_page=1000"
    r = requests.get(url, headers=HEADERS_CANVAS)
    r.raise_for_status()
    
    log(f"获取课程列表成功，共 {len(r.json())} 门课程")
    return r.json()


def parse_course(course):
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
        "folder": folder
    }


def fetch_files(course_id):
    url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/files"
    params = {"per_page": 1000}
    r = requests.get(url, headers=HEADERS_CANVAS, params=params)
    r.raise_for_status()
    return r.json()


# ==========================
# 转换
# ==========================

def convert_to_pdf(ppt_path: Path, out_dir: Path):
    subprocess.run([
        "soffice", "--headless",
        "--convert-to", "pdf",
        "--outdir", str(out_dir),
        str(ppt_path)
    ], check=True)
    return out_dir / (ppt_path.stem + ".pdf")


# ==========================
# SMH API
# ==========================

def ensure_folder(space, dir_path):
    """
    创建目录
    PUT /api/v1/directory/{LibraryId}/{SpaceId}/{DirPath}
    """
    url = f"{SMH_BASE_URL}/api/v1/directory/{space['libraryId']}/{space['spaceId']}/{dir_path}"
    params = {"access_token": space["accessToken"]}

    r = requests.put(url, params=params)
    if r.status_code not in (200, 201):
        r.raise_for_status()


def list_remote_dir(space, dir_path):
    url = f"{SMH_BASE_URL}/api/v1/directory/{space['libraryId']}/{space['spaceId']}/{dir_path}"
    params = {
        "access_token": space["accessToken"],
        "with_path": "true",
        "filter": "onlyFile"
    }

    r = requests.get(url, params=params)

    if r.status_code == 404:
        return None

    r.raise_for_status()
    return r.json().get("contents", [])


def upload_file(space, local_path, remote_path):
    size = os.path.getsize(local_path)

    url = f"{SMH_BASE_URL}/api/v1/file/{space['libraryId']}/{space['spaceId']}/{remote_path}"
    params = {
        "access_token": space["accessToken"],
        "filesize": size,
        "conflict_resolution_strategy": "overwrite"
    }

    r = requests.put(url, params=params)
    resp = r.json()
    r.raise_for_status()

    domain = resp.get("domain")
    path = resp.get("path")
    headers = resp.get("headers")
    confirm_key = resp.get("confirmKey")

    if not all([domain, path, headers, confirm_key]):
        log("获取上传地址失败")
        return
    
    upload_url = f"https://{domain}/{path.lstrip('/')}"
    with open(local_path, "rb") as f:
        r2 = requests.put(upload_url, headers=headers, data=f)
        r2.raise_for_status()
        
    confirm_url = f"{SMH_BASE_URL}/api/v1/file/{space['libraryId']}/{space['spaceId']}/{confirm_key}"
    confirm_params = f"confirm&access_token={space['accessToken']}&conflict_resolution_strategy=overwrite"
    r3 = requests.post(confirm_url, params=confirm_params)
    r3.raise_for_status()

# ==========================
# 同步逻辑
# ==========================

def sync_course(space, course):
    try:
        files = fetch_files(course["course_id"])
    except:
        files = []
        
    remote_folder = urllib.parse.unquote(str(Path(SAVE_ROOT) / Path(course['semester']) / Path(course['folder'])).replace("\\", "/"))

    try:
        remote_list = list_remote_dir(space, remote_folder)
    except:
        log("检查目录失败")
        return

    if remote_list is None:
        try:
            ensure_folder(space, remote_folder)
        except:
            log("创建目录失败")
            return
        remote_list = []

    for f in files:
        filename = f["filename"]
        lower = filename.lower()

        if not lower.endswith((".ppt", ".pptx", ".pdf")):
            continue

        canvas_updated = datetime.fromisoformat(
            f["updated_at"].replace("Z", "+00:00")
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            local_path = tmp_dir / filename

            if lower.endswith((".ppt", ".pptx")) and CONVERT_PPT:
                final_path = tmp_dir / (local_path.stem + ".pdf")
            else:
                final_path = local_path

            remote_file = f"{remote_folder}/{final_path.name}"
            
            matched = [x for x in remote_list if x["name"] == urllib.parse.unquote(final_path.name)]

            if matched:
                remote_time = datetime.fromisoformat(
                    matched[0]["modificationTime"].replace("Z", "+00:00")
                )
            else:
                remote_time = None

            if remote_time is None or canvas_updated > remote_time:
                try:
                    r = requests.get(f["url"], headers=HEADERS_CANVAS)
                    r.raise_for_status()
                    local_path.write_bytes(r.content)
                    if lower.endswith((".ppt", ".pptx")) and CONVERT_PPT:
                        convert_to_pdf(local_path, tmp_dir)
                    upload_file(space, str(final_path), remote_file)
                    global updated
                    updated = True
                except:
                    log("文件下载、转换或上传失败")
                    continue


# ==========================
# 主程序
# ==========================

def main():
    parser = argparse.ArgumentParser(description="Sync Canvas files to SMH")
    parser.add_argument('--sync-all', action='store_true', help='Sync all semesters instead of just the latest')
    args = parser.parse_args()

    space = get_space_info()
    courses = fetch_courses()
    parsed = [parse_course(c) for c in courses]

    semesters = set(course['semester'] for course in parsed if course['semester'] != "Unknown")
    if semesters:
        latest_semester = max(semesters)
        if not args.sync_all:
            parsed = [c for c in parsed if c['semester'] == latest_semester]

    for course in parsed:
        log(f"处理课程 {course['course_id']}")
        sync_course(space, course)

    if updated:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()