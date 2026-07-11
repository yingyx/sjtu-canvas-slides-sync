import sys
import argparse
import os
from pathlib import Path
import requests
from canvas_client import fetch_courses, parse_course
from config import load_config, make_canvas_headers
from logger import log, log_exception
from smh_client import get_space_info, login_with_jaccount
from sync_service import SyncResult, sync_course


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

    total = SyncResult()

    for course in parsed:
        log(f"处理课程 {course['course_id']}")
        result = sync_course(config, headers_canvas, space, course)
        total.merge(result)

    def fmt_size(n: int) -> str:
        if n >= 1024 * 1024 * 1024:
            return f"{n / 1024 / 1024 / 1024:.2f} GB"
        if n >= 1024 * 1024:
            return f"{n / 1024 / 1024:.2f} MB"
        if n >= 1024:
            return f"{n / 1024:.2f} KB"
        return f"{n} B"

    log(
        f"任务完成：发现 {total.discovered_count} 个，上传 {total.updated_count} 个，"
        f"跳过 {total.skipped_count} 个，失败 {total.failed_count} 个；"
        f"下载 {fmt_size(total.downloaded_bytes)}，"
        f"上传 {fmt_size(total.uploaded_bytes)}，"
        f"转换 PDF {total.converted_count} 份"
    )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(
                "## Canvas 同步摘要\n\n"
                f"- 课程：{len(parsed)}\n"
                f"- 发现文件：{total.discovered_count}\n"
                f"- 上传文件：{total.updated_count}\n"
                f"- 跳过文件：{total.skipped_count}\n"
                f"- 失败文件/课程：{total.failed_count}\n"
                f"- 下载流量：{fmt_size(total.downloaded_bytes)}\n"
                f"- 上传流量：{fmt_size(total.uploaded_bytes)}\n"
                f"- 转换 PDF：{total.converted_count}\n"
            )

    if total.failed_count:
        sys.exit(2)
    if total.updated:
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
