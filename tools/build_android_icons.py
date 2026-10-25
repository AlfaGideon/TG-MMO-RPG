"""Генерирует Android-иконки APK из брендового логотипа 1024x1024.

Источник — admin/static/branding/start_ru.png (тот же баннер, что бот
показывает в Telegram при /start). Никаких кропов: картинка используется
целиком, система сама применит маску (круг/сквиркл) к адаптивной иконке.

Запуск:  python3 tools/build_android_icons.py
Требуется Pillow:  pip install Pillow
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "admin/static/branding/start_ru.png")
RES = os.path.join(ROOT, "android/app/src/main/res")

# Плотности -> размер legacy-иконки в пикселях
LEGACY_SIZES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}
# Холст адаптивной иконки 108dp в плотности xxxhdpi (4x)
ADAPTIVE_BG_SIZE = 432


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    if src.size != (1024, 1024):
        raise SystemExit(f"Ожидается логотип 1024x1024, получено {src.size}")

    for density, px in LEGACY_SIZES.items():
        out_dir = os.path.join(RES, f"mipmap-{density}")
        os.makedirs(out_dir, exist_ok=True)
        icon = src.resize((px, px), Image.LANCZOS)
        icon.save(os.path.join(out_dir, "ic_launcher.png"), optimize=True)
        icon.save(os.path.join(out_dir, "ic_launcher_round.png"), optimize=True)

    bg = src.resize((ADAPTIVE_BG_SIZE, ADAPTIVE_BG_SIZE), Image.LANCZOS)
    bg.save(os.path.join(RES, "mipmap-xxxhdpi/ic_launcher_background.png"),
            optimize=True)
    print("OK: иконки сгенерированы из", os.path.relpath(SRC, ROOT))


if __name__ == "__main__":
    main()
