import subprocess
from pathlib import Path


def get_converted_pdf_name(source_path: Path) -> str:
    source_ext = source_path.suffix.lower().lstrip(".") or "file"
    return f"{source_path.stem}.from-{source_ext}.pdf"


def convert_to_pdf(ppt_path: Path, out_dir: Path) -> Path:
    try:
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(ppt_path),
            ],
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 soffice，无法执行 PPT 转 PDF") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("soffice 转换失败") from exc

    generated_path = out_dir / (ppt_path.stem + ".pdf")
    if not generated_path.exists():
        raise RuntimeError("转换输出不存在")

    final_path = out_dir / get_converted_pdf_name(ppt_path)
    generated_path.replace(final_path)
    return final_path
