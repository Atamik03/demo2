from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, timezone

class ActionType(str, Enum):
    TURN_ON = "TURN_ON"
    TURN_OFF = "TURN_OFF"
    SET_VALUE = "SET_VALUE"
    SET_SPEED = "SET_SPEED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    SET_SP = "SET_SP"        # controller setpoint
    SET_MODE = "SET_MODE"    # controller mode: АВТ / РУЧ
    ACK_ALARM = "ACK_ALARM"  # acknowledge an alarm
    # Local confirmations are emitted only by the field-operator screen.
    # They never call ``Equipment.apply_action`` and are used by the LMS
    # sequence checker to assess multi-operator practice.
    FIELD_INSPECT = "FIELD_INSPECT"
    FIELD_CONFIRM_LOCAL = "FIELD_CONFIRM_LOCAL"
    FIELD_CONFIRM_RESULT = "FIELD_CONFIRM_RESULT"

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class OperatorAction(BaseModel):
    timestamp: float
    operator_id: str
    equipment_id: str
    action_type: ActionType
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    source: str = "operator_panel"

class Alarm(BaseModel):
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    id: str
    timestamp: float
    parameter: str
    actual_value: float
    threshold: float
    severity: Severity
    description: str
    node_id: Optional[str] = None

class ErrorEvent(BaseModel):
    error_type: str
    severity: Severity
    timestamp: float
    operator_action: str
    expected_action: str
    cause: str
    consequence: str

class SimulationConfig(BaseModel):
    dt: float = 1.0
    random_seed: int = 42
    nominal_pressure: float = 101325.0  # Pa
    nominal_temperature: float = 293.15  # K
    nominal_flow: float = 100.0  # kg/s
    history_limit: int = Field(default=1000, ge=1)  # max retained states
    hydraulics_tau: float = 4.0  # s, first-order inertia of flows/pressures
    equipment_parameters: Dict[str, Any] = Field(default_factory=dict)

class SimulationState(BaseModel):
    timestamp: float = 0.0
    pressure: Dict[str, float] = Field(default_factory=dict)
    temperature: Dict[str, float] = Field(default_factory=dict)
    feed_flow: float = 0.0
    product_flow: float = 0.0
    level: Dict[str, float] = Field(default_factory=dict)
    heat_duty: Dict[str, float] = Field(default_factory=dict)
    pump_states: Dict[str, bool] = Field(default_factory=dict)
    valve_positions: Dict[str, float] = Field(default_factory=dict)
    equipment_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    node_params: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    controllers: Dict[str, Any] = Field(default_factory=dict)
    alarms: List[Alarm] = Field(default_factory=list)
    active_failures: List[str] = Field(default_factory=list)
    errors: List[ErrorEvent] = Field(default_factory=list)
