import os
import io
import time
import random
import datetime
import requests
from PIL import Image
from atproto import Client


# ---------------- CONFIG ---------------- #

common_resolutions = [
    (1920, 1080),
    (1280, 720),
    (1600, 900),
    (2560, 1440),

    (800, 800),
    (1080, 1080),
    (1200, 1200),

    (1024, 768),
    (800, 600),
    (1440, 1080),

    (1080, 720),
    (1200, 800),

    (1080, 1920),
    (720, 1280),

    (600, 800),
    (768, 1024),

    (1080, 1350)
]

PICSUM_BASE = "https://picsum.photos"

MAX_BYTES = 1_000_000
TARGET_MAX_BYTES = 950_000


# ---------------- IMAGE DOWNLOAD ---------------- #

def download_random_picsum(width: int, height: int, retries: int = 3):
    url = f"{PICSUM_BASE}/{width}/{height}"

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return resp.content, resp.url

        except requests.RequestException as e:
            if attempt == retries:
                raise RuntimeError(f"Failed to download image: {e}")
            
            # Exponential backoff: waits 2s, 4s, 6s...
            print(f"Download attempt {attempt + 1} failed: {e}. Retrying...")
            time.sleep(2 * (attempt + 1))


# ---------------- IMAGE PROCESSING ---------------- #

def compress_image(img_bytes: bytes, width: int, height: int) -> bytes:
    img = Image.open(io.BytesIO(img_bytes))
    img = img.convert("RGB")

    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    qualities = [95, 90, 85, 80, 75, 70, 65, 60, 55]

    for q in qualities:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        data = buf.getvalue()
        if len(data) <= TARGET_MAX_BYTES:
            return data

    # fallback: downscale
    scale = 0.9
    for _ in range(5):
        new_size = (int(width * scale), int(height * scale))
        resized = img.resize(new_size, Image.LANCZOS)

        for q in [80, 70, 60, 50]:
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=q, optimize=True)
            data = buf.getvalue()
            if len(data) <= TARGET_MAX_BYTES:
                return data

        scale *= 0.9

    raise RuntimeError("Could not compress image under limit")


# ---------------- BLUESKY POSTING ---------------- #

def post_to_bluesky(client: Client, text: str, image_bytes: bytes, alt_text: str):
    # Using client.send_image is the safest high-level way to post text + an image 
    # without running into complex dictionary validation issues in the atproto SDK.
    client.send_image(
        text=text,
        image=image_bytes,
        image_alt=alt_text
    )


# ---------------- MAIN ---------------- #

def main():
    handle = os.environ.get("BSKY_HANDLE", "").strip()
    app_password = os.environ.get("BSKY_APP_PASSWORD", "").strip()
    pds = os.environ.get("BSKY_PDS", "").strip()

    if not handle or not app_password:
        raise RuntimeError("Missing BSKY_HANDLE or BSKY_APP_PASSWORD")

    width, height = random.choice(common_resolutions)

    raw_img, source_url = download_random_picsum(width, height)
    final_img = compress_image(raw_img, width, height)

    if len(final_img) > MAX_BYTES:
        raise RuntimeError("Image still too large after compression")

    client = Client(pds) if pds else Client()
    client.login(handle, app_password)

    date = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

    text = f"Daily random image {date}\n{width}x{height}\nSource: {source_url}"
    alt = f"Random image at {width} by {height} resolution."

    post_to_bluesky(client, text, final_img, alt)

    print("Posted successfully:", width, height, len(final_img), "bytes")


if __name__ == "__main__":
    main()