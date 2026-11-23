"""配置解析与校验。所有字段都有类型与范围，非法值一律抛 ConfigError。"""


class ConfigError(ValueError):
    pass


DEFAULTS = {
    "width": 64,
    "height": 64,
    "scale": 1.0,
    "rotate": 0.0,
    "supersample": 2,
    "shading": "flat",
    "gamma": 1.0,
    "blur": 0,
    "trace": False,
    "output": "out.pgm",
}


def _num(name, value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("%s 必须是数字" % name)
    if value < lo or value > hi:
        raise ConfigError("%s 超出范围 [%s, %s]" % (name, lo, hi))
    return float(value)


def parse(raw):
    cfg = dict(DEFAULTS)
    if raw is None:
        return cfg
    for key, value in raw.items():
        if key not in DEFAULTS:
            raise ConfigError("未知字段 %s" % key)
        cfg[key] = value
    cfg["width"] = int(_num("width", cfg["width"], 1, 4096))
    cfg["height"] = int(_num("height", cfg["height"], 1, 4096))
    cfg["scale"] = _num("scale", cfg["scale"], 1e-6, 100.0)
    cfg["rotate"] = _num("rotate", cfg["rotate"], -6.2832, 6.2832)
    cfg["supersample"] = int(_num("supersample", cfg["supersample"], 1, 8))
    cfg["gamma"] = _num("gamma", cfg["gamma"], 0.1, 10.0)
    cfg["blur"] = int(_num("blur", cfg["blur"], 0, 16))
    if not isinstance(cfg["trace"], bool):
        raise ConfigError("trace 必须是布尔值")
    if cfg["shading"] not in ("flat", "gradient"):
        raise ConfigError("shading 只能是 flat 或 gradient")
    if not isinstance(cfg["output"], str) or not cfg["output"]:
        raise ConfigError("output 必须是非空字符串")
    return cfg
