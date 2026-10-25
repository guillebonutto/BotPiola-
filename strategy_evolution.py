"""
=============================================================================
    MOTOR DE EVOLUCIÓN DINÁMICA Y AUTO-OPTIMIZACIÓN (PAPER TRADING)
=============================================================================
1. Aislamiento Total: Corre 100% en Paper Trading (0 riesgo en cuenta real).
2. Genera nuevas mutaciones e hipótesis cuantitativas (SMC Liquidity/FVG,
   Scalpers rápidos, Momentum, Reversión).
3. Monitorea el Win Rate real y racha de cada estrategia en simulación.
4. Auto-ajuste dinámico: Si una variante cae en rendimiento, ajusta sus
   hiperparámetros (períodos, umbrales de mecha, filtros RSI) y crea una
   nueva variante evolucionada (Gen{N}).
5. Selección Natural: Descarta variantes fallidas y consolida como
   "⭐ Validada en Paper" aquellas que alcancen WR >= 58-60%.
=============================================================================
"""

import json
import random
from pathlib import Path
from datetime import datetime

from strategy_rapid_scalper import (
    FastEMAPullbackScalper,
    StochasticBollingerBurst,
    RSIVelocityMomentum,
    MicroRangeBreakout
)
from strategy_liquidity_fvg import StrategyLiquidityFVG

STATE_FILE = Path("dynamic_strategies.json")

class StrategyEvolutionEngine:
    def __init__(self, max_dynamic_strategies=7):
        self.max_dynamic = max_dynamic_strategies
        self.dynamic_strategies = []
        self.generation = 1
        self.load_state()

        if not self.dynamic_strategies:
            self.seed_initial_generation()

    def seed_initial_generation(self):
        """Genera el lote inicial de variantes cuantitativas diversas para incubación en Paper."""
        initial_pool = [
            StrategyLiquidityFVG(swing_window=15, min_wick_ratio=0.32, fvg_lookback=5, rsi_filter_enabled=True, name="[SMC] Liquidity Sweep & FVG (Gen1)"),
            FastEMAPullbackScalper(fast_period=9, slow_period=21, name="[RAPID] EMA Pullback 9/21"),
            FastEMAPullbackScalper(fast_period=7, slow_period=16, name="[RAPID] Fast EMA Scalp 7/16"),
            StochasticBollingerBurst(stoch_k=5, stoch_d=3, bb_window=14, bb_dev=1.8, name="[RAPID] Stoch Burst 5/3 + BB14"),
            StochasticBollingerBurst(stoch_k=8, stoch_d=3, bb_window=20, bb_dev=2.0, name="[RAPID] Stoch Scalp 8/3 + BB20"),
            RSIVelocityMomentum(rsi_period=7, name="[RAPID] RSI Velocity 7p"),
            MicroRangeBreakout(range_window=5, name="[RAPID] Micro Range Breakout 5v"),
        ]
        self.dynamic_strategies = initial_pool[:self.max_dynamic]
        self.save_state()

    def generate_mutation(self, parent=None, is_auto_tune=False):
        """
        Crea una nueva estrategia mutando o ajustando hiperparámetros.
        Si se especifica parent y is_auto_tune=True, realiza ajuste fino correctivo.
        """
        self.generation += 1
        tag = f"Gen{self.generation}"

        # Si viene de un padre para ajuste fino
        if parent is not None and is_auto_tune:
            if isinstance(parent, StrategyLiquidityFVG):
                # Auto-ajuste para Liquidity FVG: Aumentar exigencia de mecha y ajustar ventana
                new_wick = min(0.45, round(parent.min_wick_ratio + random.choice([0.03, 0.05]), 2))
                new_w = random.choice([12, 15, 18])
                return StrategyLiquidityFVG(
                    swing_window=new_w,
                    min_wick_ratio=new_wick,
                    fvg_lookback=parent.fvg_lookback,
                    rsi_filter_enabled=True,
                    name=f"[SMC] Liquidity & FVG W{new_w}/M{int(new_wick*100)} ({tag})"
                )
            elif isinstance(parent, FastEMAPullbackScalper):
                # Auto-ajuste para EMA Scalper: Separar medias para mayor confirmación
                fast = max(6, parent.fast_period + random.choice([-1, 1]))
                slow = fast + random.choice([12, 14, 16])
                return FastEMAPullbackScalper(fast_period=fast, slow_period=slow, name=f"[RAPID] EMA Pullback {fast}/{slow} ({tag})")
            elif isinstance(parent, StochasticBollingerBurst):
                # Auto-ajuste para Stoch BB: Aumentar desviaciones para filtrar ruido institucional
                dev = round(min(2.5, parent.bb_dev + 0.2), 1)
                bb_w = 14 if parent.bb_window != 14 else 20
                return StochasticBollingerBurst(stoch_k=parent.stoch_k_period, stoch_d=parent.stoch_d_period, bb_window=bb_w, bb_dev=dev, name=f"[RAPID] Stoch BB Dev{dev}/W{bb_w} ({tag})")
            elif isinstance(parent, RSIVelocityMomentum):
                # Auto-ajuste para RSI Velocity: Calibrar período óptimo
                p_rsi = 7 if parent.rsi_period != 7 else 9
                return RSIVelocityMomentum(rsi_period=p_rsi, name=f"[RAPID] RSI Velocity {p_rsi}p ({tag})")

        # Mutación aleatoria de familias disponibles
        family = random.choice(["liquidity_fvg", "ema", "stoch", "rsi", "breakout"])

        if family == "liquidity_fvg":
            w = random.choice([12, 15, 18, 20])
            wick = round(random.choice([0.32, 0.36, 0.40, 0.44]), 2)
            fvg_look = random.choice([3, 4, 5, 6])
            rsi_filter = True
            return StrategyLiquidityFVG(
                swing_window=w,
                min_wick_ratio=wick,
                fvg_lookback=fvg_look,
                rsi_filter_enabled=rsi_filter,
                name=f"[SMC] Liquidity & FVG W{w}/M{int(wick*100)} ({tag})"
            )

        elif family == "ema":
            fast = random.choice([6, 7, 8, 9, 10])
            slow = fast + random.choice([8, 10, 12, 14])
            return FastEMAPullbackScalper(fast_period=fast, slow_period=slow, name=f"[RAPID] EMA Pullback {fast}/{slow} ({tag})")

        elif family == "stoch":
            k = random.choice([5, 6, 7, 8])
            d = random.choice([2, 3, 4])
            bb_w = random.choice([14, 20])
            dev = round(random.choice([2.0, 2.2, 2.4]), 1)
            return StochasticBollingerBurst(stoch_k=k, stoch_d=d, bb_window=bb_w, bb_dev=dev, name=f"[RAPID] Stoch {k}/{d}+BB{bb_w} Dev{dev} ({tag})")

        elif family == "rsi":
            period = random.choice([7, 9, 11])
            return RSIVelocityMomentum(rsi_period=period, name=f"[RAPID] RSI Velocity {period}p ({tag})")

        else: # breakout
            win = random.choice([3, 4, 5, 6, 7])
            return MicroRangeBreakout(range_window=win, name=f"[RAPID] Micro Breakout {win}v ({tag})")

    def evaluate_and_evolve(self, paper_stats, min_trades=8, min_wr=0.525, target_wr=0.60):
        """
        Revisa los resultados acumulados de las estrategias en Paper Trading:
        - Si una variante tiene >= min_trades y WR < min_wr:
          Aplica AUTO-AJUSTE DINÁMICO de parámetros para corregirla y mutarla.
        - Si tiene >= min_trades y WR >= target_wr:
          La cataloga como '⭐ VALIDADA EN PAPER' (muestra exitosa probada).
        Retorna lista de mensajes informativos para la GUI / telemetría.
        """
        logs = []
        survivors = []

        # Intentar conectar con gui_bridge para registrar telemetría
        try:
            from gui_bridge import gui_bridge
        except Exception:
            gui_bridge = None

        for strat in self.dynamic_strategies:
            st = paper_stats.get(strat.name, {'trades': 0, 'wins': 0, 'losses': 0})
            total = st['wins'] + st['losses']
            wr = (st['wins'] / total) if total > 0 else 0.0

            # Caso 1: Muestra suficiente y rendimiento bajo (< min_wr) -> AUTO-AJUSTE DINÁMICO
            if total >= min_trades and wr < min_wr:
                # Se auto-ajusta buscando corregir las fallas del padre
                new_strat = self.generate_mutation(parent=strat, is_auto_tune=True)
                survivors.append(new_strat)
                msg = f"🧬 AUTO-AJUSTE DINÁMICO: '{strat.name}' cayó a {wr*100:.1f}% WR ({total}t). Reajustada y reemplazada por '{new_strat.name}'."
                logs.append(msg)
                print(f"[PAPER-INCUBADORA] {msg}")
                if gui_bridge:
                    gui_bridge.log(msg, "WARN")

            # Caso 2: Muestra suficiente y éxito demostrado (>= target_wr)
            elif total >= min_trades and wr >= target_wr:
                survivors.append(strat)
                msg = f"⭐ VALIDADA EN PAPER: '{strat.name}' consolidada con éxito ({total}t, WR: {wr*100:.1f}%). Manteniendo en evaluación."
                logs.append(msg)
                print(f"[PAPER-INCUBADORA] {msg}")
                if gui_bridge:
                    gui_bridge.log(msg, "WIN")

            else:
                # Sigue acumulando muestra
                survivors.append(strat)

        # Rellenar hasta max_dynamic si faltan variantes
        while len(survivors) < self.max_dynamic:
            new_strat = self.generate_mutation()
            survivors.append(new_strat)
            msg = f"🌱 Nueva hipótesis generada para Paper: '{new_strat.name}'"
            logs.append(msg)
            if gui_bridge:
                gui_bridge.log(msg, "INFO")

        self.dynamic_strategies = survivors
        self.save_state()
        return logs

    def save_state(self):
        try:
            data = {
                "generation": self.generation,
                "strategies": [s.name for s in self.dynamic_strategies],
                "last_update": datetime.now().isoformat()
            }
            STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[PAPER-EVO] Error guardando estado: {e}")

    def load_state(self):
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.generation = data.get("generation", 1)
        except Exception:
            pass
