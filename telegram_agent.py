import os
import sys
import json
import subprocess
import asyncio
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
import psutil

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class AntigravityTelegramAgent:
    """
    Antigravity Remote AI Agent for Telegram.
    Allows Guille to chat in natural language, request code or configuration changes,
    diagnose trading performance, and execute remote PC administration commands.
    """
    def __init__(self, api_key: str = None, workspace_dir: str = None, bot_ref = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.workspace_dir = Path(workspace_dir or os.getcwd()).resolve()
        self.bot_ref = bot_ref
        self.model_name = "gemini-2.5-flash"
        self.is_configured = False
        
        if _GENAI_AVAILABLE and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.is_configured = True
            except Exception as e:
                print(f"[Telegram Agent] Error configuring Gemini: {e}")

    # ==================== TOOLS ====================

    def read_code_file(self, filepath: str) -> str:
        """Reads the content of any project file."""
        try:
            target_path = (self.workspace_dir / filepath).resolve()
            if not str(target_path).startswith(str(self.workspace_dir)):
                return "Error: Access outside project directory is not allowed."
            
            if not target_path.exists():
                return f"Error: File '{filepath}' does not exist."
            
            with open(target_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                
            if len(content) > 20000:
                return f"--- {filepath} (Truncated, first 20000 characters) ---\n" + content[:20000]
            return f"--- {filepath} ---\n" + content
        except Exception as e:
            return f"Error reading {filepath}: {str(e)}"

    def write_code_file(self, filepath: str, content: str) -> str:
        """Writes or modifies a code or config file within the project."""
        try:
            target_path = (self.workspace_dir / filepath).resolve()
            if not str(target_path).startswith(str(self.workspace_dir)):
                return "Error: Writing outside project directory is not allowed."
            
            # Save automatic backup if file exists
            if target_path.exists():
                backup_dir = self.workspace_dir / "backups"
                backup_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = backup_dir / f"{target_path.name}_{timestamp}.bak"
                with open(target_path, 'r', encoding='utf-8', errors='replace') as src:
                    with open(backup_path, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            return f"File '{filepath}' successfully saved. (Backup created in /backups)"
        except Exception as e:
            return f"Error writing {filepath}: {str(e)}"

    def update_config_key(self, key_path: str, value_str: str) -> str:
        """
        Updates a specific key in config.json.
        Examples:
          key_path='trading.amount', value_str='2.0'
          key_path='verbose_telegram', value_str='false'
          key_path='trading.enabled_strategies', value_str='[\"WaveTrend + Keltner Channel Reversion\"]'
        """
        try:
            config_path = self.workspace_dir / "config.json"
            if not config_path.exists():
                return "Error: config.json not found."
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            try:
                parsed_val = json.loads(value_str)
            except Exception:
                parsed_val = value_str
                
            keys = key_path.split('.')
            d = config
            for k in keys[:-1]:
                if k not in d or not isinstance(d[k], dict):
                    d[k] = {}
                d = d[k]
            d[keys[-1]] = parsed_val
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                
            return f"config.json updated: {key_path} = {parsed_val}"
        except Exception as e:
            return f"Error updating config: {str(e)}"

    def restart_bot_signal(self) -> str:
        """Hot-reloads the trading bot by creating restart.signal."""
        try:
            signal_path = self.workspace_dir / "restart.signal"
            signal_path.write_text("restart", encoding='utf-8')
            return "Restart signal sent (restart.signal). The supervisor will reload the bot shortly."
        except Exception as e:
            return f"Error sending restart signal: {e}"

    def restart_windows_gui(self) -> str:
        """Restarts Windows GUI (Explorer.exe) to unfreeze the desktop interface."""
        try:
            cmd = "taskkill /f /im explorer.exe && start explorer.exe"
            subprocess.Popen(cmd, shell=True)
            return "Windows GUI (Explorer.exe) successfully restarted."
        except Exception as e:
            return f"Error restarting GUI: {e}"

    def reboot_windows_pc(self, force: bool = True) -> str:
        """Forces a reboot of the Windows operating system."""
        try:
            cmd = "shutdown /r /f /t 5"
            subprocess.Popen(cmd, shell=True)
            return "Forced reboot initiated. PC will restart in 5 seconds."
        except Exception as e:
            return f"Error initiating PC reboot: {e}"

    def run_command(self, command: str) -> str:
        """Executes a shell command (PowerShell/CMD) or diagnostic script in the project directory."""
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_dir),
                capture_output=True,
                text=True,
                timeout=45
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()
            out = []
            if stdout:
                out.append(f"STDOUT:\n{stdout}")
            if stderr:
                out.append(f"STDERR:\n{stderr}")
            if not out:
                out.append(f"Exit code: {res.returncode}")
            result_str = "\n".join(out)
            if len(result_str) > 4000:
                result_str = result_str[:4000] + "\n...(Output truncated)"
            return result_str
        except subprocess.TimeoutExpired:
            return "Command execution timed out after 45s."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def get_trading_status(self) -> str:
        """Retrieves current trading bot state, balances, session profit, and recent trades."""
        status_info = []
        try:
            # 1. Config overview
            cfg_file = self.workspace_dir / "config.json"
            if cfg_file.exists():
                with open(cfg_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    trading_cfg = cfg.get('trading', {})
                    status_info.append(f"Active pairs: {len(trading_cfg.get('pairs_with_timeframe', {}))}")
                    status_info.append(f"Timeframes: {trading_cfg.get('intervals', [300])}s")
                    status_info.append(f"Base trade amount: ${trading_cfg.get('amount', 1.0)}")
            
            # 2. Latest trades
            logs_dir = self.workspace_dir / "logs" / "trades"
            if logs_dir.exists():
                csv_files = sorted(list(logs_dir.glob("trades_*.csv")), reverse=True)
                if csv_files:
                    import pandas as pd
                    df = pd.read_csv(csv_files[0])
                    if not df.empty and 'result' in df.columns:
                        completed = df[df['result'].isin(['WIN', 'LOSS'])]
                        wins = (completed['result'] == 'WIN').sum()
                        total = len(completed)
                        wr = (wins / total * 100) if total > 0 else 0
                        pnl = completed['profit_loss'].sum() if 'profit_loss' in completed.columns else 0
                        status_info.append(f"Today: {total} trades | {wr:.1f}% WR | PnL: ${pnl:+.2f}")
            
            # 3. PC state
            cpu = psutil.cpu_percent(interval=0.2)
            ram = psutil.virtual_memory().percent
            status_info.append(f"PC: CPU {cpu}% | RAM {ram}%")
            
            return "\n".join(status_info)
        except Exception as e:
            return f"Error retrieving status: {e}"

    # ==================== PROCESSING WITH GEMINI ====================

    async def process_message(self, user_prompt: str) -> str:
        """
        Processes a natural language prompt from Telegram using Gemini function calling.
        """
        if not self.is_configured:
            return "❌ Gemini API is not configured or currently unavailable."

        system_instruction = (
            "You are Antigravity Remote Agent, Guille's personal quantitative trading assistant, coder, "
            "and Windows system administrator.\n"
            "Guille messages you from his mobile phone via Telegram while away from the computer.\n\n"
            "Available Tools:\n"
            "1. read_code_file(filepath): Read source code, logs, or configurations.\n"
            "2. write_code_file(filepath, content): Write or modify project files.\n"
            "3. update_config_key(key_path, value_str): Update keys/values in config.json.\n"
            "4. restart_bot_signal(): Hot-reload the trading bot via restart.signal.\n"
            "5. restart_windows_gui(): Unfreeze the PC by restarting Explorer.exe.\n"
            "6. reboot_windows_pc(force): Force reboot the Windows PC.\n"
            "7. run_command(command): Run shell commands, backtests, or diagnostics.\n"
            "8. get_trading_status(): Retrieve live bot stats, win rate, and PnL.\n\n"
            "Instructions:\n"
            "- ALWAYS respond in clean, professional English.\n"
            "- Keep explanations direct, concise, and technically precise.\n"
            "- If asked to modify strategies or configurations, inspect the file first if needed, apply changes, and trigger restart_bot_signal.\n"
            "- If asked to reboot the PC or restart the GUI, do it immediately.\n"
            "- Clearly summarize the exact changes made and any diagnostic findings."
        )

        tools = [
            self.read_code_file,
            self.write_code_file,
            self.update_config_key,
            self.restart_bot_signal,
            self.restart_windows_gui,
            self.reboot_windows_pc,
            self.run_command,
            self.get_trading_status
        ]

        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                tools=tools
            )
            
            chat = model.start_chat(enable_automatic_function_calling=True)
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: chat.send_message(user_prompt)
            )
            
            return response.text.strip()
        except Exception as e:
            print(f"[Telegram Agent] Exception processing message: {e}")
            return f"⚠️ Error in Antigravity Agent: {str(e)}"
