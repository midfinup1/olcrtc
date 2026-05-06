from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
SRC = BASE_DIR / "icon.png"
OUT_ICO = BASE_DIR / "icon.ico"

img = Image.open(SRC).convert("RGBA")

sizes = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]

img.save(
    OUT_ICO,
    format="ICO",
    sizes=sizes,
)

print(f"Created: {OUT_ICO}")