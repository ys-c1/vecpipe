"""光栅化：超采样填充与 PGM 输出。"""
from .geom import point_in_poly


def new_image(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("画幅必须为正")
    return [[0] * width for _ in range(height)]


def bounds(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def fill(image, polygons, supersample=1):
    if supersample < 1:
        raise ValueError("supersample 必须为正")
    height = len(image)
    width = len(image[0]) if height else 0
    for poly in polygons:
        if len(poly) < 3:
            raise ValueError("多边形至少三个顶点")
    xs = [p[0] for poly in polygons for p in poly]
    ys = [p[1] for poly in polygons for p in poly]
    if not xs:
        return image
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0
    for row in range(height):
        for col in range(width):
            hit = 0
            for sj in range(supersample):
                for si in range(supersample):
                    px = minx + (col + (si + 0.5) / supersample) * spanx / width
                    py = miny + (row + (sj + 0.5) / supersample) * spany / height
                    for poly in polygons:
                        if point_in_poly(poly, px, py):
                            hit += 1
                            break
            image[row][col] = int(255 * hit / (supersample * supersample))
    return image


def save_pgm(path, image):
    height = len(image)
    width = len(image[0]) if height else 0
    if width == 0 or height == 0:
        raise ValueError("空图不能导出")
    with open(path, "wb") as fh:
        fh.write(("P5\n%d %d\n255\n" % (width, height)).encode("ascii"))
        for row in image:
            fh.write(bytes(row))


def count_on(image, threshold=128):
    return sum(1 for row in image for v in row if v >= threshold)
