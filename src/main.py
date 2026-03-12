import sys
import argparse
import requests
from canvas_client import fetch_courses, parse_course
from config import load_config, make_canvas_headers
from logger import log, log_exception
from smh_client import get_space_info, login_with_jaccount
from sync_service import sync_course


# ==========================
# 主程序
# ==========================

def main():
    parser = argparse.ArgumentParser(description="Sync Canvas files to SMH")
    parser.add_argument('--sync-all', action='store_true', help='Sync all semesters instead of just the latest')
    args = parser.parse_args()

    config = load_config()
    if not config.canvas_token:
        log("未检测到 CANVAS_TOKEN，请先配置后重试")
        sys.exit(2)

    headers_canvas = make_canvas_headers(config.canvas_token)
    smh_user_token = config.smh_user_token

    if not smh_user_token:
        if config.smh_jaauth_cookie:
            log("未检测到 SMH_USER_TOKEN，尝试使用 JAAuthCookie 登录...")
            token = login_with_jaccount(config.smh_base_url, config.smh_jaauth_cookie)
            if token:
                smh_user_token = token
            else:
                log("JAAuthCookie 登录失败")
                sys.exit(2)
        else:
            log("未检测到 SMH_USER_TOKEN 或 JAAuthCookie，请提供其中之一")
            sys.exit(2)

    try:
        space = get_space_info(config.smh_base_url, smh_user_token)
    except requests.RequestException as exc:
        log_exception("登录云盘失败，请检查网络和凭据", exc)
        sys.exit(2)
    except ValueError as exc:
        log_exception("登录云盘失败，响应解析异常", exc)
        log("登录云盘失败，请检查 SMH_USER_TOKEN 或 JAAuthCookie")
        sys.exit(2)

    try:
        courses = fetch_courses(config.canvas_base_url, headers_canvas)
    except requests.RequestException as exc:
        log_exception("获取 Canvas 课程列表失败", exc)
        sys.exit(2)
    except ValueError as exc:
        log_exception("解析 Canvas 课程列表失败", exc)
        sys.exit(2)

    parsed = [parse_course(c) for c in courses]

    semesters = set(course['semester'] for course in parsed if course['semester'] != "Unknown")
    mode_desc = "所有学期"
    semester_desc = "全部学期"

    if semesters:
        latest_semester = max(semesters)
        if not args.sync_all:
            parsed = [c for c in parsed if c['semester'] == latest_semester]
            mode_desc = "最新学期"
            semester_desc = latest_semester
    elif not args.sync_all:
        mode_desc = "最新学期"
        semester_desc = "Unknown"

    log(f"同步模式：{mode_desc}（{semester_desc}），待处理课程数：{len(parsed)}")

    updated = False
    for course in parsed:
        log(f"处理课程 {course['course_id']}")
        if sync_course(config, headers_canvas, space, course):
            updated = True

    if updated:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("任务被用户中断")
        sys.exit(130)
    except Exception as exc:
        log_exception("程序发生未处理异常", exc)
        sys.exit(2)