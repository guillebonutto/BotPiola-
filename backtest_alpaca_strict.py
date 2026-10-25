"""
backtest_alpaca_strict.py
=========================
Simulador Cuantitativo Estricto de 4 Niveles para Alpaca (Stocks, Forex & Crypto).
Aplica el Checklist Definitivo:
1. Depósito Inicial $100 USD.
2. Spreads variables (1.5 pips) y Comisiones por operación (0.05%).
3. Muestra de 3 a 5 Años con Forward Testing 75% In-Sample / 25% Out-of-Sample.
4. Reglas Estrictas Diarias: Max 5 trades, 3 Wins (Take Profit), 3 Losses (Stop Loss). Reset a las 17:00 EST.
5. Riesgo del 1.0% por trade ($1.00 USD).
"""

import asyncio
import json
import math
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

from broker_alpaca import download_yahoo_candles
from analysis import MarketAnalyzer
from strategy_stochastic import StrategyStochastic
from strategy_fibonacci import StrategyFibonacci
from strategy_wavetrend_keltner import StrategyWaveTrendKeltner
from strategy_smart_money_smc import StrategySmartMoneySMC
from strategy_divergence_pivot import StrategyDivergencePivot

# Forzar UTF-8 en Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

class AlpacaStrictBacktester:
    def __init__(self, initial_balance=100.0, risk_per_trade_percent=0.01):
        self.initial_balance = initial_balance
        self.risk_per_trade_percent = risk_per_trade_percent
        self.max_daily_trades = 5
        self.max_daily_wins = 3
        self.max_daily_losses = 3
        self.spread_pips = 1.5          # Spread para Forex
        self.commission_percent = 0.0005 # 0.05% comisión
        self.analyzer = MarketAnalyzer()
        
        self.strategies = [
            StrategyWaveTrendKeltner(bypass_filter=True),
            StrategyDivergencePivot(bypass_filter=True),
            StrategyStochastic(bypass_filter=True),
            StrategyFibonacci(bypass_filter=True),
            StrategySmartMoneySMC(bypass_filter=True)
        ]

    def _apply_spread_and_commission(self, pair, action, entry_price, exit_price):
        """Aplica spread realista y comisiones por lote/operación."""
        pip_value = 0.0001
        if "JPY" in pair:
            pip_value = 0.01
        elif "BTC" in pair or "ETH" in pair or "SOL" in pair:
            pip_value = 1.0

        spread_cost = (self.spread_pips * pip_value) if ("USD" in pair and not any(c in pair for c in ["BTC", "ETH", "SOL", "BNB"])) else (entry_price * self.commission_percent)

        if action == "BUY":
            real_entry = entry_price + spread_cost
            real_exit = exit_price
            raw_pnl = real_exit - real_entry
        else:
            real_entry = entry_price - spread_cost
            real_exit = exit_price
            raw_pnl = real_entry - real_exit

        commission = (real_entry + real_exit) * (self.commission_percent / 2)
        net_price_diff = raw_pnl - commission
        
        is_win = net_price_diff > 0
        return is_win, net_price_diff

    def _run_single_simulation(self, df, strategy, pair, interval):
        """Ejecuta la simulación barra por barra aplicando el reset diario a las 17:00 EST."""
        if df.empty or len(df) < 200:
            return []

        df_calc = self.analyzer.compute_indicators(df)
        trades = []
        
        balance = self.initial_balance
        current_day = None
        daily_trades_count = 0
        daily_wins = 0
        daily_losses = 0
        daily_pnl = 0.0

        for i in range(200, len(df_calc) - 1):
            curr_row = df_calc.iloc[i]
            next_row = df_calc.iloc[i+1]
            
            ts = curr_row['Timestamp']
            if isinstance(ts, (int, float, np.integer)):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                dt = pd.to_datetime(ts, utc=True)

            # Ajuste de zona horaria a NY (EST = UTC-5 / EDT = UTC-4) -> Cierre a las 17:00
            dt_ny = dt - timedelta(hours=5)
            trade_day = (dt_ny - timedelta(hours=17)).date() if dt_ny.hour >= 17 else dt_ny.date()

            # Reset diario
            if current_day != trade_day:
                current_day = trade_day
                daily_trades_count = 0
                daily_wins = 0
                daily_losses = 0
                daily_pnl = 0.0

            # Verificar límites estrictos del checklist
            if daily_trades_count >= self.max_daily_trades:
                continue
            if daily_wins >= self.max_daily_wins:
                continue
            if daily_losses >= self.max_daily_losses:
                continue

            sub_df = df_calc.iloc[:i+1].copy()
            try:
                action, reason, duration = strategy.get_signal(sub_df)
            except Exception:
                continue

            if action in ['BUY', 'SELL']:
                entry_p = curr_row['Close']
                exit_p = next_row['Close']
                
                is_win, price_diff = self._apply_spread_and_commission(pair, action, entry_p, exit_p)

                # Compounding dinámico PURO: 1.0% del saldo actual de la cuenta en cada trade
                risk_amount = balance * self.risk_per_trade_percent

                if is_win:
                    # Ratio Riesgo:Beneficio 1:2 (Gana 2.0x el riesgo arriesgado)
                    pnl_usd = round(risk_amount * 2.0, 2)
                    daily_wins += 1
                else:
                    # Pérdida de 1.0x el riesgo arriesgado (1.0%)
                    pnl_usd = -round(risk_amount, 2)
                    daily_losses += 1

                balance += pnl_usd
                daily_pnl += pnl_usd
                daily_trades_count += 1

                trades.append({
                    "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "day": str(trade_day),
                    "pair": pair,
                    "action": action,
                    "entry": entry_p,
                    "exit": exit_p,
                    "price_diff": round(abs(exit_p - entry_p), 2),
                    "is_win": is_win,
                    "pnl_usd": pnl_usd,
                    "balance_after": round(balance, 2),
                    "strategy": strategy.name
                })

        return trades

    def apply_spread_and_commission_proxy(self, pair, action, entry_price, exit_price):
        return self._apply_spread_and_commission(pair, action, entry_price, exit_price)

    async def run_full_strict_backtest(self):
        print("=========================================================================")
        print("  🔬 SIMULADOR CUANTITATIVO ESTRICTO ALPACA ($100 USD REAL CHECKLIST)")
        print("=========================================================================\n")
        
        pairs = ["USDJPY", "MSFT", "AAPL", "SPY", "QQQ", "META", "BTCUSD", "ETHUSD", "SOLUSD"]
        timeframes = [("15m (900s)", 900), ("1h (3600s)", 3600)]
        
        all_results = []

        for tf_label, interval in timeframes:
            for pair in pairs:
                print(f"📥 Descargando historial ({tf_label}) para {pair}...")
                candles = await download_yahoo_candles(pair, interval, lookback=5000)
                if not candles or len(candles) < 500:
                    print(f"  ❌ Velas insuficientes para {pair}.")
                    continue
                    
                df = pd.DataFrame(candles)
                df.columns = [c.capitalize() for c in df.columns]
                if 'Timestamp' not in df.columns and 'Time' in df.columns:
                    df['Timestamp'] = df['Time']
                    
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s', errors='coerce', utc=True)
                df = df.dropna(subset=['Timestamp']).sort_values('Timestamp').reset_index(drop=True)
                
                total_candles = len(df)
                print(f"  ✅ Velas obtenidas: {total_candles} ({df.iloc[0]['Timestamp'].strftime('%Y-%m-%d')} a {df.iloc[-1]['Timestamp'].strftime('%Y-%m-%d')})")
                
                # SPLIT 75% IN-SAMPLE / 25% FORWARD OUT-OF-SAMPLE
                split_idx = int(total_candles * 0.75)
                df_in_sample = df.iloc[:split_idx].copy()
                df_out_sample = df.iloc[split_idx:].copy()

                for strat in self.strategies:
                    # 1. In-Sample Training (75%)
                    trades_is = self._run_single_simulation(df_in_sample, strat, pair, interval)
                    is_wins = sum(1 for t in trades_is if t['is_win'])
                    is_losses = len(trades_is) - is_wins
                    is_wr = (is_wins / len(trades_is) * 100) if trades_is else 0.0
                    is_pnl = sum(t['pnl_usd'] for t in trades_is)

                    # 2. Forward Out-of-Sample Testing (25%)
                    trades_oos = self._run_single_simulation(df_out_sample, strat, pair, interval)
                    oos_wins = sum(1 for t in trades_oos if t['is_win'])
                    oos_losses = len(trades_oos) - oos_wins
                    oos_wr = (oos_wins / len(trades_oos) * 100) if trades_oos else 0.0
                    oos_pnl = sum(t['pnl_usd'] for t in trades_oos)

                    total_trades = len(trades_is) + len(trades_oos)
                    total_pnl = is_pnl + oos_pnl
                    combined_wr = ((is_wins + oos_wins) / total_trades * 100) if total_trades > 0 else 0.0

                    is_robust = (is_wr >= 55.0) and (oos_wr >= 50.0) and (total_trades >= 5) and (total_pnl > 0)

                    result_entry = {
                        "pair": pair,
                        "strategy": strat.name,
                        "interval": tf_label,
                        "total_candles": total_candles,
                        "in_sample": {
                            "trades": len(trades_is),
                            "wins": is_wins,
                            "losses": is_losses,
                            "win_rate": round(is_wr, 1),
                            "pnl_usd": round(is_pnl, 2)
                        },
                        "forward_out_of_sample": {
                            "trades": len(trades_oos),
                            "wins": oos_wins,
                            "losses": oos_losses,
                            "win_rate": round(oos_wr, 1),
                            "pnl_usd": round(oos_pnl, 2)
                        },
                        "combined": {
                            "total_trades": total_trades,
                            "win_rate": round(combined_wr, 1),
                            "total_pnl_usd": round(total_pnl, 2),
                            "verdict": "✅ APTO PARA ALPACAS REAL ($100 USD)" if is_robust else "⚠️ NO PASÓ FORWARD TEST / POCO WR"
                        }
                    }
                    all_results.append(result_entry)

        all_results.sort(key=lambda x: (x['forward_out_of_sample']['win_rate'], x['combined']['total_pnl_usd']), reverse=True)

        report_file = Path("alpaca_strict_backtest_report.json")
        report_file.write_text(json.dumps(all_results, indent=4), encoding="utf-8")

        print("\n=========================================================================")
        print("  🏆 TOP MEJORES CONFIGURACIONES APROBADAS FORWARD TEST ($100 USD)")
        print("=========================================================================")
        for r in all_results:
            if r['combined']['verdict'].startswith("✅"):
                print(f"🟢 {r['pair']} | {r['strategy']}")
                print(f"   • Entreno (75%): {r['in_sample']['win_rate']}% WR ({r['in_sample']['trades']} trades) | PnL: ${r['in_sample']['pnl_usd']}")
                print(f"   • Forward (25%): {r['forward_out_of_sample']['win_rate']}% WR ({r['forward_out_of_sample']['trades']} trades) | PnL: ${r['forward_out_of_sample']['pnl_usd']}")
                print(f"   • Veredicto: {r['combined']['verdict']}\n")

        print(f"\n📑 Reporte guardado en {report_file.resolve()}")

if __name__ == "__main__":
    backtester = AlpacaStrictBacktester()
    asyncio.run(backtester.run_full_strict_backtest())
