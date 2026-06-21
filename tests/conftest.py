"""Allow pure modules to load without importing Home Assistant integration setup."""

import importlib.util
import sys
import types
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "custom_components" / "bermuda_tuner"
package = types.ModuleType("custom_components.bermuda_tuner")
package.__path__ = [str(PACKAGE)]
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
sys.modules["custom_components.bermuda_tuner"] = package

spec = importlib.util.spec_from_file_location(
    "custom_components.bermuda_tuner.analyzer", PACKAGE / "analyzer.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
