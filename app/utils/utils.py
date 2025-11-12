import base64
import httpx

async def download_and_base64(url: str, timeout: int = 30) -> str:
    """
    Download file from URL, return base64-encoded bytes string.
    Uses httpx.AsyncClient.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
