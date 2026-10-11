"""
heat_exchanger.py
=================
Rigorous heat exchanger model with LMTD and energy balance.
"""

from typing import Dict, Any, Optional
import numpy as np
from .base_equipment import BaseEquipment, EquipmentState
from models.stream import Stream, Phase

class HeatExchanger(BaseEquipment):
    """
    Shell-and-tube heat exchanger with LMTD method.
    """

    def __init__(self, equipment_id: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(equipment_id, params or {})
        self.duty = 0.0
        self.t_hot_out = 293.15
        self.t_cold_out = 293.15
        self._thermal_ready = False
        self._apply_params()

    def _apply_params(self) -> None:
        self.u = self.params.get("u", 300.0)
        self.area = self.params.get("area", 200.0)
        self.thermal_tau_s = max(0.0, float(self.params.get("thermal_tau_s", 12.0)))

    def _relax_temperature(self, previous: float, target: float, lo: float, hi: float, dt: float) -> float:
        """First-order thermal response of the apparatus metal and hold-up."""
        if not self._thermal_ready or self.thermal_tau_s <= 0.0:
            return min(hi, max(lo, target))
        alpha = 1.0 - np.exp(-max(0.0, dt) / self.thermal_tau_s)
        return min(hi, max(lo, previous + alpha * (target - previous)))

    def step(self, dt: float, **inputs) -> Dict[str, Any]:
        """
        Inputs:
            hot_in: Stream
            cold_in: Stream
            thermo: ThermodynamicModel

        The exchanger is bidirectional: heat always flows from the physically
        hotter inlet to the physically colder one, regardless of which stream
        is connected to the ``hot_in`` / ``cold_in`` ports.  The internal
        calculation labels the hotter stream "hot" and the colder one "cold";
        the results are then mapped back to the original ports so the port
        roles (hot_out / cold_out) always refer to the connected streams.
        """
        port_hot_in: Stream = inputs.get("hot_in")
        port_cold_in: Stream = inputs.get("cold_in")
        thermo = inputs.get("thermo")
        previous_hot_out = self.t_hot_out
        previous_cold_out = self.t_cold_out

        # АВЗ/АВО: через аппарат проходит один технологический поток, а тепло
        # отводится окружающим воздухом. Воздух не является второй
        # технологической линией и не требует cold_in/cold_out на схеме.
        if self.params.get("cooling_medium") == "air" and port_hot_in is not None and thermo is not None:
            return self._air_cool(port_hot_in, thermo, dt)
        
        if port_hot_in is None or port_cold_in is None or thermo is None:
            # An unavailable utility/recycle cannot erase the process stream.
            # Preserve the supplied channel with zero inter-channel heat duty.
            self.duty = 0.0
            return {
                "hot_out": port_hot_in, "cold_out": port_cold_in, "duty": 0.0,
                "t_hot_in": port_hot_in.temperature if port_hot_in is not None else None,
                "t_hot_out": port_hot_in.temperature if port_hot_in is not None else None,
                "t_cold_in": port_cold_in.temperature if port_cold_in is not None else None,
                "t_cold_out": port_cold_in.temperature if port_cold_in is not None else None,
            }

        # Resolve the physical roles: the hotter stream releases heat, the
        # colder one absorbs it, no matter which port it is attached to.
        # For a marked cooler/heater the ports are physical and must not swap
        # merely because two inlet temperatures cross by a fraction of a
        # degree. That swap was the source of alternating outlet readings.
        fixed_roles = self.params.get("thermal_role") in ("cooler", "heater")
        if fixed_roles or port_hot_in.temperature >= port_cold_in.temperature:
            hot_in, cold_in = port_hot_in, port_cold_in
            swapped = False
        else:
            hot_in, cold_in = port_cold_in, port_hot_in
            swapped = True

        # Calculate max possible heat transfer (effectiveness-NTU or simple approach)
        # For MVP, we use a simplified iterative LMTD
        cp_hot = thermo.calculate_cp(hot_in.temperature, hot_in.pressure, hot_in.composition)
        cp_cold = thermo.calculate_cp(cold_in.temperature, cold_in.pressure, cold_in.composition)
        
        c_hot = hot_in.mass_flow * cp_hot
        c_cold = cold_in.mass_flow * cp_cold
        
        if c_hot <= 0 or c_cold <= 0:
            self.duty = 0.0
            return {"hot_out": port_hot_in, "cold_out": port_cold_in, "duty": 0.0,
                    "t_hot_in": port_hot_in.temperature, "t_hot_out": port_hot_in.temperature,
                    "t_cold_in": port_cold_in.temperature, "t_cold_out": port_cold_in.temperature}

        # Simplified duty calculation for MVP
        # Q = UA * LMTD
        # We need an iterative solver for real T_out, here we use a fixed approach
        dt_max = hot_in.temperature - cold_in.temperature
        if dt_max <= 0:
            self.duty = 0.0
            return {"hot_out": port_hot_in, "cold_out": port_cold_in, "duty": 0.0,
                    "t_hot_in": port_hot_in.temperature, "t_hot_out": port_hot_in.temperature,
                    "t_cold_in": port_cold_in.temperature, "t_cold_out": port_cold_in.temperature}
            
        # Effectiveness-NTU method
        c_min = min(c_hot, c_cold)
        c_max = max(c_hot, c_cold)
        cr = c_min / c_max
        ntu = (self.u * self.area) / c_min
        
        # Effectiveness for counter-flow
        if cr < 1:
            eps = (1 - np.exp(-ntu * (1 - cr))) / (1 - cr * np.exp(-ntu * (1 - cr)))
        else:
            eps = ntu / (1 + ntu)

        duty_ntu = eps * c_min * dt_max

        # Physical duty caps so the outlet temperatures respect the second
        # law: the hot outlet cannot be colder than the cold inlet and the
        # cold outlet cannot be hotter than the hot inlet.  The NTU shortcut
        # with constant Cp over-estimates the duty whenever latent heat is
        # involved (a condenser would "cool" the distillate far below the
        # cooling-water temperature), so the caps are enforced against the
        # actual flashed enthalpies.
        # Reference inlet enthalpies from the flashed EOS state, not the
        # stream's claimed enthalpy.  Upstream equipment (e.g. a column that
        # emits a super-saturated "vapor" distillate below its dew point) can
        # carry an enthalpy inconsistent with T/P/x; recomputing it makes the
        # energy balance and the duty caps self-consistent.
        try:
            h_hot_in = thermo.calculate_enthalpy(
                hot_in.temperature, hot_in.pressure, hot_in.composition)
        except Exception:
            h_hot_in = hot_in.enthalpy
        try:
            h_cold_in = thermo.calculate_enthalpy(
                cold_in.temperature, cold_in.pressure, cold_in.composition)
        except Exception:
            h_cold_in = cold_in.enthalpy
        try:
            h_hot_at_cold_in = thermo.calculate_enthalpy(
                cold_in.temperature, hot_in.pressure, hot_in.composition)
        except Exception:
            h_hot_at_cold_in = h_hot_in - c_hot * (hot_in.temperature - cold_in.temperature)
        try:
            h_cold_at_hot_in = thermo.calculate_enthalpy(
                hot_in.temperature, cold_in.pressure, cold_in.composition)
        except Exception:
            h_cold_at_hot_in = h_cold_in + c_cold * (hot_in.temperature - cold_in.temperature)
        duty_max_hot = hot_in.mass_flow * max(0.0, h_hot_in - h_hot_at_cold_in)
        duty_max_cold = cold_in.mass_flow * max(0.0, h_cold_at_hot_in - h_cold_in)
        self.duty = min(duty_ntu, duty_max_hot, duty_max_cold)
        if self.duty <= 0:
            return {
                "hot_out": port_hot_in, "cold_out": port_cold_in, "duty": 0.0,
                "t_hot_in": port_hot_in.temperature,
                "t_hot_out": port_hot_in.temperature,
                "t_cold_in": port_cold_in.temperature,
                "t_cold_out": port_cold_in.temperature,
            }

        # Energy balances
        h_hot_out = h_hot_in - self.duty / hot_in.mass_flow
        h_cold_out = h_cold_in + self.duty / cold_in.mass_flow

        if hasattr(thermo, "temperature_from_enthalpy"):
            try:
                self.t_hot_out = self._enthalpy_to_temp(thermo, hot_in, h_hot_out)
            except Exception:
                self.t_hot_out = hot_in.temperature - self.duty / c_hot
            try:
                self.t_cold_out = self._enthalpy_to_temp(thermo, cold_in, h_cold_out)
            except Exception:
                self.t_cold_out = cold_in.temperature + self.duty / c_cold
        else:
            self.t_hot_out = hot_in.temperature - self.duty / c_hot
            self.t_cold_out = cold_in.temperature + self.duty / c_cold

        # The shell/tubes have thermal inertia. Smooth the calculated outlet
        # temperatures so a new hydraulic iteration cannot make a refrigerator
        # jump between two values every one-second simulation tick.
        target_hot, target_cold = self.t_hot_out, self.t_cold_out
        # ``self.t_*_out`` was just overwritten by the steady-state
        # calculation above.  Keep the old apparatus temperatures first;
        # otherwise the relaxation receives target == previous and every
        # indication jumps instantly to the inlet/boundary value.
        self.t_hot_out = self._relax_temperature(
            previous_hot_out, target_hot, cold_in.temperature, hot_in.temperature, dt,
        )
        self.t_cold_out = self._relax_temperature(
            previous_cold_out, target_cold, cold_in.temperature, hot_in.temperature, dt,
        )
        self._thermal_ready = True
        try:
            h_hot_out = thermo.calculate_enthalpy(self.t_hot_out, hot_in.pressure, hot_in.composition)
            h_cold_out = thermo.calculate_enthalpy(self.t_cold_out, cold_in.pressure, cold_in.composition)
            self.duty = max(0.0, hot_in.mass_flow * (h_hot_in - h_hot_out))
        except Exception:
            pass

        # Map the internal (physical) hot/cold results back to the connected
        # ports: the "hot" outlet port always receives the cooled stream of the
        # port_hot_in connection and vice versa.
        if swapped:
            # port_hot_in was the physically colder stream (internal cold),
            # so it exits heated on the hot_out port.
            port_hot_out = cold_in.copy_with(temperature=self.t_cold_out, enthalpy=h_cold_out)
            port_cold_out = hot_in.copy_with(temperature=self.t_hot_out, enthalpy=h_hot_out)
            # Keep get_state() consistent with the port semantics.
            port_t_hot_out = self.t_cold_out
            port_t_cold_out = self.t_hot_out
            self.t_hot_out = port_t_hot_out
            self.t_cold_out = port_t_cold_out
            return {
                "hot_out": port_hot_out,
                "cold_out": port_cold_out,
                "duty": self.duty,
                "t_hot_in": port_hot_in.temperature,
                "t_hot_out": port_t_hot_out,
                "t_cold_in": port_cold_in.temperature,
                "t_cold_out": port_t_cold_out,
            }

        hot_out = hot_in.copy_with(temperature=self.t_hot_out, enthalpy=h_hot_out)
        cold_out = cold_in.copy_with(temperature=self.t_cold_out, enthalpy=h_cold_out)

        return {
            "hot_out": hot_out,
            "cold_out": cold_out,
            "duty": self.duty,
            "t_hot_in": hot_in.temperature,
            "t_hot_out": self.t_hot_out,
            "t_cold_in": cold_in.temperature,
            "t_cold_out": self.t_cold_out,
        }

    def _air_cool(self, stream: Stream, thermo: Any, dt: float) -> Dict[str, Any]:
        """Cool one process stream against ambient air in an AVO/AVZ."""
        ambient_k = float(self.params.get("ambient_temperature_c", 25.0)) + 273.15
        approach_k = max(1.0, float(self.params.get("air_approach_k", 10.0)))
        cp = thermo.calculate_cp(stream.temperature, stream.pressure, stream.composition)
        heat_capacity = stream.mass_flow * cp
        available_dt = max(0.0, stream.temperature - ambient_k - approach_k)
        if heat_capacity <= 0.0 or available_dt <= 0.0:
            self.duty = 0.0
            self.t_hot_out = stream.temperature
            self.t_cold_out = ambient_k
            return {
                "hot_out": stream, "cold_out": None, "duty": 0.0,
                "t_hot_in": stream.temperature, "t_hot_out": stream.temperature,
                "t_cold_in": ambient_k, "t_cold_out": ambient_k,
            }

        # The air side is not a pipe, but it still has a finite heat capacity.
        # Use the NTU effectiveness for a one-stream air cooler. Previously
        # enthalpy inversion left a partially condensing stream at its inlet
        # saturation temperature, so АВЗ showed a large duty but no cooling.
        ntu = (self.u * self.area) / max(heat_capacity, 1e-9)
        effectiveness = 1.0 - np.exp(-ntu)
        target = ambient_k + approach_k + available_dt * (1.0 - effectiveness)
        self.t_hot_out = self._relax_temperature(
            self.t_hot_out, target, ambient_k + approach_k, stream.temperature, dt,
        )
        self._thermal_ready = True
        try:
            h_in = thermo.calculate_enthalpy(stream.temperature, stream.pressure, stream.composition)
            h_out = thermo.calculate_enthalpy(self.t_hot_out, stream.pressure, stream.composition)
            self.duty = max(0.0, stream.mass_flow * (h_in - h_out))
        except Exception:
            self.duty = heat_capacity * max(0.0, stream.temperature - self.t_hot_out)
            h_out = stream.enthalpy - self.duty / stream.mass_flow
        self.t_cold_out = ambient_k
        return {
            "hot_out": stream.copy_with(temperature=self.t_hot_out, enthalpy=h_out),
            "cold_out": None,
            "duty": self.duty,
            "t_hot_in": stream.temperature,
            "t_hot_out": self.t_hot_out,
            "t_cold_in": ambient_k,
            "t_cold_out": ambient_k,
        }

    def _enthalpy_to_temp(self, thermo, stream, h_target: float) -> float:
        """Monotone phase-aware enthalpy -> temperature inversion.

        Inverts the flashed (auto-phase) enthalpy H(T, P, x) for the stream.
        Because the auto-phase enthalpy includes the latent heat, a condensing
        distillate stays pinned at its saturation temperature and a two-phase
        hot stream condenses in place -- instead of "warming up" or dropping
        below the cooling medium like the old fixed-LIQUID-phase inversion
        did.
        """
        p = stream.pressure
        comp = stream.composition
        lo, hi = 200.0, 1200.0
        f_lo = thermo.calculate_enthalpy(lo, p, comp) - h_target
        f_hi = thermo.calculate_enthalpy(hi, p, comp) - h_target
        if f_lo >= 0.0:
            return lo
        if f_hi <= 0.0:
            return hi
        for _ in range(35):
            mid = 0.5 * (lo + hi)
            f_mid = thermo.calculate_enthalpy(mid, p, comp) - h_target
            if abs(f_mid) < 1e-6:
                return mid
            if f_lo * f_mid < 0.0:
                hi = mid
            else:
                lo, f_lo = mid, f_mid
        return 0.5 * (lo + hi)

    def get_state(self) -> EquipmentState:
        self.state.extra["duty"] = self.duty
        self.state.extra["t_hot_out"] = self.t_hot_out
        self.state.extra["t_cold_out"] = self.t_cold_out
        return self.state

    def apply_action(self, action_type: str, value: Optional[float] = None) -> None:
        pass

    def reset(self) -> None:
        super().reset()
        self.duty = 0.0
        self.t_hot_out = 293.15
        self.t_cold_out = 293.15
        self._thermal_ready = False
