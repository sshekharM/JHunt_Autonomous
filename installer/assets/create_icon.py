"""
Generate assets/icon.ico — run once to create the icon file.
Uses Pillow if available; otherwise writes a minimal valid 1x1 ICO from raw bytes.
"""
import os
import struct

_HERE = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(_HERE, "icon.ico")


def _create_minimal_ico():
    """
    Build a minimal valid ICO file: two images (16x16 and 32x32),
    both filled with #0078D4 (the jH_ANS brand blue).
    ICO format reference: https://en.wikipedia.org/wiki/ICO_(file_format)
    """
    def _bmp_image(size: int, r: int, g: int, b: int) -> bytes:
        """Return a raw bottom-up 24-bit BMP DIB (no file header) for a solid-colour square."""
        width = height = size
        row_size = (width * 3 + 3) & ~3  # 4-byte aligned row
        pixel_row = bytes([b, g, r]) * width + b"\x00" * (row_size - width * 3)
        pixel_data = pixel_row * height

        info_header = struct.pack(
            "<LLLHHLLLLLL",
            40,          # biSize
            width,       # biWidth
            height * 2,  # biHeight (×2 for ICO: image + mask)
            1,           # biPlanes
            24,          # biBitCount
            0,           # biCompression (BI_RGB)
            len(pixel_data),  # biSizeImage
            0, 0,        # biXPelsPerMeter, biYPelsPerMeter
            0, 0,        # biClrUsed, biClrImportant
        )

        # AND mask: all 0s = fully opaque; rows must be 4-byte aligned
        mask_row_size = ((width + 31) // 32) * 4
        mask_data = b"\x00" * mask_row_size * height

        return info_header + pixel_data + mask_data

    sizes = [16, 32]
    images = [_bmp_image(s, 0x00, 0x78, 0xD4) for s in sizes]

    # ICO header
    num_images = len(images)
    header = struct.pack("<HHH", 0, 1, num_images)  # reserved=0, type=1(ICO), count

    # Directory entries (16 bytes each)
    offset = 6 + num_images * 16
    dir_entries = b""
    for i, size in enumerate(sizes):
        img_size = len(images[i])
        entry = struct.pack(
            "<BBBBHHLL",
            size,     # width  (0 means 256)
            size,     # height (0 means 256)
            0,        # color count (0 = no palette)
            0,        # reserved
            1,        # planes
            24,       # bit count
            img_size, # size of image data
            offset,   # offset to image data
        )
        dir_entries += entry
        offset += img_size

    ico_bytes = header + dir_entries + b"".join(images)
    return ico_bytes


def create_icon():
    try:
        from PIL import Image, ImageDraw
        icons = []
        for size in [16, 32, 48, 64, 128, 256]:
            img = Image.new("RGBA", (size, size), (0, 120, 212, 255))
            draw = ImageDraw.Draw(img)
            # Simple "J" letter
            margin = size // 6
            font_size = int(size * 0.6)
            draw.text(
                (size // 2, size // 2),
                "J",
                fill=(255, 255, 255, 255),
                anchor="mm"
            )
            icons.append(img)
        icons[0].save(ICO_PATH, format="ICO", sizes=[(i.width, i.height) for i in icons],
                      append_images=icons[1:])
        print(f"Created icon (Pillow) at {ICO_PATH}")
    except ImportError:
        ico_bytes = _create_minimal_ico()
        with open(ICO_PATH, "wb") as f:
            f.write(ico_bytes)
        print(f"Created minimal icon at {ICO_PATH} ({len(ico_bytes)} bytes)")


if __name__ == "__main__":
    create_icon()
