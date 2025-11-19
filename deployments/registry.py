import importlib
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExperimentInfo:
    name: str
    cls: type
    metadata: Dict[str, Any]


class Registry:
    def __init__(self):
        self._experiments: List[ExperimentInfo] = []
        self._scan_mode: Literal["raise", "skip", "replace"] = "raise"

    def get_by_metadata(self, **filters) -> List[ExperimentInfo]:
        return [
            experiment
            for experiment in self._experiments
            if all(experiment.metadata.get(key) == value for key, value in filters.items())
        ]

    def __getitem__(self, name: str) -> ExperimentInfo:
        try:
            return next((info for info in self._experiments if info.name == name))
        except StopIteration as e:
            raise KeyError(f"No experiment for name exists: `{name}`") from e

    def get(self, name: str) -> Optional[ExperimentInfo]:
        try:
            return self[name]
        except KeyError as e:
            return None

    def items(self) -> List[ExperimentInfo]:
        return self._experiments

    def add(self, name: str, cls: type, **metadata: Any) -> None:
        existing = self.get(name)
        if existing:
            if self._scan_mode == "skip":
                logger.debug(f"Skipping already registered experiment: `{name}`")
                return
            elif self._scan_mode == "replace":
                if existing.metadata["module_path"] != metadata["module_path"]:
                    logger.debug(
                        f"Experiment already registered from another module. Experiment: `{name}`\tModule: `{existing.metadata['module_path']}`"
                    )
                logger.debug(f"Removing existing experiment: `{name}`")
                self._experiments.remove(existing)
            elif self._scan_mode == "raise":
                raise ValueError(f"Experiment already registered: `{name}`")
            else:
                raise RuntimeError("Invalid scan mode")
        self._experiments.append(ExperimentInfo(name, cls, metadata))

    def _process_module(self, module_path: str, module_name: str) -> None:
        base_path = Path(__file__).parent
        module_name = (
            Path(module_path).relative_to(base_path).parent.as_posix().replace("/", ".")
            + "."
            + Path(module_path).stem
        ).strip(".")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if not spec:
            raise ValueError(f"Could not load spec for module: `{module_path}`")
        if module_name in sys.modules:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    def scan(self, folder: str, mode: Literal["raise", "skip", "replace"] = "raise") -> None:
        """Scan a directory for experiments.

        Warning: Do not scan a directory with a venv under it.
        Scanning venv will raise errors.
        """
        root_dir = Path(folder).resolve()
        logger.debug(f"Scanning directory for experiments: `{root_dir}`")
        old_mode = self._scan_mode
        self._scan_mode = mode
        try:
            for path in root_dir.rglob("*.py"):
                if path.name.startswith("_"):
                    continue
                if path == Path(__file__):
                    # Reloading this module would cause `registry = Registry()` to execute again.
                    # This would result in multiple registry objects.
                    continue

                module_path = str(path.resolve())
                self._process_module(module_path, path.stem)
        finally:
            self._scan_mode = old_mode


registry = Registry()


def experiment(name, **metadata):
    def decorator(cls):
        metadata["module_path"] = sys.modules[cls.__module__].__file__
        exp_name = name if name is not None else cls.__name__
        registry.add(exp_name, cls, **metadata)
        cls.name = exp_name
        return cls

    return decorator
