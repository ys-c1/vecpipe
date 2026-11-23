"""着色：平面色与线性渐变。"""
from .config import ConfigError


def flat(intensity):
    if not 0.0 <= intensity <= 1.0:
        raise ConfigError("intensity 超出范围")
    return int(255 * intensity)


def gradient(t):
    if not 0.0 <= t <= 1.0:
        raise ConfigError("t 超出范围")
    return int(255 * t)


def apply(image, mode="flat", top=1.0, bottom=0.0):
    if mode not in ("flat", "gradient"):
        raise ConfigError("未知着色模式")
    height = len(image)
    for row in range(height):
        if mode == "flat":
            value = flat(top)
        else:
            t = top + (bottom - top) * (row / max(1, height - 1))
            value = gradient(t)
        for col in range(len(image[0])):
            if image[row][col]:
                image[row][col] = value
    return image
