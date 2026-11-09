"""The Patch Loop: the small steps it is built from (config, validate, snapshot, apply, parse)."""
import os

import yaml

from p1 import index


def load_validation_command():
    """The Validation Command from the Target Project's ioc.config.yml."""
    with open(os.path.join(index.TARGET_DIR, "ioc.config.yml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict) or not isinstance(config.get("validate"), str) or not config["validate"]:
        raise ValueError("ioc.config.yml must contain a 'validate' command")
    return config["validate"]
