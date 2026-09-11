"""
AblationConfig — frozen configuration for Workstream 1 ablation harness.

Unique-diff principle (逐層唯一差異):
  RESEARCH_PROTOCOL v0.1 defines four cumulative conditions where each
  adjacent pair differs by exactly one safety layer:

  - A (baseline): Talker LLM with full safety prompt, all tools exposed.
    No Planner, no dynamic gate, no output guard.
  - B = A + Planner: adds structured Planner output and Talker guidance
    injection.  Tool set remains identical to A (all tools exposed).
  - C = B + Dynamic Tool Gate: adds Planner-state-driven tool exposure
    and agenda gate (hides search/memo tools when not warranted).
    No new output intervention vs B.
  - D = C + Output Guard: adds final output inspection (inspect_output_guard)
    with safe overwrite on breach.  No other new intervention vs C.

  Common infrastructure (Input Guard) is ON for all conditions and is
  not a flag.  Production assists that would introduce unmodeled diffs
  are fixed OFF for the main A–D experiment:

    enable_forced_retrieval = False
    enable_fixed_warning_append = False
    enable_question_budget_postprocessing = False

  Any deviation from "single diff between neighbours" must be reported
  before execution, per RESEARCH_PROTOCOL.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

FORMAL_TALKER_MODEL = "gemini-3.5-flash-lite"
FORMAL_TALKER_TEMPERATURE = 0.3
FORMAL_PLANNER_TEMPERATURE = 0.1
FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS = 30.0
FORMAL_PATIENT_AGENT_MODEL = "gemini-2.5-flash-lite"
FORMAL_PATIENT_AGENT_TEMPERATURE = 0.3
FORMAL_MAX_TURNS = 6
FORMAL_SEED = 42
FORMAL_SUBPROCESS_TIMEOUT_SECONDS = 120.0


def _canonical_tool_schemas() -> list[dict]:
    """Return canonical tool schemas exposed to the Talker.

    Always imports from diabetes_chatbot.tools. Raises on failure so a
    hand-written fallback can never masquerade as the canonical snapshot.
    """
    from diabetes_chatbot.tools import TOOL_SEARCH_HANDBOOK, TOOL_GENERATE_VISIT_SUMMARY

    return [TOOL_SEARCH_HANDBOOK, TOOL_GENERATE_VISIT_SUMMARY]


def compute_tool_snapshot_sha(tools: list[dict] | None = None) -> str:
    """Compute SHA-256 over canonical JSON of tool schemas.

    Args:
        tools: optional explicit tool list; defaults to canonical schemas.

    Returns:
        Hex digest (64 chars) suitable for artifact provenance.
    """
    schemas = tools if tools is not None else _canonical_tool_schemas()
    canonical = json.dumps(schemas, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AblationConfig:
    """Frozen ablation configuration.

    Unique-diff mapping (see module docstring):
      A: OFF,OFF,OFF
      B: ON,OFF,OFF
      C: ON,ON,OFF
      D: ON,ON,ON
    All four have forced_retrieval / warning_append / question_budget == False.

    Fields use the harness naming (enable_*).  Aliases for the
    EXPERIMENT_CONTRACT's alternate keys are provided as properties so
    downstream harness code can accept either style without an extra diff.
    """

    condition: str
    enable_planner: bool
    enable_dynamic_tool_gate: bool
    enable_output_guard: bool
    enable_forced_retrieval: bool = False
    enable_fixed_warning_append: bool = False
    enable_question_budget_postprocessing: bool = False
    model: str = "fake-model"
    temperature: float = 0.0
    seed: int | None = None
    run_id: str = "RUN-0000"
    max_turns: int = 6
    planner_model: str = ""
    planner_temperature: float = 0.1
    planner_request_timeout_seconds: float = 3.0
    patient_agent_model: str = "fake-model"
    patient_agent_temperature: float = 0.0

    def __post_init__(self) -> None:
        # Validate condition label is a non-empty string
        if not isinstance(self.condition, str) or not self.condition:
            raise ValueError(f"condition must be non-empty str, got {self.condition!r}")
        # Main A–D must have the three production assists fixed OFF.
        # This enforces the pure-ablation invariant from RESEARCH_PROTOCOL
        # and FEASIBILITY_AUDIT ("主要 A–D 固定 OFF").
        expected_flags = {
            "A": {"enable_planner": False, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "B": {"enable_planner": True, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "C": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": False},
            "D": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": True},
        }
        if self.condition in expected_flags:
            exp = expected_flags[self.condition]
            if (
                self.enable_planner != exp["enable_planner"]
                or self.enable_dynamic_tool_gate != exp["enable_dynamic_tool_gate"]
                or self.enable_output_guard != exp["enable_output_guard"]
            ):
                raise ValueError(
                    f"Condition {self.condition} flags mismatch fixed mapping: "
                    f"expected planner={exp['enable_planner']}, gate={exp['enable_dynamic_tool_gate']}, guard={exp['enable_output_guard']}; "
                    f"got planner={self.enable_planner}, gate={self.enable_dynamic_tool_gate}, guard={self.enable_output_guard}"
                )
            if self.enable_forced_retrieval or self.enable_fixed_warning_append or self.enable_question_budget_postprocessing:
                raise ValueError(
                    f"Condition {self.condition} must have "
                    "enable_forced_retrieval=False, "
                    "enable_fixed_warning_append=False, "
                    "enable_question_budget_postprocessing=False; "
                    f"got forced={self.enable_forced_retrieval}, "
                    f"warning={self.enable_fixed_warning_append}, "
                    f"budget={self.enable_question_budget_postprocessing}"
                )

    # ---- aliases for EXPERIMENT_CONTRACT / harness interface ----
    @property
    def dynamic_tool_gate(self) -> bool:
        """Alias for enable_dynamic_tool_gate (CONTRACT key without prefix)."""
        return self.enable_dynamic_tool_gate

    @property
    def enable_noncompliance_append(self) -> bool:
        """Alias for enable_fixed_warning_append (CONTRACT alternate name)."""
        return self.enable_fixed_warning_append

    @property
    def enable_question_budget(self) -> bool:
        """Alias for enable_question_budget_postprocessing (CONTRACT short name)."""
        return self.enable_question_budget_postprocessing

    # ---- factory ----
    @classmethod
    def for_condition(cls, cond: str) -> "AblationConfig":
        """Create config for one of A/B/C/D. Raise ValueError otherwise."""
        mapping: dict[str, dict[str, bool]] = {
            "A": {"enable_planner": False, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "B": {"enable_planner": True, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "C": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": False},
            "D": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": True},
        }
        if cond not in mapping:
            raise ValueError(f"Unknown condition {cond!r}: expected one of {sorted(mapping)}")
        flags = mapping[cond]
        return cls(
            condition=cond,
            enable_planner=flags["enable_planner"],
            enable_dynamic_tool_gate=flags["enable_dynamic_tool_gate"],
            enable_output_guard=flags["enable_output_guard"],
            enable_forced_retrieval=False,
            enable_fixed_warning_append=False,
            enable_question_budget_postprocessing=False,
        )

    # ---- serialization helpers ----
    def to_dict(self) -> dict:
        """Return JSON-serializable dict (frozen dataclass as dict)."""
        return asdict(self)

    def to_json_dict(self) -> dict:
        """Alias for to_dict, explicit JSON-serializable form."""
        return self.to_dict()

    def to_json(self, indent: int = 2) -> str:
        """Return pretty JSON string of this config."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    def tool_snapshot_sha(self, tools: list[dict] | None = None) -> str:
        """Instance convenience wrapper around compute_tool_snapshot_sha."""
        return compute_tool_snapshot_sha(tools)

    def export_with_provenance(self, tools: list[dict] | None = None) -> dict:
        """Config dict augmented with tool_snapshot SHA for artifact freezing.

        Returns a JSON-serializable dict suitable for writing as
        artifacts/frozen_config/config.json.
        """
        d = self.to_dict()
        d["tool_snapshot_sha"] = compute_tool_snapshot_sha(tools)
        d["tool_schemas"] = tools if tools is not None else _canonical_tool_schemas()
        return d

    # Backwards-compatible alias used in some drafts
    as_dict = to_dict


CONFIG_A = AblationConfig.for_condition("A")
CONFIG_B = AblationConfig.for_condition("B")
CONFIG_C = AblationConfig.for_condition("C")
CONFIG_D = AblationConfig.for_condition("D")


def config_diff(a: AblationConfig, b: AblationConfig) -> dict:
    da = a.to_dict()
    db = b.to_dict()
    diff = {}
    for k in da:
        if da[k] != db[k]:
            diff[k] = {"from": da[k], "to": db[k]}
    return diff


def formal_ablation_config(cond: str) -> AblationConfig:
    base = AblationConfig.for_condition(cond)
    return AblationConfig(
        **{
            **base.to_dict(),
            "model": FORMAL_TALKER_MODEL,
            "temperature": FORMAL_TALKER_TEMPERATURE,
            "planner_model": FORMAL_TALKER_MODEL,
            "planner_temperature": FORMAL_PLANNER_TEMPERATURE,
            "planner_request_timeout_seconds": FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS,
            "patient_agent_model": FORMAL_PATIENT_AGENT_MODEL,
            "patient_agent_temperature": FORMAL_PATIENT_AGENT_TEMPERATURE,
            "max_turns": FORMAL_MAX_TURNS,
            "seed": FORMAL_SEED,
        }
    )


def formal_runtime_spec() -> dict:
    conditions = {}
    for cond in ("A", "B", "C", "D"):
        cfg = formal_ablation_config(cond)
        conditions[cond] = {
            "enable_planner": cfg.enable_planner,
            "enable_dynamic_tool_gate": cfg.enable_dynamic_tool_gate,
            "enable_output_guard": cfg.enable_output_guard,
        }
    return {
        "talker_model": FORMAL_TALKER_MODEL,
        "talker_temperature": FORMAL_TALKER_TEMPERATURE,
        "planner_model": FORMAL_TALKER_MODEL,
        "planner_temperature": FORMAL_PLANNER_TEMPERATURE,
        "planner_request_timeout_seconds": FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS,
        "patient_agent_model": FORMAL_PATIENT_AGENT_MODEL,
        "patient_agent_temperature": FORMAL_PATIENT_AGENT_TEMPERATURE,
        "max_turns": FORMAL_MAX_TURNS,
        "seed": FORMAL_SEED,
        "subprocess_timeout_seconds": FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
        "input_guard": "ON",
        "enable_forced_retrieval": False,
        "enable_fixed_warning_append": False,
        "enable_question_budget_postprocessing": False,
        "conditions": conditions,
    }


FROZEN_FORMAL_CONFIG_FIELDS = (
    "condition",
    "enable_planner",
    "enable_dynamic_tool_gate",
    "enable_output_guard",
    "enable_forced_retrieval",
    "enable_fixed_warning_append",
    "enable_question_budget_postprocessing",
    "model",
    "temperature",
    "planner_model",
    "planner_temperature",
    "planner_request_timeout_seconds",
    "patient_agent_model",
    "patient_agent_temperature",
    "max_turns",
    "seed",
)


def _frozen_formal_mismatches(config: Any) -> list:
    condition = getattr(config, "condition", None)
    if condition not in {"A", "B", "C", "D"}:
        return ["condition"]
    expected = formal_ablation_config(condition)
    mismatched = []
    for field in FROZEN_FORMAL_CONFIG_FIELDS:
        if getattr(config, field, None) != getattr(expected, field):
            mismatched.append(field)
    return mismatched


def is_frozen_formal_config(config: Any) -> bool:
    return not _frozen_formal_mismatches(config)


def require_frozen_formal_config(config: Any) -> None:
    mismatched = _frozen_formal_mismatches(config)
    if mismatched:
        condition = getattr(config, "condition", None)
        raise ValueError(
            "Formal execution requires the frozen formal config "
            f"(condition {condition!r}); "
            f"mismatched fields: {', '.join(mismatched)}"
        )


def _coerce_config(d: dict) -> AblationConfig:
    if isinstance(d, AblationConfig):
        return d
    # Filter to known fields
    fields = AblationConfig.__dataclass_fields__
    filtered = {k: v for k, v in d.items() if k in fields}
    # Ensure required fields have defaults if missing
    if "condition" not in filtered:
        filtered["condition"] = d.get("condition", "A")
    if "enable_planner" not in filtered:
        filtered["enable_planner"] = d.get("enable_planner", False)
    if "enable_dynamic_tool_gate" not in filtered:
        filtered["enable_dynamic_tool_gate"] = d.get("enable_dynamic_tool_gate", False)
    if "enable_output_guard" not in filtered:
        filtered["enable_output_guard"] = d.get("enable_output_guard", False)
    return AblationConfig(**filtered)
