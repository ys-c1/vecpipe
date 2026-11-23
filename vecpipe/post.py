"""后处理：伽马、反相、盒式模糊。"""
from .config import ConfigError


def gamma(image, value):
    if not 0.1 <= value <= 10.0:
        raise ConfigError("gamma 超出范围")
    table = [int(255 * ((i / 255.0) ** (1.0 / value))) for i in range(256)]
    return [[table[v] for v in row] for row in image]


def invert(image):
    return [[255 - v for v in row] for row in image]


def blur(image, radius):
    if radius < 0:
        raise ConfigError("blur 不能为负")
    if radius == 0:
        return [row[:] for row in image]
    height = len(image)
    width = len(image[0])
    out = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            total, count = 0, 0
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width:
                        total += image[ny][nx]
                        count += 1
            out[y][x] = total // count
    return out
