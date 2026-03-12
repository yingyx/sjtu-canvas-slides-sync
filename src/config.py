import os
from dataclasses import dataclass

from logger import log


@dataclass(frozen=True)
class AppConfig:
    canvas_base_url: str
    canvas_token: str
    smh_base_url: str
    smh_user_token: str
    smh_jaauth_cookie: str
    save_root: str
    convert_ppt: bool
    max_file_size_mb: int
    file_extensions: set[str]
    convert_extensions: set[str]

    @property
    def jaauth_cookie(self) -> str:
        return self.smh_jaauth_cookie


def _parse_bool_env(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in ("1", "true", "yes", "on")


def _parse_int_env(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        value = int(raw)
    except ValueError:
        log(f"环境变量 {name} 非法（{raw}），将使用默认值 {default}")
        value = int(default)

    if value < 0:
        log(f"环境变量 {name} 小于 0，将按 0 处理")
        return 0
    return value


def load_config() -> AppConfig:
    return AppConfig(
        canvas_base_url="https://oc.sjtu.edu.cn",
        canvas_token=os.environ.get("CANVAS_TOKEN", ""),
        smh_base_url="https://pan.sjtu.edu.cn",
        smh_user_token=os.environ.get("SMH_USER_TOKEN", ""),
        smh_jaauth_cookie=os.environ.get("JAAuthCookie", ""),
        save_root=os.environ.get("SAVE_ROOT", "Canvas Files"),
        convert_ppt=_parse_bool_env("CONVERT_PPT_TO_PDF", "false"),
        max_file_size_mb=_parse_int_env("MAX_FILE_SIZE", "0"),
        file_extensions=set(
            s.strip().lower()
            for s in os.environ.get("FILE_EXTENSIONS", ".ppt,.pptx,.pdf").split(",")
            if s.strip()
        ),
        convert_extensions=set(
            s.strip().lower()
            for s in os.environ.get("CONVERT_EXTENSIONS", ".ppt,.pptx").split(",")
            if s.strip()
        ),
    )


def make_canvas_headers(canvas_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {canvas_token}"}
