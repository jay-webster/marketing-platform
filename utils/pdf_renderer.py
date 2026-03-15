"""PDF rendering — Jinja2 HTML templates rendered to PDF bytes via WeasyPrint.

Design:
  - Images are fetched from GCS as bytes and base64-encoded as data URIs before
    Jinja2 template rendering. WeasyPrint never makes network requests.
  - HTML string is rendered to bytes via WeasyPrint in asyncio.to_thread (CPU-bound,
    blocking call). No temp files are written to the container filesystem.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "pdf_templates"

_ALLOWED_TEMPLATES = {"one_pager", "campaign_brief"}


async def render_pdf(
    template_name: str,
    content: dict[str, Any],
    images: list[dict[str, str]],
    bucket_name: str,
) -> bytes:
    """Render a Jinja2 HTML template to PDF bytes.

    Args:
        template_name: Template key — "one_pager" or "campaign_brief".
        content: Dict with "title" and "sections" keys from generate_content().
        images: List of {"gcs_object_name": str, "display_title": str}.
        bucket_name: GCS bucket containing the image objects.

    Returns:
        Raw PDF bytes.
    """
    if template_name not in _ALLOWED_TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}")

    # Fetch images from GCS and convert to base64 data URIs
    image_data = await _prepare_images(images, bucket_name)

    # Render HTML synchronously (Jinja2 is fast, no I/O)
    html_string = _render_html(template_name, content, image_data)

    # WeasyPrint is CPU-bound and blocking — run in thread pool
    pdf_bytes = await asyncio.to_thread(_weasyprint_render, html_string)
    return pdf_bytes


async def _prepare_images(
    images: list[dict[str, str]],
    bucket_name: str,
) -> list[dict[str, str]]:
    """Download images from GCS and return list with base64 data URIs."""
    from utils.gcs import download_stream_from_gcs

    result = []
    for img in images:
        try:
            buf = await download_stream_from_gcs(bucket_name, img["gcs_object_name"])
            raw = buf.read()
            content_type = _guess_content_type(img["gcs_object_name"])
            b64 = base64.b64encode(raw).decode("ascii")
            result.append({
                "data_uri": f"data:{content_type};base64,{b64}",
                "display_title": img.get("display_title", ""),
            })
        except Exception:
            logger.warning("Skipping image %s — failed to fetch from GCS", img["gcs_object_name"])
    return result


def _guess_content_type(object_name: str) -> str:
    ext = os.path.splitext(object_name)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _render_html(
    template_name: str,
    content: dict[str, Any],
    image_data: list[dict[str, str]],
) -> str:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
    )
    template = env.get_template(f"{template_name}.html")
    return template.render(
        title=content.get("title", "Document"),
        tagline=content.get("tagline", ""),
        sections=content.get("sections", []),
        images=image_data,
    )


def _weasyprint_render(html_string: str) -> bytes:
    """Synchronous WeasyPrint render — call only from asyncio.to_thread."""
    from weasyprint import HTML
    return HTML(string=html_string, base_url=str(_TEMPLATE_DIR)).write_pdf()
