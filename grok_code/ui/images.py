"""Image handling for grokCode"""

import base64
import os
import subprocess
from pathlib import Path


def get_clipboard_image() -> tuple[str, str] | None:
    """
    Get image from clipboard (macOS).
    Returns (base64_data, media_type) or None if no image.
    """
    try:
        # Check if clipboard has image data (macOS)
        result = subprocess.run(
            ["osascript", "-e", "clipboard info"],
            capture_output=True,
            text=True,
        )

        if "«class PNGf»" not in result.stdout and "TIFF" not in result.stdout:
            return None

        # Save clipboard image to temp file
        temp_path = "/tmp/grok_clipboard_image.png"
        subprocess.run(
            [
                "osascript",
                "-e",
                f"""
                set theFile to (open for access POSIX file "{temp_path}" with write permission)
                try
                    set eof theFile to 0
                    write (the clipboard as «class PNGf») to theFile
                    close access theFile
                on error
                    close access theFile
                end try
            """,
            ],
            capture_output=True,
        )

        if os.path.exists(temp_path):
            with open(temp_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(temp_path)
            return data, "image/png"

    except Exception:
        pass

    return None


def load_image_file(path: str) -> tuple[str, str] | None:
    """
    Load an image file and return base64 data.
    Returns (base64_data, media_type) or None.
    """
    path = Path(path).expanduser()

    if not path.exists():
        return None

    # Determine media type
    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    media_type = media_types.get(suffix)
    if not media_type:
        return None

    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return data, media_type
    except Exception:
        return None


def is_image_path(text: str) -> bool:
    """Check if text looks like an image path"""
    text = text.strip()
    if not text:
        return False

    path = Path(text).expanduser()
    if path.exists() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return True

    return False
