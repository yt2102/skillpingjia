"""
jishufangan 图片处理工具（v3.1 新增）

职责：图片预处理全链路，供 add_image 使用前调用。
目标显示尺寸：A4 页面四分之一（约 10.5cm 宽 × 14.85cm 高，面积 1/4）。

函数：
    fetch_image(src, dest=None)        URL/本地路径 → 本地文件
    prepare_image(src, dest=None, ...) 格式归一化 + 缩放 + 白底 → 可插入图片
    verify_image(path)                 有效性检查（可解码/尺寸/体积）
    verify_docx_images(docx_path)      三要素闭环检查（media/rels/blip）

设计原则：
    - 确定性处理，失败明确报错不静默
    - 只依赖 Pillow（requirements.txt 已声明）
    - 不绑定任何平台/模型/绝对路径
"""
import re
import sys
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional

# 目标尺寸（A4 四分之一：21cm/2 × 29.7cm/2）
TARGET_WIDTH_CM = 10.5
TARGET_HEIGHT_CM = 14.85
# 像素上限（约 250 DPI，Word 显示清晰且体积可控）
MAX_WIDTH_PX = 1024
MAX_HEIGHT_PX = 1400
# 支持输入格式
SUPPORTED_INPUT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff")
OUTPUT_FORMAT = "PNG"  # 统一转 PNG（Word 兼容 + 透明铺白底）


def fetch_image(src: str, dest: Optional[str] = None) -> str:
    """把 URL 或本地路径归一化为本地图片文件路径。

    Args:
        src: http(s):// URL 或本地路径
        dest: 目标路径（可选，默认 <src 所在目录>/<文件名>）

    Returns:
        本地文件绝对路径

    Raises:
        ValueError: src 不是 URL 也不是存在的本地文件
        RuntimeError: URL 下载失败
    """
    src_s = str(src)
    if src_s.startswith(("http://", "https://")):
        if dest is None:
            fname = src_s.split("/")[-1].split("?")[0]
            dest = str(Path("/tmp") / fname)
        dest_p = Path(dest)
        dest_p.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            src_s, headers={"User-Agent": "Mozilla/5.0 (jishufangan image fetch)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
        except Exception as e:
            raise RuntimeError(f"图片下载失败 {src_s}: {e}") from e
        if not data:
            raise RuntimeError(f"图片下载为空 {src_s}")
        dest_p.write_bytes(data)
        return str(dest_p.resolve())
    else:
        p = Path(src_s)
        if not p.exists():
            raise ValueError(f"图片路径不存在: {src_s}")
        return str(p.resolve())


def _require_pillow():
    """懒加载 Pillow，缺失时给出明确安装指引而非裸 ImportError。"""
    try:
        from PIL import Image
        return Image
    except ImportError as e:
        raise RuntimeError(
            "缺少 Pillow 依赖。请安装：pip install Pillow（或 pip3 install Pillow）"
        ) from e


def prepare_image(
    src: str,
    dest: Optional[str] = None,
    max_width_px: int = MAX_WIDTH_PX,
    max_height_px: int = MAX_HEIGHT_PX,
    bg_white: bool = True,
) -> str:
    """图片预处理：格式归一化 + 缩放 + 透明铺白底。

    Args:
        src: URL 或本地路径
        dest: 输出路径（默认 <src 目录>/<stem>_prepared.png）
        max_width_px: 最大宽度像素（默认 1024 ≈ A4 1/4 @ 250dpi）
        max_height_px: 最大高度像素（默认 1400）
        bg_white: 透明背景铺白底（Word 兼容）

    Returns:
        处理后的 PNG 绝对路径

    Raises:
        ValueError: 格式不支持 / 无法解码
    """
    Image = _require_pillow()

    src_path = fetch_image(src)
    ext = Path(src_path).suffix.lower()
    if ext not in SUPPORTED_INPUT:
        raise ValueError(f"不支持的图片格式: {ext}（支持 {SUPPORTED_INPUT}）")

    try:
        img = Image.open(src_path)
        img.load()
    except Exception as e:
        raise ValueError(f"图片无法解码 {src_path}: {e}") from e

    # 透明背景铺白底（RGBA/LA/P 带透明 → RGB 白底）
    if bg_white and (img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    # 等比缩放（只缩小不放大）
    w, h = img.size
    ratio = min(1.0, max_width_px / w, max_height_px / h)
    if ratio < 1.0:
        img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)

    # 输出
    if dest is None:
        src_p = Path(src_path)
        dest = str(src_p.with_name(src_p.stem + "_prepared.png"))
    dest_p = Path(dest)
    dest_p.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest_p, format=OUTPUT_FORMAT, optimize=True)
    return str(dest_p.resolve())


def verify_image(path: str) -> dict:
    """图片有效性检查。

    Returns:
        {"ok": bool, "width": int, "height": int, "bytes": int, "error": str|None}
    """
    Image = _require_pillow()

    p = Path(path)
    result = {"ok": False, "width": 0, "height": 0, "bytes": 0, "error": None}
    if not p.exists():
        result["error"] = f"文件不存在: {path}"
        return result
    result["bytes"] = p.stat().st_size
    try:
        with Image.open(p) as img:
            result["width"], result["height"] = img.size
        result["ok"] = True
    except Exception as e:
        result["error"] = f"无法解码: {e}"
    return result


def verify_docx_images(docx_path: str) -> dict:
    """验证 docx 内图片三要素闭环（media 文件 / rels 关系 / document 引用）。

    Returns:
        {"ok": bool, "media_count": int, "blip_refs": int, "broken": [str], "detail": str}
    """
    p = Path(docx_path)
    if not p.exists():
        return {"ok": False, "media_count": 0, "blip_refs": 0, "broken": [f"文件不存在 {docx_path}"], "detail": ""}
    try:
        with zipfile.ZipFile(p, "r") as z:
            names = z.namelist()
            media = [n for n in names if n.startswith("word/media/")]
            rels_name = "word/_rels/document.xml.rels"
            doc_name = "word/document.xml"
            rels = z.read(rels_name).decode("utf-8", errors="ignore") if rels_name in names else ""
            doc_xml = z.read(doc_name).decode("utf-8", errors="ignore") if doc_name in names else ""
    except Exception as e:
        return {"ok": False, "media_count": 0, "blip_refs": 0, "broken": [f"docx 读取失败: {e}"], "detail": ""}

    blip_refs = re.findall(r'r:embed="(rId\d+)"', doc_xml)
    broken = []
    # 每个 blip 引用必须在 rels 中存在，且 rels 指向 media 文件
    rels_targets = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    for rid in blip_refs:
        if rid not in rels_targets:
            broken.append(f"{rid} 不在 rels 中")
        elif not rels_targets[rid].startswith("media/"):
            broken.append(f"{rid} 指向非 media: {rels_targets[rid]}")

    ok = len(media) > 0 and len(blip_refs) > 0 and not broken
    return {
        "ok": ok,
        "media_count": len(media),
        "blip_refs": len(blip_refs),
        "broken": broken,
        "detail": f"media={len(media)} 个, blip 引用={len(blip_refs)} 处",
    }


def main():
    """CLI：python3 image_tools.py <src> [--dest <path>]"""
    import argparse

    parser = argparse.ArgumentParser(description="jishufangan 图片预处理")
    parser.add_argument("src", help="URL 或本地图片路径")
    parser.add_argument("--dest", help="输出路径（默认同目录 _prepared.png）")
    parser.add_argument("--max-width", type=int, default=MAX_WIDTH_PX)
    parser.add_argument("--max-height", type=int, default=MAX_HEIGHT_PX)
    parser.add_argument("--verify-only", action="store_true", help="只验证不处理")
    args = parser.parse_args()

    if args.verify_only:
        r = verify_image(args.src)
        print(r)
        sys.exit(0 if r["ok"] else 1)

    out = prepare_image(args.src, dest=args.dest, max_width_px=args.max_width, max_height_px=args.max_height)
    v = verify_image(out)
    print(f"预处理完成: {out}")
    print(f"尺寸: {v['width']}x{v['height']}px, {v['bytes']} 字节")
    if not v["ok"]:
        print(f"警告: {v['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
