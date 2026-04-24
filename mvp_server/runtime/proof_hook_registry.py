from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ProofModuleSpec:
    module_id: str
    module_path: str
    enabled: bool = True


class ProofHookRegistry:
    """Tracks active module specs for hook capture.

    Phase 1 only supports one enabled module.
    """

    def __init__(self, specs: List[ProofModuleSpec]) -> None:
        enabled_specs = [spec for spec in specs if spec.enabled]
        if not enabled_specs:
            raise ValueError("at least one enabled proof module is required")
        if len(enabled_specs) > 1:
            raise ValueError("phase 1 supports only one enabled proof module")
        self._specs_by_id: Dict[str, ProofModuleSpec] = {
            spec.module_id: spec for spec in specs
        }
        self._active_module_id = enabled_specs[0].module_id

    @classmethod
    def single_module(cls, module_path: str) -> "ProofHookRegistry":
        return cls([ProofModuleSpec(module_id=module_path, module_path=module_path)])

    def active_spec(self) -> ProofModuleSpec:
        return self._specs_by_id[self._active_module_id]

