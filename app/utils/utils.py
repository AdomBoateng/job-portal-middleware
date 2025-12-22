import base64
import os
import asyncio
from typing import Optional
from urllib.parse import urlparse

import httpx


async def _http_download(url: str, timeout: int, max_retries: int = 3, backoff_factor: float = 0.5) -> bytes:
    """Download bytes over HTTP(S) with a simple retry/backoff loop."""
    attempt = 0
    last_exc: Optional[Exception] = None
    # Use an explicit httpx.Timeout so it applies to the whole request
    timeout_cfg = httpx.Timeout(timeout)
    async with httpx.AsyncClient(timeout=timeout_cfg) as client:
        while attempt < max_retries:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                last_exc = e
                attempt += 1
                if attempt >= max_retries:
                    break
                # exponential backoff
                await asyncio.sleep(backoff_factor * (2 ** (attempt - 1)))
    # re-raise the last exception for caller handling
    raise last_exc


def _s3_download_sync(bucket: str, key: str) -> bytes:
    """Synchronous S3 download helper using boto3 (called in a thread)."""
    try:
        import boto3
    except Exception as e:  # pragma: no cover - missing boto3
        raise RuntimeError("boto3 is required to download from s3:// URLs") from e

    client = boto3.client("s3")
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()


async def download_and_base64(url: str, timeout: int = 30) -> str:
    """
    Download file from URL and return base64-encoded string.

    Behavior:
    - s3://bucket/key -> use boto3 to fetch object (runs sync boto3 in threadpool)
    - file:///path or /absolute/path -> read local file
    - http(s):// -> download with httpx and retries

    Raises helpful RuntimeError on failures so callers can log/handle uniformly.
    """
    if not url:
        raise ValueError("empty URL provided to download_and_base64")

    parsed = urlparse(url)

    try:
        if parsed.scheme == "s3":
            # s3://bucket/key
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
            if not bucket or not key:
                raise ValueError("invalid s3 url")
            # boto3 is synchronous; run in thread to avoid blocking event loop
            data = await asyncio.to_thread(_s3_download_sync, bucket, key)

        elif parsed.scheme == "file" or (parsed.scheme == "" and os.path.isabs(url)):
            # local file path, support both file:/// and direct absolute paths
            path = parsed.path if parsed.scheme == "file" else url
            if not os.path.exists(path):
                raise FileNotFoundError(f"local file not found: {path}")
            # read file in thread
            def _read_file(p: str) -> bytes:
                with open(p, "rb") as fh:
                    return fh.read()

            data = await asyncio.to_thread(_read_file, path)

        else:
            # treat as HTTP(S) (or other resolvable URL) and attempt download with retries
            # Allow plain URLs without scheme to be handled by httpx as well
            download_url = url if parsed.scheme else f"http://{url}"
            data = await _http_download(download_url, timeout)

        return base64.b64encode(data).decode("utf-8")

    except Exception as e:  # give a clearer outer error type for callers
        raise RuntimeError(str(e)) from e