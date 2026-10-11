"""
tank.py
=======
Buffer tank (settler / feed tank) with a real material balance and a physical
drain line:

  dM/dt  = m_in - m_out
  m_out  = min(draw(level), max_out)
  draw   = sqrt(rho*g*h / k_drain)          (static-head drain)

The tank has NO hidden level controller: the outflow is NOT `m_in + Kc*(L-SP)`.
The outflow is set by the static head of the liquid column and the resistance
of the outlet line (k_drain), clamped by the downstream capacity `max_out`.
The level is a consequence of the mass balance: closing a downstream valve
cuts `max_out`, the outflow drops and the level builds up; opening it lets the
level fall.  The drain resistance is calibrated so that at the nominal draw
flow and reference level the line passes exactly the nominal flow.

Mass is always conserved and the product never disappears.
"""

import math
from typing import Any, Dict, Optional
from .base_equipment import BaseEquipment, EquipmentState
from models.stream import Phase, Stream


class Tank(BaseEquipment):
    """
    Buffer / settling tank with level dynamics and mass conservation.
    """

    def __init__(self, equipment_id: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(equipment_id, params or {})
        init_level = self.params.get("initial_level", 2.0)
        self.level = init_level
        self.setpoint = self.params.get("setpoint_level", init_level)
        # У неподвижной ёмкости также есть температура. Раньше она появлялась
        # только после первого расхода через аппарат, из-за чего КИП на Е-1
        # показывал прочерк на холодной/остановленной установке.
        self.temperature = float(
            self.params.get("initial_temperature_c", self.params.get("temperature_c", 25.0))
        ) + 273.15
        self._drain_k: Optional[float] = None
        self._nominal_draw: Optional[float] = None
        self._h_ref: float = float(init_level)
        self._apply_params()
        # No design flow in the scheme: the outlet line has to be sized from the
        # duty that actually reaches the vessel (see step()).
        self._auto_sized = self._nominal_draw is None

    def _apply_params(self) -> None:
        diameter = self.params.get("diameter_m")
        if diameter:
            self.area = 3.141592653589793 * (float(diameter) / 2.0) ** 2
        else:
            self.area = self.params.get("vessel_area", self.params.get("sump_area", 30.0))
        self.height = self.params.get("height_m", 6.0)
        self.volume = self.area * self.height
        self.pressure = self.params.get("nominal_pressure", None)
        # Е-15 has a dedicated top vapour outlet.  A zero default means that
        # the pipe is present and ready for a vapour model without inventing a
        # gas rate for a liquid-only feed.
        self.gas_outlet_flow = max(0.0, float(self.params.get("gas_outlet_flow_kg_s", 0.0)))
        # Е-1 — водоотделитель: часть жидкой фазы отводится отдельным
        # нижним штуцером в сернисто-щелочную канализацию. Если состав
        # известен, доля определяется по воде; параметр оставлен как
        # инженерный минимум для неполного состава потока.
        self.water_drain_fraction = max(0.0, min(1.0, float(
            self.params.get("water_drain_fraction", 0.0)
        )))
        if "setpoint_level" in self.params:
            self.setpoint = max(0.0, float(self.params["setpoint_level"]))
        q_nom = self.params.get("nominal_flow") or self.params.get("flow_kg_s")
        if q_nom:
            self._nominal_draw = max(float(q_nom), 1e-3)
        self._drain_k = None

    def _drain_flow(self, level: float, rho: float) -> float:
        """Static-head drain through the outlet line: Q = sqrt(rho*g*h / k)."""
        if level <= 1e-9:
            return 0.0
        if self._drain_k is None or self._nominal_draw is None:
            return 0.0
        head = max(rho * 9.81 * level, 0.0)
        return math.sqrt(head / max(self._drain_k, 1e-12))

    def _calibrate_drain(self, nominal_flow: float, rho: float) -> None:
        """Calibrate the outlet-line resistance at the reference level.

        k_drain = rho*g*h_ref / q_nom^2, so that at h_ref the line passes
        exactly the nominal draw flow.  h_ref is the initial level (the
        operating point the vessel is designed for).
        """
        q_nom = max(float(nominal_flow), 1e-3)
        h_ref = max(float(self.level), 0.2)
        self._drain_k = max(rho * 9.81 * h_ref, 1.0) / max(q_nom * q_nom, 1e-6)
        self._h_ref = h_ref
        if self._nominal_draw is None:
            self._nominal_draw = q_nom

    def step(self, dt: float, **inputs) -> Dict[str, Any]:
        inlet: Stream = inputs.get("inlet_stream")
        # Downstream restriction: the tank may push out at most this much, the
        # excess accumulates in the level (blocked/dead-headed line).
        max_out = inputs.get("max_out")
        # The vessel's own operating pressure (base + hydrostatic head), the
        # same pressure the upstream line pushes against.  Keeps the outlet
        # continuous with the inlet even outside a solved hydraulic line.
        vessel_pressure = inputs.get("vessel_pressure")
        if inlet is None:
            return {
                "outlet_stream": None,
                "level": self.level,
                "setpoint": self.setpoint,
                "temperature": self.temperature,
            }

        rho = inlet.density if inlet.density and inlet.density > 0 else 850.0
        m_in = max(0.0, inlet.mass_flow)
        # Для идеально перемешанной модели принимаем температуру входящего
        # потока как текущую измеряемую температуру содержимого. При остановке
        # это значение сохраняется до следующего притока.
        self.temperature = inlet.temperature
        gas_out = min(self.gas_outlet_flow, m_in)
        liquid_in = m_in - gas_out
        water_fraction = max(
            self.water_drain_fraction,
            min(1.0, float(inlet.composition.get("water", 0.0))),
        )

        if self.state.failed:
            return {"outlet_stream": inlet, "level": self.level, "setpoint": self.setpoint}

        # The outlet-line resistance is calibrated once against the nominal
        # flow (explicit param, or the actual operating inflow at start-up).
        if self._drain_k is None:
            self._calibrate_drain(self._nominal_draw or max(m_in, 1e-3), rho)
        elif self._auto_sized and m_in > self._drain_flow(self.level, rho) \
                and self.level >= self._h_ref:
            # Auto-sizing of the outlet line.  Without an explicit design flow
            # the resistance is inferred from the operating point, and at the
            # first step that point is a cold plant: the inflow is still a
            # trickle, so the line would stay sized for that start-up transient
            # for good -- the vessel then fills up and never passes its real
            # duty (Е-1 took 7 kg/s and drained 0.03).  While the vessel is
            # demonstrably over-filling (level at or above its reference and
            # the inflow still exceeding the drain), re-size the line to the
            # flow that actually arrives.  Below the reference level the drain
            # follows the static head as before, so the dynamics stay real.
            self._calibrate_drain(m_in, rho)

        # Physical drain: the outflow follows the static head of the liquid
        # column (Q = sqrt(rho*g*h/k_drain)), never a level controller.  An
        # empty vessel cannot be drawn.  The downstream capacity clamps it.
        m_out = self._drain_flow(self.level, rho)
        if max_out is not None:
            m_out = min(m_out, max_out)
        m_out = max(0.0, m_out)

        # Material balance: accumulation = in - out.
        level_new = self.level + (liquid_in - m_out) / max(rho * self.area, 1e-6) * dt
        # Overflow: mass above the tank height cannot accumulate, so it must
        # leave the vessel (spill / relief to the downstream) — otherwise the
        # balance would silently destroy mass.
        overflow_mass = 0.0
        if level_new > self.height:
            overflow_mass = (level_new - self.height) * rho * self.area
            m_out += overflow_mass / max(dt, 1e-9)
            level_new = self.height
        level_new = max(0.0, level_new)
        self.level = level_new

        out_pressure = vessel_pressure or self.pressure or inlet.pressure
        water_out = min(m_out, liquid_in * water_fraction)
        hydrocarbon_out = max(0.0, m_out - water_out)
        outlet = inlet.copy_with(
            name="TankOut",
            pressure=out_pressure,
            mass_flow=hydrocarbon_out,
            temperature=inlet.temperature,
        )
        water_stream = inlet.copy_with(
            name="TankWaterOut",
            pressure=out_pressure,
            mass_flow=water_out,
            temperature=inlet.temperature,
            composition={"water": 1.0},
            phase=Phase.LIQUID,
            density=1000.0,
            viscosity=1.0e-3,
        )
        gas_outlet = inlet.copy_with(
            name="TankGasOut",
            mass_flow=gas_out,
            pressure=out_pressure,
            phase=Phase.VAPOR,
            density=1.2,
            viscosity=1.8e-5,
        )
        return {
            "outlet_stream": outlet,
            "water_outlet_stream": water_stream,
            "gas_outlet_stream": gas_outlet,
            "level": self.level,
            "setpoint": self.setpoint,
            "volume_m3": round(self.area * self.height, 2),
            "in_flow": m_in,
            "out_flow": m_out,
            "gas_out_flow": gas_out,
            "water_out_flow": water_out,
            "overflow_mass": overflow_mass,
            "temperature": self.temperature,
        }

    def get_state(self) -> EquipmentState:
        self.state.extra["level"] = self.level
        self.state.extra["setpoint"] = self.setpoint
        return self.state

    def apply_action(self, action_type: str, value: Optional[float] = None) -> None:
        # No hidden level controller: setpoint is informational only.
        if action_type in ("SET_VALUE", "SET_LEVEL") and value is not None:
            self.setpoint = max(0.0, value)

    def reset(self) -> None:
        super().reset()
        init_level = self.params.get("initial_level", 2.0)
        self.level = init_level
        self.setpoint = self.params.get("setpoint_level", init_level)
        self.temperature = float(
            self.params.get("initial_temperature_c", self.params.get("temperature_c", 25.0))
        ) + 273.15
        self._drain_k = None
        self._nominal_draw = None
        q_nom = self.params.get("nominal_flow") or self.params.get("flow_kg_s")
        if q_nom:
            self._nominal_draw = max(float(q_nom), 1e-3)
        self._apply_params()
