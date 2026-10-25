"""
=============================================================================
         PIBOT TRADING TERMINAL - INTERFAZ GRÁFICA DE USUARIO NATIVA
=============================================================================
Diseño Fintech Moderno (CustomTkinter) para PocketOption y Alpaca.
Control en tiempo real, protección anti-congelamiento y visualización completa.
=============================================================================
"""

import sys
import time
import os
import socket
import subprocess
import psutil
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

from gui_bridge import gui_bridge

# Configuración visual global de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Paleta de Colores Cyber-Fintech
COLOR_BG_DARK = "#090d16"
COLOR_CARD_BG = "#111827"
COLOR_CARD_BORDER = "#1f2937"
COLOR_ACCENT_CYAN = "#00d2ff"
COLOR_ACCENT_GREEN = "#10b981"
COLOR_ACCENT_RED = "#ef4444"
COLOR_ACCENT_AMBER = "#f59e0b"
COLOR_ACCENT_PURPLE = "#8b5cf6"
COLOR_TEXT_MAIN = "#f9fafb"
COLOR_TEXT_MUTED = "#9ca3af"

APP_WINDOW_TITLE = "⚡ PiBot Trading Terminal | PocketOption & Alpaca Dual Mode"
_GUI_LOCK_SOCKET = None

def acquire_gui_single_instance_lock():
    """Asegura que solo exista 1 sola ventana de la GUI abierta en Windows."""
    global _GUI_LOCK_SOCKET
    import socket
    import ctypes

    lock_port = 49995  # Puerto de bloqueo exclusivo para la GUI
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', lock_port))
        s.listen(1)
        _GUI_LOCK_SOCKET = s
        return True
    except OSError:
        # Ya hay una ventana abierta -> traerla al frente y salir
        if sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, APP_WINDOW_TITLE)
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    print("⚠️ PiBot Terminal ya está abierto en otra ventana. Traída al frente.")
                else:
                    print("⚠️ Ya existe una instancia de PiBot Terminal activa en segundo plano (puerto 49995).")
            except Exception:
                pass
        return False

class TradingTerminalApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_WINDOW_TITLE)
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.configure(fg_color=COLOR_BG_DARK)

        # Variables de estado
        self.filter_tag = "ALL"
        self.auto_scroll = tk.BooleanVar(value=True)
        self.all_logs = []
        self.current_view = "REAL"
        self.dist_metric_mode = "pnl"

        # Construir Interfaz y Estilos
        self._setup_cyber_ttk_styles()
        self._build_header()
        self._build_nav_bar()

        # Contenedores principales de vistas (Operativa Real vs Paper Trading Lab)
        self.real_view_container = ctk.CTkFrame(self, fg_color="transparent")
        self.paper_view_container = ctk.CTkFrame(self, fg_color="transparent")

        # Construir contenido de cada vista
        self._build_kpi_cards(self.real_view_container)
        self._build_quick_commands_bar(self.real_view_container)
        self._build_status_section(self.real_view_container)
        self._build_main_split(self.real_view_container)

        self._build_paper_view(self.paper_view_container)

        # Mostrar por defecto la vista Real
        self.real_view_container.pack(fill="both", expand=True)

        self._build_footer()

        # Interceptar cierre de ventana
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Iniciar bucles periódicos de actualización
        self.after(500, self._update_logs_tick)
        self.after(1000, self._update_telemetry_tick)

        # Registrar log inicial en GUI
        gui_bridge.log("Terminal gráfica iniciada con éxito en Python 3.14.", "WIN")
        
        # Modo 100% Desatendido: El bot siempre inicia la operativa automáticamente al abrirse
        gui_bridge.log("⚡ Modo 100% Desatendido: Verificando conexión de red e iniciando trading...", "INFO")
        self.after(600, self._auto_start_trading)

        # Conectar callback para desplegar el gráfico dinámico en telemetría cuando se solicite
        gui_bridge.on_request_chart = lambda: self.after(0, lambda: self._show_chart_view("both"))

    def _ensure_telemetry_service(self):
        """Asegura que el servicio de telemetría pibot_service.py esté activo en background sin consola."""
        try:
            for p in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmd = " ".join(p.info.get('cmdline') or [])
                    if "pibot_service.py" in cmd:
                        return True
                except Exception:
                    pass
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            base_dir = Path(__file__).resolve().parent
            python_exe = sys.executable
            subprocess.Popen([python_exe, "-u", "pibot_service.py"], creationflags=creationflags, cwd=str(base_dir))
            gui_bridge.log("Agente de telemetría PiBot (@pi_gui_bot) iniciado en segundo plano.", "INFO")
            return True
        except Exception as e:
            gui_bridge.log(f"Aviso telemetría PiBot: {e}", "WARN")
            return False

    def _is_internet_connected(self):
        """Verifica si hay salida real a Internet vía Google DNS."""
        try:
            with socket.create_connection(("8.8.8.8", 53), timeout=1.5):
                return True
        except OSError:
            return False

    def _auto_start_trading(self):
        """Verifica conexión de red nativa y arranca el motor automáticamente."""
        if not self._is_internet_connected():
            gui_bridge.log("Esperando enlace Wi-Fi / Internet de Windows (reintentando en 2s)...", "WARN")
            self.lbl_footer_status.configure(text="🔄 Esperando enlace Wi-Fi / Internet de Windows...")
            self.after(2000, self._auto_start_trading)
            return

        gui_bridge.log("Internet verificado y activo. Iniciando motor de trading...", "WIN")
        self._ensure_telemetry_service()
        if not gui_bridge.is_running:
            self._toggle_bot_execution()

    def _setup_cyber_ttk_styles(self):
        """Aplica estilo Cyber-Fintech dark a los Treeviews y Scrollbars eliminando bordes grises de Windows."""
        try:
            style = ttk.Style()
            style.theme_use("clam")

            # Estilo personalizado Cyber para Treeviews
            style.configure("Cyber.Treeview",
                background="#090d16",
                fieldbackground="#090d16",
                foreground="#f8fafc",
                rowheight=26,
                borderwidth=0,
                relief="flat",
                font=("Segoe UI", 9)
            )

            # Estilo personalizado Cyber para encabezados
            style.configure("Cyber.Treeview.Heading",
                background="#0f172a",
                foreground="#38bdf8",
                relief="flat",
                borderwidth=0,
                font=("Segoe UI", 9, "bold")
            )

            style.map("Cyber.Treeview.Heading",
                background=[('active', '#1e293b')],
                foreground=[('active', '#ffffff')]
            )

            style.map("Cyber.Treeview",
                background=[('selected', '#1e293b')],
                foreground=[('selected', '#38bdf8')]
            )

            # Estilo personalizado Cyber para Scrollbars verticales
            style.configure("Cyber.Vertical.TScrollbar",
                gripcount=0,
                background="#1e293b",
                darkcolor="#1e293b",
                lightcolor="#1e293b",
                troughcolor="#090d16",
                bordercolor="#090d16",
                arrowcolor="#64748b",
                arrowsize=10,
                relief="flat"
            )

            style.map("Cyber.Vertical.TScrollbar",
                background=[('active', '#334155'), ('pressed', '#475569')],
                arrowcolor=[('active', '#38bdf8'), ('pressed', '#38bdf8')]
            )
        except Exception as e:
            print(f"Aviso configurando estilos TTK: {e}")

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        header_frame.pack(fill="x", padx=16, pady=(14, 8))

        # Título y Logo
        title_group = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_group.pack(side="left", padx=16, pady=10)

        icon_label = ctk.CTkLabel(title_group, text="⚡", font=ctk.CTkFont(size=24))
        icon_label.pack(side="left", padx=(0, 8))

        title_text_frame = ctk.CTkFrame(title_group, fg_color="transparent")
        title_text_frame.pack(side="left")

        app_title = ctk.CTkLabel(title_text_frame, text="PIBOT TRADING TERMINAL", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_ACCENT_CYAN)
        app_title.pack(anchor="w")

        app_subtitle = ctk.CTkLabel(title_text_frame, text="Motor Cuantitativo Híbrido • PocketOption & Alpaca Markets", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        app_subtitle.pack(anchor="w")

        # Botones de Acción y Control
        btn_group = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_group.pack(side="right", padx=16, pady=10)

        # Reloj Digital & Fecha
        clock_box = ctk.CTkFrame(btn_group, fg_color="transparent")
        clock_box.pack(side="left", padx=(0, 16))

        self.clock_label = ctk.CTkLabel(clock_box, text="00:00:00", font=ctk.CTkFont(family="Consolas", size=15, weight="bold"), text_color=COLOR_TEXT_MAIN)
        self.clock_label.pack(anchor="e")

        self.clock_date_label = ctk.CTkLabel(clock_box, text=datetime.now().strftime("%d %b %Y"), font=ctk.CTkFont(family="Consolas", size=10), text_color=COLOR_TEXT_MUTED)
        self.clock_date_label.pack(anchor="e")

        # Botón Start / Stop
        self.btn_toggle_bot = ctk.CTkButton(
            btn_group,
            text="🔴 DETENER BOT" if gui_bridge.is_running else "🟢 INICIAR BOT",
            font=ctk.CTkFont(family="Outfit", size=12, weight="bold"),
            fg_color="#dc2626" if gui_bridge.is_running else "#10b981",
            hover_color="#b91c1c" if gui_bridge.is_running else "#059669",
            width=135,
            height=36,
            corner_radius=8,
            command=self._toggle_bot_execution
        )
        self.btn_toggle_bot.pack(side="left", padx=5)

        # Botón Reset Sesión
        self.btn_reset_session = ctk.CTkButton(
            btn_group,
            text="🔄 RESET SESIÓN",
            font=ctk.CTkFont(family="Outfit", size=12, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#f9fafb",
            width=130,
            height=36,
            corner_radius=8,
            command=self._reset_daily_session
        )
        self.btn_reset_session.pack(side="left", padx=5)

        # Botón Reinicio Motor
        self.btn_restart_motor = ctk.CTkButton(
            btn_group,
            text="⚡ REINICIAR MOTOR",
            font=ctk.CTkFont(family="Outfit", size=12, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#f9fafb",
            width=145,
            height=36,
            corner_radius=8,
            command=self._restart_engine
        )
        self.btn_restart_motor.pack(side="left", padx=5)

    def _build_nav_bar(self):
        """Barra de navegación principal para alternar entre Operativa Real y Laboratorio Paper."""
        nav_container = ctk.CTkFrame(self, fg_color="transparent")
        nav_container.pack(fill="x", padx=16, pady=(0, 4))

        self.btn_nav_real = ctk.CTkButton(
            nav_container,
            text="💼 OPERATIVA REAL",
            font=ctk.CTkFont(family="Outfit", size=12, weight="bold"),
            fg_color=COLOR_ACCENT_CYAN,
            text_color="#000000",
            hover_color="#38bdf8",
            height=32,
            corner_radius=8,
            command=self._switch_to_real_view
        )
        self.btn_nav_real.pack(side="left", padx=(0, 6))

        self.btn_nav_paper = ctk.CTkButton(
            nav_container,
            text="🧪 LABORATORIO PAPER TRADING",
            font=ctk.CTkFont(family="Outfit", size=12, weight="bold"),
            fg_color="#1e293b",
            text_color="#9ca3af",
            hover_color="#334155",
            height=32,
            corner_radius=8,
            command=self._switch_to_paper_view
        )
        self.btn_nav_paper.pack(side="left", padx=6)

    def _build_kpi_cards(self, parent=None):
        p = parent or self
        kpi_container = ctk.CTkFrame(p, fg_color="transparent")
        kpi_container.pack(fill="x", padx=16, pady=6)
        kpi_container.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")

        # Card 1: Balance PocketOption
        card1 = ctk.CTkFrame(kpi_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card1.grid(row=0, column=0, padx=(0, 6), sticky="nsew", ipady=6)
        ctk.CTkLabel(card1, text="SALDO POCKETOPTION", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(8, 0))
        # Frame for balance + pct
        bal_frame1 = ctk.CTkFrame(card1, fg_color="transparent")
        bal_frame1.pack(fill="x", padx=14)
        
        self.lbl_po_balance = ctk.CTkLabel(bal_frame1, text="$0.00 USD", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_ACCENT_CYAN)
        self.lbl_po_balance.pack(side="left")
        
        self.lbl_po_pct = ctk.CTkLabel(bal_frame1, text="(0.0%)", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_MUTED)
        self.lbl_po_pct.pack(side="left", padx=(8, 0), pady=(4, 0))
        self.lbl_po_sub = ctk.CTkLabel(card1, text="Cuenta Real Activa", font=ctk.CTkFont(size=11), text_color=COLOR_ACCENT_GREEN)
        self.lbl_po_sub.pack(anchor="w", padx=14, pady=(0, 6))

        # Card 2: Saldo Alpaca
        card2 = ctk.CTkFrame(kpi_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card2.grid(row=0, column=1, padx=6, sticky="nsew", ipady=6)
        ctk.CTkLabel(card2, text="EQUITY ALPACA", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(8, 0))
        # Frame for balance + pct
        bal_frame2 = ctk.CTkFrame(card2, fg_color="transparent")
        bal_frame2.pack(fill="x", padx=14)
        
        self.lbl_alpaca_balance = ctk.CTkLabel(bal_frame2, text="$0.00 USD", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_ACCENT_PURPLE)
        self.lbl_alpaca_balance.pack(side="left")
        
        self.lbl_alpaca_pct = ctk.CTkLabel(bal_frame2, text="(0.0%)", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_TEXT_MUTED)
        self.lbl_alpaca_pct.pack(side="left", padx=(8, 0), pady=(4, 0))
        self.lbl_alpaca_sub = ctk.CTkLabel(card2, text="Acciones Wall Street", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_alpaca_sub.pack(anchor="w", padx=14, pady=(0, 6))

        # Card 3: PnL Diario
        card3 = ctk.CTkFrame(kpi_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card3.grid(row=0, column=2, padx=6, sticky="nsew", ipady=6)
        ctk.CTkLabel(card3, text="PnL REALIZADO HOY", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(8, 0))
        self.lbl_pnl_today = ctk.CTkLabel(card3, text="+$0.00 USD", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_ACCENT_GREEN)
        self.lbl_pnl_today.pack(anchor="w", padx=14)
        self.lbl_pnl_sub = ctk.CTkLabel(card3, text="Sesión Actual", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_pnl_sub.pack(anchor="w", padx=14, pady=(0, 6))

        # Card 4: Score & Win Rate
        card4 = ctk.CTkFrame(kpi_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card4.grid(row=0, column=3, padx=(6, 0), sticky="nsew", ipady=6)
        ctk.CTkLabel(card4, text="SCORE & WIN RATE", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=14, pady=(8, 0))
        self.lbl_score_wr = ctk.CTkLabel(card4, text="0W - 0L (0%)", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLOR_TEXT_MAIN)
        self.lbl_score_wr.pack(anchor="w", padx=14)
        self.lbl_score_sub = ctk.CTkLabel(card4, text="Límite: 3 Wins / 3 Losses", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_score_sub.pack(anchor="w", padx=14, pady=(0, 6))

    def _build_quick_commands_bar(self, parent=None):
        p = parent or self
        cmd_bar = ctk.CTkFrame(p, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        cmd_bar.pack(fill="x", padx=16, pady=(0, 6))

        bar_inner = ctk.CTkFrame(cmd_bar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=12, pady=6)

        lbl_tag = ctk.CTkLabel(
            bar_inner,
            text="⚡ ACCIONES RÁPIDAS:",
            font=ctk.CTkFont(family="Outfit", size=11, weight="bold"),
            text_color=COLOR_ACCENT_CYAN
        )
        lbl_tag.pack(side="left", padx=(4, 8))

        commands = [
            ("🧪 Paper Lab", "GOTO_PAPER", "#0284c7", "#0369a1"),
            ("📄 Reporte Info", "LARGE_REPORT", "#0284c7", "#0369a1"),
            ("📊 Gráfico PnL", "LARGE_CHART", "#7c3aed", "#6d28d9"),
            ("🎥 Videos Primo", "OPEN_VIDEOS", "#e11d48", "#be123c"),
            ("🟢 PocketOption", "/po", "#064e3b", "#047857"),
            ("🔸 Alpaca", "/alpaca", "#4c1d95", "#6d28d9"),
            ("📅 Diario Trades", "/daily", "#1e293b", "#334155"),
            ("📑 Exportar Excel", "/excel", "#14532d", "#15803d"),
            ("🧹 Limpiar RAM", "/limpiar_ram", "#78350f", "#b45309"),
            ("💻 Recursos PC", "/recursos", "#1e293b", "#334155"),
        ]

        for text, cmd, fg, hover in commands:
            if cmd == "LARGE_REPORT":
                cmd_action = lambda: self._show_large_report_window()
            elif cmd == "LARGE_CHART":
                cmd_action = lambda: self._show_large_chart_window("both")
            elif cmd == "GOTO_PAPER":
                cmd_action = lambda: self._switch_to_paper_view()
            elif cmd == "OPEN_VIDEOS":
                cmd_action = lambda: self._show_videos_window()
            else:
                cmd_action = lambda c=cmd: self._on_send_command(c)

            btn = ctk.CTkButton(
                bar_inner,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=fg,
                hover_color=hover,
                height=28,
                corner_radius=6,
                command=cmd_action
            )
            btn.pack(side="left", padx=3)

    def _build_status_section(self, parent=None):
        p = parent or self
        status_container = ctk.CTkFrame(p, fg_color="transparent")
        status_container.pack(fill="x", padx=16, pady=6)
        status_container.grid_columnconfigure((0, 1), weight=1, uniform="status")

        # PocketOption Status Card
        self.card_po_status = ctk.CTkFrame(status_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        self.card_po_status.grid(row=0, column=0, padx=(0, 6), sticky="nsew", ipady=6)

        po_header = ctk.CTkFrame(self.card_po_status, fg_color="transparent")
        po_header.pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(po_header, text="ESTADO POCKETOPTION (Miriam Molina MM)", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        self.badge_po_state = ctk.CTkLabel(po_header, text="DETENIDO", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ffffff", fg_color="#374151", corner_radius=6, padx=8, pady=2)
        self.badge_po_state.pack(side="right")

        self.lbl_po_details = ctk.CTkLabel(self.card_po_status, text="Inversión base: $1.00 USD • Soros Nivel 1 • Whitelist activa (20 pares)", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_po_details.pack(anchor="w", padx=14, pady=(0, 4))

        self.lbl_po_reason = ctk.CTkLabel(self.card_po_status, text="Esperando inicio del bot.", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_ACCENT_AMBER)
        self.lbl_po_reason.pack(anchor="w", padx=14, pady=(0, 6))

        # Alpaca Status Card
        self.card_alpaca_status = ctk.CTkFrame(status_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        self.card_alpaca_status.grid(row=0, column=1, padx=(6, 0), sticky="nsew", ipady=6)

        alpaca_header = ctk.CTkFrame(self.card_alpaca_status, fg_color="transparent")
        alpaca_header.pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(alpaca_header, text="ESTADO ALPACA (Wall Street)", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        self.badge_alpaca_state = ctk.CTkLabel(alpaca_header, text="MERCADO CERRADO", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ffffff", fg_color="#1e293b", corner_radius=6, padx=8, pady=2)
        self.badge_alpaca_state.pack(side="right")

        self.lbl_alpaca_details = ctk.CTkLabel(self.card_alpaca_status, text="Horario operativo: Lunes a Viernes 09:00 a 17:30 hs (UTC-3)", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_alpaca_details.pack(anchor="w", padx=14, pady=(0, 4))

        self.lbl_alpaca_reason = ctk.CTkLabel(self.card_alpaca_status, text="0 Posiciones abiertas • Sesión pausada fuera de hora.", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_alpaca_reason.pack(anchor="w", padx=14, pady=(0, 6))

    def _build_main_split(self, parent=None):
        p = parent or self
        split_container = ctk.CTkFrame(p, fg_color="transparent")
        split_container.pack(fill="both", expand=True, padx=16, pady=6)
        split_container.grid_columnconfigure(0, weight=4)
        split_container.grid_columnconfigure(1, weight=5)
        split_container.grid_rowconfigure(0, weight=1)

        # Columna Izquierda: Tabla de Operaciones de Hoy (Real)
        table_card = ctk.CTkFrame(split_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        table_card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        tbl_header = ctk.CTkFrame(table_card, fg_color="transparent")
        tbl_header.pack(fill="x", padx=14, pady=(10, 6))
        
        ctk.CTkLabel(tbl_header, text="OPERACIONES DE HOY (REAL)", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        
        btn_refresh_trades = ctk.CTkButton(tbl_header, text="Refrescar", width=70, height=24, font=ctk.CTkFont(size=11), fg_color="#374151", command=self._refresh_trades_table)
        btn_refresh_trades.pack(side="right")

        # Treeview de Operaciones (ttk con tema dark adaptado)
        tree_frame = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
            background="#111827",
            foreground="#f9fafb",
            fieldbackground="#111827",
            rowheight=26,
            font=("Consolas", 9)
        )
        style.configure("Treeview.Heading",
            background="#1f2937",
            foreground="#9ca3af",
            font=("Outfit", 9, "bold")
        )
        style.map("Treeview", background=[("selected", "#374151")])

        columns = ("time", "pair", "tf", "dir", "result", "profit")
        self.trades_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse", style="Cyber.Treeview")
        self.trades_tree.heading("time", text="Hora")
        self.trades_tree.heading("pair", text="Activo")
        self.trades_tree.heading("tf", text="TF")
        self.trades_tree.heading("dir", text="Dir")
        self.trades_tree.heading("result", text="Resultado")
        self.trades_tree.heading("profit", text="PnL")

        self.trades_tree.column("time", width=65, anchor="center")
        self.trades_tree.column("pair", width=95, anchor="w")
        self.trades_tree.column("tf", width=40, anchor="center")
        self.trades_tree.column("dir", width=45, anchor="center")
        self.trades_tree.column("result", width=70, anchor="center")
        self.trades_tree.column("profit", width=65, anchor="e")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.trades_tree.yview, style="Cyber.Vertical.TScrollbar")
        self.trades_tree.configure(yscrollcommand=tree_scroll.set)

        self.trades_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Configurar tags de color para la tabla
        self.trades_tree.tag_configure("win", foreground="#10b981")
        self.trades_tree.tag_configure("draw", foreground="#9ca3af")
        self.trades_tree.tag_configure("loss", foreground="#ef4444")
        self.trades_tree.tag_configure("pending", foreground="#f59e0b")

        # Columna Derecha: Terminal de Logs
        log_card = ctk.CTkFrame(split_container, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        log_card.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.pack(fill="x", padx=14, pady=(10, 6))
        self.lbl_telemetry_title = ctk.CTkLabel(log_header, text="CONSOLA DE TELEMETRÍA", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_TEXT_MAIN)
        self.lbl_telemetry_title.pack(side="left")

        btn_clear_top = ctk.CTkButton(
            log_header, text="Limpiar", width=60, height=24, font=ctk.CTkFont(size=11),
            fg_color="#374151", hover_color="#4b5563",
            command=self._clear_logs
        )
        btn_clear_top.pack(side="right")

        # --- VISTA 1: CONSOLA DE LOGS Y CLI ---
        self.console_container = ctk.CTkFrame(log_card, fg_color="transparent")
        self.console_container.pack(fill="both", expand=True, padx=0, pady=0)

        # Textbox de Log
        self.log_text = ctk.CTkTextbox(
            self.console_container,
            fg_color="#090d16",
            text_color="#f9fafb",
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word",
            corner_radius=8
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Configurar tags de color para el texto
        self.log_text.tag_config("WIN", foreground="#10b981")
        self.trades_tree.tag_configure("draw", foreground="#9ca3af")
        self.log_text.tag_config("LOSS", foreground="#ef4444")
        self.log_text.tag_config("WARN", foreground="#f59e0b")
        self.log_text.tag_config("ALPACA", foreground="#a78bfa")
        self.log_text.tag_config("PO", foreground="#00d2ff")
        self.log_text.tag_config("INFO", foreground="#9ca3af")

        # Entrada interactiva de comandos (CLI)
        cmd_input_frame = ctk.CTkFrame(self.console_container, fg_color="transparent")
        cmd_input_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.cmd_entry = ctk.CTkEntry(
            cmd_input_frame,
            placeholder_text="Escribí un comando (ej: /info, /balance, /chart, /excel, /po, /limpiar_ram)...",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#090d16",
            border_color="#374151",
            text_color="#f9fafb",
            height=30
        )
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cmd_entry.bind("<Return>", lambda e: self._on_send_command())

        self.btn_send_cmd = ctk.CTkButton(
            cmd_input_frame,
            text="▶ Enviar",
            width=75,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1f2937",
            hover_color="#374151",
            command=self._on_send_command
        )
        self.btn_send_cmd.pack(side="right")

        # Barra inferior del Log
        log_footer = ctk.CTkFrame(self.console_container, fg_color="transparent")
        log_footer.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkCheckBox(log_footer, text="Auto-scroll", variable=self.auto_scroll, font=ctk.CTkFont(size=11), width=16, height=16).pack(side="left")
        ctk.CTkButton(log_footer, text="Limpiar Consola", width=95, height=24, font=ctk.CTkFont(size=11), fg_color="#374151", command=self._clear_logs).pack(side="right")

        # --- VISTA 2: GRÁFICO LINEAL DINÁMICO NATIVO ---
        self.chart_view_container = ctk.CTkFrame(log_card, fg_color="transparent")
        self.chart_canvas = None
        self.current_chart_broker = "both"

        chart_nav = ctk.CTkFrame(self.chart_view_container, fg_color="transparent")
        chart_nav.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(chart_nav, text="VISTA:", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))

        self.btn_chart_both = ctk.CTkButton(chart_nav, text="🏆 Dual", width=55, height=22, font=ctk.CTkFont(size=10), fg_color="#1e293b", hover_color="#334155", command=lambda: self._render_dynamic_chart("both"))
        self.btn_chart_both.pack(side="left", padx=2)

        self.btn_chart_po = ctk.CTkButton(chart_nav, text="🟢 PO", width=50, height=22, font=ctk.CTkFont(size=10), fg_color="#064e3b", hover_color="#047857", command=lambda: self._render_dynamic_chart("pocketoption"))
        self.btn_chart_po.pack(side="left", padx=2)

        self.btn_chart_alpaca = ctk.CTkButton(chart_nav, text="🔸 Alpaca", width=62, height=22, font=ctk.CTkFont(size=10), fg_color="#4c1d95", hover_color="#6d28d9", command=lambda: self._render_dynamic_chart("alpaca"))
        self.btn_chart_alpaca.pack(side="left", padx=2)

        self.btn_chart_refresh = ctk.CTkButton(chart_nav, text="🔄 Refrescar", width=75, height=22, font=ctk.CTkFont(size=10), fg_color="#374151", hover_color="#4b5563", command=lambda: self._render_dynamic_chart(self.current_chart_broker))
        self.btn_chart_refresh.pack(side="left", padx=6)

        self.btn_chart_back = ctk.CTkButton(chart_nav, text="🔙 Volver a Consola", width=115, height=22, font=ctk.CTkFont(size=10, weight="bold"), fg_color="#374151", hover_color="#4b5563", command=lambda: self._show_console_view("ALL"))
        self.btn_chart_back.pack(side="right")

        self.chart_canvas_frame = ctk.CTkFrame(self.chart_view_container, fg_color="#090d16", corner_radius=8)
        self.chart_canvas_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    def _build_footer(self):
        footer_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, height=32, corner_radius=0)
        footer_frame.pack(fill="x", side="bottom")

        self.lbl_footer_status = ctk.CTkLabel(footer_frame, text="🟢 PocketOption Conectado • Watchdog de red activo (0 congelamientos)", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        self.lbl_footer_status.pack(side="left", padx=16)

        self.lbl_sys_metrics = ctk.CTkLabel(footer_frame, text="CPU: 0% | RAM: 0% | v2.4.1", font=ctk.CTkFont(size=11, family="Consolas"), text_color=COLOR_TEXT_MUTED)
        self.lbl_sys_metrics.pack(side="right", padx=16)

    # -------------------------------------------------------------------------
    # GESTIÓN DE EVENTOS Y ACCIONES
    # -------------------------------------------------------------------------
    def _toggle_bot_execution(self):
        if not gui_bridge.is_running:
            started = gui_bridge.start_bot_process("config.json")
            if started:
                self.btn_toggle_bot.configure(text="🔴 DETENER BOT", fg_color="#dc2626", hover_color="#b91c1c")
                self.lbl_footer_status.configure(text="🟢 PocketOption Conectado • Motor activo", text_color="#10b981")
                if hasattr(self, 'badge_paper_motor'):
                    self.badge_paper_motor.configure(text="🟢 Motor activo", text_color="#10b981")
        else:
            gui_bridge.stop_bot_process()
            self.btn_toggle_bot.configure(text="🟢 INICIAR BOT", fg_color="#10b981", hover_color="#059669")
            self.lbl_footer_status.configure(text="⚪ PocketOption Desconectado • Motor detenido", text_color=COLOR_TEXT_MUTED)
            if hasattr(self, 'badge_paper_motor'):
                self.badge_paper_motor.configure(text="🔴 Motor detenido", text_color="#ef4444")

    def _reset_daily_session(self):
        ok = gui_bridge.reset_daily_session()
        if ok:
            messagebox.showinfo("Sesión Reiniciada", "La sesión diaria de PocketOption se reinició a 0 pérdidas y 0 ganancias.\n\nEl bot vuelve a buscar oportunidades en el mercado.")
            self._update_telemetry_tick()
            self._refresh_trades_table()

    def _restart_engine(self):
        gui_bridge.restart_bot()
        messagebox.showinfo("Reinicio en Caliente", "Se envió la señal de reinicio (restart.signal).\nEl supervisor relanzará el proceso en 2 segundos.")

    def _on_send_command(self, preset_cmd=None):
        cmd = preset_cmd if preset_cmd else self.cmd_entry.get().strip()
        if not cmd:
            return
        if not preset_cmd:
            self.cmd_entry.delete(0, "end")

        cmd_lower = cmd.lower().strip()
        if cmd_lower in ["/info", "/stats", "/performance", "/reporte"]:
            self._show_large_report_window()
            return
        elif cmd_lower in ["/chart", "/grafico"]:
            self._show_large_chart_window("both")
            return
        
        # Ejecutar en hilo de fondo para no bloquear la interfaz gráfica
        import threading
        threading.Thread(target=gui_bridge.execute_command, args=(cmd,), daemon=True).start()

    def _show_large_chart_window(self, default_broker="both"):
        """Abre una ventana emergente grande (980x680) fuera de la consola para ver los gráficos de PnL."""
        if hasattr(self, 'win_chart_popup') and self.win_chart_popup is not None and self.win_chart_popup.winfo_exists():
            self.win_chart_popup.lift()
            self.win_chart_popup.focus()
            return

        popup = ctk.CTkToplevel(self)
        self.win_chart_popup = popup
        popup.title("📊 Gráfico de Rendimiento en Tiempo Real | Dual Broker")
        popup.geometry("980x680")
        popup.minsize(800, 500)
        popup.configure(fg_color=COLOR_BG_DARK)

        # Header nav
        nav = ctk.CTkFrame(popup, fg_color=COLOR_CARD_BG, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        nav.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(nav, text="VISTA DE GRÁFICO PnL:", font=ctk.CTkFont(family="Outfit", size=13, weight="bold"), text_color=COLOR_ACCENT_CYAN).pack(side="left", padx=14)

        current_broker = tk.StringVar(value=default_broker)

        canvas_frame = ctk.CTkFrame(popup, fg_color="#090d16", corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        canvas_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def render(b_type):
            current_broker.set(b_type)
            for widget in canvas_frame.winfo_children():
                widget.destroy()

            try:
                fig = gui_bridge.generate_linear_chart_figure(broker=b_type, figsize=(9.0, 5.0))
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                chart_canvas = FigureCanvasTkAgg(fig, master=canvas_frame)
                chart_canvas.draw()
                chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
            except Exception as e:
                gui_bridge.log(f"Error cargando gráfico modal: {e}", "LOSS")

        ctk.CTkButton(nav, text="🏆 Dual General", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#1e293b", hover_color="#334155", width=110, command=lambda: render("both")).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="🟢 PocketOption", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#064e3b", hover_color="#047857", width=110, command=lambda: render("pocketoption")).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="🔸 Alpaca", font=ctk.CTkFont(size=11, weight="bold"), fg_color="#4c1d95", hover_color="#6d28d9", width=110, command=lambda: render("alpaca")).pack(side="left", padx=4)
        ctk.CTkButton(nav, text="🔄 Refrescar", font=ctk.CTkFont(size=11), fg_color="#374151", width=95, command=lambda: render(current_broker.get())).pack(side="left", padx=8)

        ctk.CTkButton(nav, text="❌ Cerrar", font=ctk.CTkFont(size=11), fg_color="#ef4444", hover_color="#dc2626", width=80, command=popup.destroy).pack(side="right", padx=14)

        render(default_broker)

    def _show_videos_window(self):
        if hasattr(self, 'win_videos_popup') and self.win_videos_popup is not None and self.win_videos_popup.winfo_exists():
            self.win_videos_popup.lift()
            self.win_videos_popup.focus()
            return

        popup = ctk.CTkToplevel(self)
        self.win_videos_popup = popup
        popup.title("🎥 Videos Primo - Bandeja de Entrada")
        popup.geometry("640x540")
        popup.minsize(580, 420)
        popup.configure(fg_color=COLOR_BG_DARK)
        
        nav = ctk.CTkFrame(popup, fg_color=COLOR_CARD_BG, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        nav.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(nav, text="ARCHIVOS Y VIDEOS RECIBIDOS", font=ctk.CTkFont(family="Outfit", size=13, weight="bold"), text_color=COLOR_ACCENT_CYAN).pack(side="left", padx=14)
        ctk.CTkButton(nav, text="❌ Cerrar", font=ctk.CTkFont(size=11), fg_color="#ef4444", hover_color="#dc2626", width=80, command=popup.destroy).pack(side="right", padx=14)

        container = ctk.CTkScrollableFrame(popup, fg_color="#090d16", corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        container.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        lbl_status = ctk.CTkLabel(container, text="Conectando con Gmail... por favor espera.", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED)
        lbl_status.pack(pady=20)

        def fetch_emails():
            try:
                from email_handler import get_emails_with_videos, download_video
                emails, err = get_emails_with_videos()
                if not popup.winfo_exists():
                    return
                self.after(0, lambda em=emails, er=err, dv=download_video: render_emails(em, er, dv))
            except Exception as e:
                err_msg = str(e)
                if not popup.winfo_exists():
                    return
                self.after(0, lambda msg=err_msg: lbl_status.configure(text=f"Error: {msg}", text_color=COLOR_ACCENT_RED) if lbl_status.winfo_exists() else None)

        def on_download(email_id, filename, drive_url, btn, status_lbl, download_video, prog_bar):
            if not btn.winfo_exists():
                return
            btn.configure(state="disabled", text="Descargando...")
            prog_bar.pack(pady=(4, 0))
            prog_bar.start()
            status_lbl.configure(text="Descargando...", text_color=COLOR_TEXT_MAIN)
            
            def do_dl():
                success, res = download_video(email_id, filename, drive_url)
                if not popup.winfo_exists():
                    return
                if success:
                    self.after(0, lambda: [
                        btn.configure(text="✅ Listo") if btn.winfo_exists() else None,
                        prog_bar.stop() if prog_bar.winfo_exists() else None,
                        prog_bar.pack_forget() if prog_bar.winfo_exists() else None,
                        status_lbl.configure(text=f"Guardado en: {res}", text_color=COLOR_ACCENT_GREEN) if status_lbl.winfo_exists() else None
                    ])
                else:
                    self.after(0, lambda: [
                        btn.configure(state="normal", text="Reintentar") if btn.winfo_exists() else None,
                        prog_bar.stop() if prog_bar.winfo_exists() else None,
                        prog_bar.pack_forget() if prog_bar.winfo_exists() else None,
                        status_lbl.configure(text=res, text_color=COLOR_ACCENT_RED) if status_lbl.winfo_exists() else None
                    ])
            import threading
            threading.Thread(target=do_dl, daemon=True).start()

        def render_emails(emails, err, download_video_func):
            if not popup.winfo_exists() or not container.winfo_exists():
                return
            if err:
                if lbl_status.winfo_exists():
                    lbl_status.configure(text=str(err), text_color=COLOR_ACCENT_RED)
                return
            if lbl_status.winfo_exists():
                lbl_status.destroy()
            if not emails:
                ctk.CTkLabel(container, text="No se encontraron correos con archivos adjuntos.", text_color=COLOR_TEXT_MUTED).pack(pady=20)
                return

            for email in emails:
                if not container.winfo_exists():
                    break
                card = ctk.CTkFrame(container, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
                card.pack(fill="x", pady=6, padx=8)
                
                header = ctk.CTkFrame(card, fg_color="transparent")
                header.pack(fill="x", padx=10, pady=8)
                
                subj = email.get("subject", "(Sin Asunto)")
                date = email.get("date", "")
                ctk.CTkLabel(header, text=subj, font=ctk.CTkFont(weight="bold", size=12), text_color=COLOR_TEXT_MAIN).pack(side="left")
                ctk.CTkLabel(header, text=date, font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="right")
                
                for att in email.get("attachments", []):
                    # Soporte para dict {"filename": fn, "is_drive": bool, "drive_url": url} y string legacy
                    if isinstance(att, dict):
                        fn = att.get("filename", "")
                        drive_url = att.get("drive_url", "")
                    else:
                        fn = str(att)
                        drive_url = ""

                    att_frame = ctk.CTkFrame(card, fg_color="#1f2937", corner_radius=6)
                    att_frame.pack(fill="x", padx=10, pady=(0, 8))
                    
                    # 1. Empacar la columna derecha PRIMERO (fija el botón de descarga a la derecha)
                    right_col = ctk.CTkFrame(att_frame, fg_color="transparent")
                    right_col.pack(side="right", padx=10, pady=6)

                    status_lbl = ctk.CTkLabel(right_col, text="", font=ctk.CTkFont(size=10))
                    status_lbl.pack(side="right", padx=6)

                    dl_container = ctk.CTkFrame(right_col, fg_color="transparent")
                    dl_container.pack(side="right")
                    
                    btn_dl = ctk.CTkButton(dl_container, text="Descargar", width=80, height=24, fg_color="#3b82f6", hover_color="#2563eb", font=ctk.CTkFont(size=11, weight="bold"))
                    btn_dl.pack()
                    prog_bar = ctk.CTkProgressBar(dl_container, width=80, height=4, mode="indeterminate", fg_color=COLOR_CARD_BORDER, progress_color="#3b82f6")
                    btn_dl.configure(command=lambda e=email["id"], f=fn, u=drive_url, b=btn_dl, s=status_lbl, f2=download_video_func, p=prog_bar: on_download(e, f, u, b, s, f2, p))

                    # 2. Icono representativo del archivo (Audio, Video, Proyecto)
                    ext_lower = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''

                    if ext_lower in {'mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'}:
                        icon = "🎵 "
                    elif ext_lower in {'mp4', 'mkv', 'avi', 'mov', 'wmv', 'webm'}:
                        icon = "🎬 "
                    elif ext_lower in {'wfp', 'prproj'}:
                        icon = "🎞️ "
                    else:
                        icon = "📁 "

                    # 3. Formatear nombre visual si es muy largo para que no desborde
                    disp_text = fn
                    if len(disp_text) > 48:
                        disp_text = disp_text[:28] + "..." + disp_text[-16:]

                    lbl_att = ctk.CTkLabel(att_frame, text=f"{icon}{disp_text}", font=ctk.CTkFont(size=11), anchor="w")
                    lbl_att.pack(side="left", fill="x", expand=True, padx=10, pady=6)

        import threading
        threading.Thread(target=fetch_emails, daemon=True).start()

    def _show_large_report_window(self):
        """Abre una ventana emergente grande estilo Telegram con el reporte formateado + el gráfico incorporado."""
        if hasattr(self, 'win_report_popup') and self.win_report_popup is not None and self.win_report_popup.winfo_exists():
            self.win_report_popup.lift()
            self.win_report_popup.focus()
            return

        popup = ctk.CTkToplevel(self)
        self.win_report_popup = popup
        popup.title("📄 Reporte Completo de Operativa (Telegram Style)")
        popup.geometry("1020x700")
        popup.minsize(850, 550)
        popup.configure(fg_color=COLOR_BG_DARK)

        # Header bar
        header_bar = ctk.CTkFrame(popup, fg_color=COLOR_CARD_BG, corner_radius=10, border_width=1, border_color=COLOR_CARD_BORDER)
        header_bar.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(header_bar, text="📄 REPORTE DE ESTRATEGIA Y RENDIMIENTO EN VIVO", font=ctk.CTkFont(family="Outfit", size=14, weight="bold"), text_color=COLOR_ACCENT_CYAN).pack(side="left", padx=14)

        ctk.CTkButton(header_bar, text="❌ Cerrar", font=ctk.CTkFont(size=11), fg_color="#ef4444", hover_color="#dc2626", width=80, command=popup.destroy).pack(side="right", padx=14)

        # Split container: 30% texto compacto a la izquierda, 70% gráfico expandido a la derecha
        body_split = ctk.CTkFrame(popup, fg_color="transparent")
        body_split.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        body_split.grid_columnconfigure(0, weight=1)
        body_split.grid_columnconfigure(1, weight=3)
        body_split.grid_rowconfigure(0, weight=1)

        # Left Column: Telegram Text Card (Compacto)
        text_card = ctk.CTkFrame(body_split, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER, width=310)
        text_card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        ctk.CTkLabel(text_card, text="📊 DETALLE EN VIVO", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 4))

        report_textbox = ctk.CTkTextbox(text_card, fg_color="#090d16", text_color="#f9fafb", font=ctk.CTkFont(family="Consolas", size=11), wrap="word", corner_radius=8)
        report_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Right Column: Embedded Chart Card (Amplio cubriendo todo el ancho)
        chart_card = ctk.CTkFrame(body_split, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        chart_card.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        chart_header = ctk.CTkFrame(chart_card, fg_color="transparent")
        chart_header.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(chart_header, text="📈 RENDIMIENTO Y OPERACIONES DEL DÍA", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_ACCENT_CYAN).pack(side="left")

        # Controles de navegación diaria (Día anterior / siguiente)
        from datetime import timedelta, date
        nav_date_frame = ctk.CTkFrame(chart_header, fg_color="transparent")
        nav_date_frame.pack(side="right")

        # Selector de Broker para el gráfico (Ambos / PocketOption / Alpaca)
        self.report_broker_filter = "both"
        broker_filter_frame = ctk.CTkFrame(chart_header, fg_color="transparent")
        broker_filter_frame.pack(side="right", padx=(0, 15))

        def set_broker_filter(b_mode):
            self.report_broker_filter = b_mode
            btn_filter_both.configure(
                fg_color=COLOR_ACCENT_CYAN if b_mode == "both" else "#1f2937",
                text_color="#000000" if b_mode == "both" else "#9ca3af"
            )
            btn_filter_po.configure(
                fg_color="#00ff88" if b_mode == "po" else "#1f2937",
                text_color="#000000" if b_mode == "po" else "#9ca3af"
            )
            btn_filter_al.configure(
                fg_color="#ff9900" if b_mode == "alpaca" else "#1f2937",
                text_color="#000000" if b_mode == "alpaca" else "#9ca3af"
            )
            load_report_data(self.report_view_date)

        btn_filter_both = ctk.CTkButton(
            broker_filter_frame, text="Ambos", width=55, height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=COLOR_ACCENT_CYAN, text_color="#000000",
            hover_color="#00b4db", command=lambda: set_broker_filter("both")
        )
        btn_filter_both.pack(side="left", padx=2)

        btn_filter_po = ctk.CTkButton(
            broker_filter_frame, text="🟢 PocketOption", width=105, height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1f2937", text_color="#9ca3af",
            hover_color="#059669", command=lambda: set_broker_filter("po")
        )
        btn_filter_po.pack(side="left", padx=2)

        btn_filter_al = ctk.CTkButton(
            broker_filter_frame, text="🔸 Alpaca", width=75, height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1f2937", text_color="#9ca3af",
            hover_color="#d97706", command=lambda: set_broker_filter("alpaca")
        )
        btn_filter_al.pack(side="left", padx=2)

        self.report_view_date = datetime.now().date()

        def on_change_day(delta):
            today = datetime.now().date()
            new_date = self.report_view_date + timedelta(days=delta)
            if new_date > today:
                return
            self.report_view_date = new_date

            if self.report_view_date >= today:
                btn_next.configure(state="disabled", fg_color="#1f2937", text_color="#6b7280")
                lbl_date_indicator.configure(text=f"{self.report_view_date.strftime('%d/%m/%Y')} (Hoy)")
            else:
                btn_next.configure(state="normal", fg_color="#374151", text_color="#ffffff")
                lbl_date_indicator.configure(text=f"{self.report_view_date.strftime('%d/%m/%Y')}")

            load_report_data(self.report_view_date)

        btn_prev = ctk.CTkButton(
            nav_date_frame, text="◀", width=32, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#374151", hover_color="#4b5563",
            command=lambda: on_change_day(-1)
        )
        btn_prev.pack(side="left", padx=2)

        lbl_date_indicator = ctk.CTkLabel(
            nav_date_frame,
            text=f"{self.report_view_date.strftime('%d/%m/%Y')} (Hoy)",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_date_indicator.pack(side="left", padx=6)

        btn_next = ctk.CTkButton(
            nav_date_frame, text="▶", width=32, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1f2937", text_color="#6b7280", state="disabled", hover_color="#4b5563",
            command=lambda: on_change_day(1)
        )
        btn_next.pack(side="left", padx=2)

        chart_frame = ctk.CTkFrame(chart_card, fg_color="#090d16", corner_radius=8)
        chart_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def load_report_data(target_date=None):
            t_date = target_date if target_date is not None else self.report_view_date
            is_today = (t_date == datetime.now().date())
            date_display = f"{t_date.strftime('%d/%m/%Y')} (Hoy)" if is_today else t_date.strftime('%d/%m/%Y')

            po_stat = gui_bridge.get_pocketoption_status()
            po_bal = float(po_stat.get('balance', 0.0))
            alpaca_stat = gui_bridge.get_alpaca_status()
            alpaca_bal = float(alpaca_stat.get('balance', 0.0))
            state = gui_bridge.get_session_state()
            day_trades = gui_bridge.get_trades_for_date(t_date)

            po_trades = [t for t in day_trades if t.get('broker') == 'PocketOption']
            al_trades = [t for t in day_trades if t.get('broker') == 'Alpaca']

            po_wins = sum(1 for t in po_trades if str(t.get('result')).upper() in ('WIN', '1', 'GANADA'))
            po_losses = sum(1 for t in po_trades if str(t.get('result')).upper() in ('LOSS', '0', 'PERDIDA'))
            po_total = po_wins + po_losses
            po_wr = (po_wins / po_total * 100) if po_total > 0 else 0.0
            import math
            def safe_pnl(val):
                try:
                    f = float(val)
                    return 0.0 if math.isnan(f) or math.isinf(f) else f
                except:
                    return 0.0

            po_pnl = sum(safe_pnl(t.get('profit', 0.0)) for t in po_trades)

            al_wins = sum(1 for t in al_trades if str(t.get('result')).upper() in ('WIN', '1', 'GANADA'))
            al_losses = sum(1 for t in al_trades if str(t.get('result')).upper() in ('LOSS', '0', 'PERDIDA'))
            al_total = al_wins + al_losses
            al_wr = (al_wins / al_total * 100) if al_total > 0 else 0.0
            al_pnl = sum(safe_pnl(t.get('profit', 0.0)) for t in al_trades)

            total_wins = po_wins + al_wins
            total_losses = po_losses + al_losses
            total_count = len(day_trades)
            total_wr = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0.0
            net_pnl = po_pnl + al_pnl
            total_bal = po_bal + alpaca_bal

            lines = [
                "==================================",
                "⚡ PIBOT TRADING TERMINAL - REPORTE",
                "==================================",
                f"📅 Fecha: {date_display}",
                "",
                "🟢 POCKETOPTION (Real / OTC):",
                f"   • Saldo Cuenta: ${po_bal:.2f} USD",
                f"   • Récord Día PO: {po_wins}W - {po_losses}L ({po_wr:.1f}%)",
                f"   • PnL Día PO: {po_pnl:+.2f} USD",
                f"   • Soros (MM): Nivel {state.get('compound_level', 0) + 1} (${state.get('current_amount', 1.0):.2f} USD)",
                f"   • Estado: {'ACTIVO & OPERANDO' if state.get('is_session_active', True) else 'REPOSO'}",
                "",
                "🔸 ALPACA MARKETS (Wall Street & Crypto):",
                f"   • Equity Cuenta: ${alpaca_bal:,.2f} USD",
                f"   • Récord Día Alpaca: {al_wins}W - {al_losses}L ({al_wr:.1f}%)",
                f"   • PnL Día Alpaca: {al_pnl:+.2f} USD",
                f"   • Posiciones Abiertas: {len(alpaca_stat.get('active_trades', {}))}",
                "",
                "🏆 RENDIMIENTO TOTAL DEL DÍA:",
                f"   • Total Trades: {total_count} (PO: {len(po_trades)} | Alpaca: {len(al_trades)})",
                f"   • Win Rate Total: {total_wr:.1f}% ({total_wins}W - {total_losses}L)",
                f"   • PnL Neto Total: {net_pnl:+.2f} USD",
                f"   • Capital Portafolio: ${total_bal:,.2f} USD",
                "==================================",
            ]

            active_trades = alpaca_stat.get('active_trades', {})
            if active_trades and is_today:
                lines.append("\n📈 POSICIONES EN CURSO ALPACA:")
                for sym, t in active_trades.items():
                    lines.append(f"   • {sym}: {t.get('action', 'BUY')} @ ${t.get('entry_price', 0):.2f}")

            # Filtrar lista para el detalle según selección
            display_trades = day_trades
            filter_suffix = ""
            if self.report_broker_filter in ("po", "pocketoption"):
                display_trades = po_trades
                filter_suffix = " (🟢 PocketOption)"
            elif self.report_broker_filter in ("alpaca", "al"):
                display_trades = al_trades
                filter_suffix = " (🔸 Alpaca)"

            if display_trades:
                lines.append(f"\n📋 DETALLE DE OPERACIONES{filter_suffix}:")
                for i, t in enumerate(display_trades, 1):
                    b_tag = "[PO]" if t.get('broker') == 'PocketOption' else "[ALPACA]"
                    res = str(t.get('result', 'PENDING')).upper()
                    icon = "✅" if res in ("WIN", "1", "GANADA") else ("❌" if res in ("LOSS", "0", "PERDIDA") else "⏳")
                    prof = safe_pnl(t.get('profit', 0.0))
                    pair = t.get('pair', '')
                    tf = t.get('timeframe', '')
                    dec = t.get('decision', 'BUY')
                    ts = t.get('timestamp', '')
                    lines.append(f"{i}. {b_tag} [{ts}] {pair} ({tf}) {dec} {icon} {prof:+.2f} USD")
            else:
                lines.append(f"\n📋 DETALLE DE OPERACIONES{filter_suffix}: Sin operaciones registradas.")

            report_textbox.delete("1.0", "end")
            report_textbox.insert("1.0", "\n".join(lines))

            for w in chart_frame.winfo_children():
                w.destroy()
            try:
                fig = gui_bridge.generate_today_pnl_chart_figure(
                    target_date=t_date,
                    broker=self.report_broker_filter,
                    figsize=(7.2, 4.8)
                )
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                chart_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
                chart_canvas.draw()
                chart_canvas.get_tk_widget().pack(fill="both", expand=True)
            except Exception as e:
                gui_bridge.log(f"Error renderizando gráfico en reporte: {e}", "LOSS")

        load_report_data(self.report_view_date)

    def _set_log_filter(self, tag):
        self.filter_tag = tag
        self._render_filtered_logs()

    def _show_chart_view(self, broker="both"):
        """Muestra el gráfico lineal dinámico en el sector de telemetría."""
        self.console_container.pack_forget()
        self.chart_view_container.pack(fill="both", expand=True, padx=0, pady=0)
        self.lbl_telemetry_title.configure(text="GRÁFICO DE RENDIMIENTO EN VIVO")

        for tag, btn in self.filter_buttons.items():
            if tag == "CHART":
                btn.configure(fg_color=COLOR_ACCENT_CYAN, text_color="#000000")
            else:
                btn.configure(fg_color="#1f2937", text_color="#f9fafb")

        self._render_dynamic_chart(broker=broker)

    def _show_console_view(self, tag="ALL"):
        """Restaura la consola de telemetría de texto."""
        self.chart_view_container.pack_forget()
        self.console_container.pack(fill="both", expand=True, padx=0, pady=0)
        self.lbl_telemetry_title.configure(text="CONSOLA DE TELEMETRÍA")

        for b_tag, btn in self.filter_buttons.items():
            if b_tag == tag:
                btn.configure(fg_color="#374151", text_color="#ffffff")
            else:
                btn.configure(fg_color="#1f2937", text_color="#f9fafb")

        self._set_log_filter(tag)

    def _render_dynamic_chart(self, broker="both"):
        """Genera e incrusta la figura de la curva lineal continua en el contenedor Tkinter."""
        self.current_chart_broker = broker
        if hasattr(self, 'chart_canvas') and self.chart_canvas is not None:
            try:
                self.chart_canvas.get_tk_widget().destroy()
            except Exception:
                pass
            self.chart_canvas = None

        if hasattr(self, 'chart_toolbar') and self.chart_toolbar is not None:
            try:
                self.chart_toolbar.destroy()
            except Exception:
                pass
            self.chart_toolbar = None

        try:
            fig = gui_bridge.generate_linear_chart_figure(broker=broker)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_canvas_frame)
            self.chart_canvas.draw()
            self.chart_canvas.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            gui_bridge.log(f"Error renderizando gráfico dinámico: {e}", "LOSS")

    def _clear_logs(self):
        self.all_logs.clear()
        self.log_text.delete("1.0", "end")

    def _render_filtered_logs(self):
        self.log_text.delete("1.0", "end")
        for ts, tag, text in self.all_logs:
            if self.filter_tag == "ALL" or self.filter_tag == tag:
                line = f"[{ts}] {text}\n"
                self.log_text.insert("end", line, tag)
        if self.auto_scroll.get():
            self.log_text.see("end")

    # -------------------------------------------------------------------------
    # BUCLES DE ACTUALIZACIÓN PERIÓDICA (POLLING LIGERO)
    # -------------------------------------------------------------------------
    def _update_logs_tick(self):
        """Consume logs acumulados en la cola de gui_bridge y los muestra."""
        has_new = False
        while not gui_bridge.log_queue.empty():
            try:
                item = gui_bridge.log_queue.get_nowait()
                self.all_logs.append(item)
                if len(self.all_logs) > 1500:
                    self.all_logs.pop(0)

                ts, tag, text = item
                if self.filter_tag == "ALL" or self.filter_tag == tag:
                    line = f"[{ts}] {text}\n"
                    self.log_text.insert("end", line, tag)
                    has_new = True
            except Exception:
                break

        if has_new and self.auto_scroll.get():
            self.log_text.see("end")

        self.after(200, self._update_logs_tick)

    def _update_telemetry_tick(self):
        """Actualiza KPIs, estados de brokers y métricas del sistema cada 1.5s."""
        now = datetime.now()
        self.clock_label.configure(text=now.strftime("%H:%M:%S"))
        if hasattr(self, 'clock_date_label'):
            self.clock_date_label.configure(text=now.strftime("%d %b %Y"))

        # Actualizar botón según estado del subproceso
        if gui_bridge.is_running:
            self.btn_toggle_bot.configure(text="🔴 DETENER BOT", fg_color="#dc2626", hover_color="#b91c1c")
            self.lbl_footer_status.configure(text="🟢 PocketOption Conectado • Watchdog de red activo (0 congelamientos)", text_color="#10b981")
            if hasattr(self, 'badge_paper_motor'):
                self.badge_paper_motor.configure(text="🟢 Motor activo", text_color="#10b981")
        else:
            self.btn_toggle_bot.configure(text="🟢 INICIAR BOT", fg_color="#10b981", hover_color="#059669")
            self.lbl_footer_status.configure(text="⚪ PocketOption Desconectado • Esperando inicio", text_color=COLOR_TEXT_MUTED)
            if hasattr(self, 'badge_paper_motor'):
                self.badge_paper_motor.configure(text="🔴 Motor detenido", text_color="#ef4444")

        # 1. PocketOption MM State
        po_state = gui_bridge.get_session_state()
        po_wins = po_state.get("session_wins", 0)
        po_losses = po_state.get("session_losses", 0)
        po_trades = po_state.get("session_trades", 0)
        po_pnl = po_state.get("session_pnl", 0.0)
        po_active = po_state.get("is_session_active", True)
        po_stop_reason = po_state.get("session_stop_reason", "")
        compound_lvl = po_state.get("compound_level", 0) + 1
        current_amount = po_state.get("current_amount", 1.0)

        # 2. Balances
        po_status = gui_bridge.get_pocketoption_status()
        po_bal = po_status.get("balance", 0.0)
        if isinstance(po_bal, (int, float)) and po_bal > 0:
            self.lbl_po_balance.configure(text=f"${po_bal:.2f} USD")
            initial_po = po_bal - po_pnl
            po_pct_val = (po_pnl / initial_po * 100) if initial_po > 0 else 0.0
            po_pct_color = COLOR_ACCENT_GREEN if po_pct_val >= 0 else COLOR_ACCENT_RED
            self.lbl_po_pct.configure(text=f"({po_pct_val:+.2f}%)", text_color=po_pct_color)

        alpaca_status = gui_bridge.get_alpaca_status()
        alp_bal = alpaca_status.get("balance", 0.0)
        alp_last = alpaca_status.get("last_equity", alp_bal)
        if isinstance(alp_bal, (int, float)) and alp_bal > 0:
            self.lbl_alpaca_balance.configure(text=f"${alp_bal:,.2f} USD")
            alp_pct_val = ((alp_bal - alp_last) / alp_last * 100) if alp_last > 0 else 0.0
            alp_pct_color = COLOR_ACCENT_GREEN if alp_pct_val >= 0 else COLOR_ACCENT_RED
            self.lbl_alpaca_pct.configure(text=f"({alp_pct_val:+.2f}%)", text_color=alp_pct_color)

        # 3. PnL y Score
        pnl_color = COLOR_ACCENT_GREEN if po_pnl >= 0 else COLOR_ACCENT_RED
        self.lbl_pnl_today.configure(text=f"${po_pnl:+.2f} USD", text_color=pnl_color)

        wr = (po_wins / po_trades * 100) if po_trades > 0 else 0.0
        self.lbl_score_wr.configure(text=f"{po_wins}W - {po_losses}L ({wr:.1f}%)")

        # 4. Tarjeta Estado PocketOption
        if not gui_bridge.is_running:
            self.badge_po_state.configure(text="DETENIDO", fg_color="#374151")
            self.lbl_po_reason.configure(text="Bot no iniciado. Presioná 'INICIAR BOT'.", text_color=COLOR_TEXT_MUTED)
        elif not po_active:
            self.badge_po_state.configure(text="EN REPOSO (STOP LOSS)", fg_color=COLOR_ACCENT_AMBER)
            self.lbl_po_reason.configure(text=f"Protección activa: {po_stop_reason or 'Límite alcanzado'}", text_color=COLOR_ACCENT_AMBER)
        else:
            self.badge_po_state.configure(text="ACTIVO & ANALIZANDO", fg_color=COLOR_ACCENT_GREEN)
            self.lbl_po_reason.configure(text="Escaneando 20 pares activos con Whitelist (WR ≥ 70%)", text_color=COLOR_ACCENT_GREEN)

        self.lbl_po_details.configure(
            text=f"Inversión actual: ${current_amount:.2f} USD • Soros Nivel {compound_lvl} • Operaciones hoy: {po_trades}/5"
        )

        # 5. Tarjeta Estado Alpaca
        # Lunes a Viernes de 09:00 a 17:30 hs (UTC-3)
        time_mins = now.hour * 60 + now.minute
        is_alpaca_market = (now.weekday() < 5) and (9 * 60 <= time_mins < 17 * 60 + 30)
        is_forex_market = not ((now.weekday() == 5) or (now.weekday() == 6 and time_mins < 18 * 60) or (now.weekday() == 4 and time_mins >= 18 * 60))
        
        if is_alpaca_market:
            self.badge_alpaca_state.configure(text="MERCADO ABIERTO", fg_color=COLOR_ACCENT_GREEN)
            self.lbl_alpaca_reason.configure(text="Wall Street, Forex y Cripto activos (Operativa Full)", text_color=COLOR_ACCENT_GREEN)
        elif is_forex_market:
            self.badge_alpaca_state.configure(text="FOREX & CRIPTO", fg_color=COLOR_ACCENT_PURPLE)
            self.lbl_alpaca_reason.configure(text="Wall Street cerrado. Operando divisas y criptomonedas", text_color=COLOR_ACCENT_PURPLE)
        else:
            self.badge_alpaca_state.configure(text="MODO CRIPTO 24/7", fg_color="#1e293b")
            self.lbl_alpaca_reason.configure(text="Fin de semana (Forex y Acciones cerradas). Escaneando Criptos.", text_color=COLOR_TEXT_MUTED)

        # 6. Métricas del Sistema
        sys_m = gui_bridge.get_system_metrics()
        self.lbl_sys_metrics.configure(text=f"CPU: {sys_m['cpu']:.1f}% | RAM: {sys_m['ram']:.1f}% | v2.4.1")

        # Refrescar tabla cada 5 segundos según la vista activa
        if now.second % 5 == 0:
            if getattr(self, 'current_view', 'REAL') == "PAPER":
                self._refresh_paper_section(force=False)
            else:
                self._refresh_trades_table()

        self.after(1500, self._update_telemetry_tick)

    def _switch_to_real_view(self):
        """Cambia a la vista de Operativa Real."""
        self.current_view = "REAL"
        self.dist_metric_mode = "pnl"
        self.btn_nav_real.configure(fg_color=COLOR_ACCENT_CYAN, text_color="#000000")
        self.btn_nav_paper.configure(fg_color="#1e293b", text_color="#9ca3af")
        self.paper_view_container.pack_forget()
        self.real_view_container.pack(fill="both", expand=True)
        self._refresh_trades_table()

    def _switch_to_paper_view(self):
        """Cambia a la vista del Laboratorio de Paper Trading."""
        self.current_view = "PAPER"
        self.btn_nav_paper.configure(fg_color=COLOR_ACCENT_CYAN, text_color="#000000")
        self.btn_nav_real.configure(fg_color="#1e293b", text_color="#9ca3af")
        self.real_view_container.pack_forget()
        self.paper_view_container.pack(fill="both", expand=True)
        self._refresh_paper_section(force=True)

    def _refresh_trades_table(self):
        """Llena la tabla de operaciones recientes reales."""
        trades = gui_bridge.get_today_trades()
            
        for item in self.trades_tree.get_children():
            self.trades_tree.delete(item)

        for t in trades[:30]:
            res = t.get("result", "PENDING")
            tag = "pending"
            if res in ("WIN", "1", "GANADA"):
                tag = "win"
            elif res in ("LOSS", "0", "PERDIDA"):
                tag = "loss"

            pnl_str = f"${t.get('profit', 0.0):+.2f}"
            self.trades_tree.insert("", "end", values=(
                t.get("timestamp", ""),
                t.get("pair", ""),
                t.get("timeframe", ""),
                t.get("decision", ""),
                res,
                pnl_str
            ), tags=(tag,))

    def _build_paper_view(self, parent=None):
        """Construye la sección dedicada al Laboratorio de Paper Trading con el diseño exacto Cyber-Fintech."""
        p = parent or self

        # 1. 5 KPIs de Paper (Mockup Cyber-Fintech)
        kpi_frame = ctk.CTkFrame(p, fg_color="transparent")
        kpi_frame.pack(fill="x", padx=16, pady=(4, 6))
        kpi_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="pkpi")

        # Card 0: Saldo Simulado
        card_bal = ctk.CTkFrame(kpi_frame, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card_bal.grid(row=0, column=0, padx=(0, 4), sticky="nsew", ipady=4)
        ctk.CTkLabel(card_bal, text="💾 SALDO SIMULADO (PAPER)", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(6, 0))
        self.lbl_paper_balance = ctk.CTkLabel(card_bal, text="-$1.81 USD", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_ACCENT_CYAN)
        self.lbl_paper_balance.pack(anchor="w", padx=12)
        
        card_bal_footer = ctk.CTkFrame(card_bal, fg_color="transparent")
        card_bal_footer.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(card_bal_footer, text="Stake base: $1.00 USD", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left")
        self.badge_paper_motor = ctk.CTkLabel(
            card_bal_footer,
            text="🟢 Motor activo" if gui_bridge.is_running else "🔴 Motor detenido",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#10b981" if gui_bridge.is_running else "#ef4444"
        )
        self.badge_paper_motor.pack(side="right")

        # Card 1: Total Operaciones Paper
        card_ops = ctk.CTkFrame(kpi_frame, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card_ops.grid(row=0, column=1, padx=4, sticky="nsew", ipady=4)
        ctk.CTkLabel(card_ops, text="📊 OPERACIONES EXPLORADAS", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(6, 0))
        self.lbl_paper_total_ops = ctk.CTkLabel(card_ops, text="9,286 trades", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_TEXT_MAIN)
        self.lbl_paper_total_ops.pack(anchor="w", padx=12)
        ctk.CTkLabel(card_ops, text="Backtest acumulativo en vivo", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 4))

        # Card 2: Resultados Globales
        card_wr = ctk.CTkFrame(kpi_frame, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card_wr.grid(row=0, column=2, padx=4, sticky="nsew", ipady=4)
        ctk.CTkLabel(card_wr, text="🏆 RESULTADOS (GLOBAL)", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(6, 0))
        self.lbl_paper_score = ctk.CTkLabel(card_wr, text="4,697W - 4,518L (51.0%)", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_ACCENT_AMBER)
        self.lbl_paper_score.pack(anchor="w", padx=12)
        self.lbl_paper_draws_sub = ctk.CTkLabel(card_wr, text="71 Empates detectados", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
        self.lbl_paper_draws_sub.pack(anchor="w", padx=12, pady=(0, 4))

        # Card 3: PnL Simulado
        card_pnl = ctk.CTkFrame(kpi_frame, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card_pnl.grid(row=0, column=3, padx=4, sticky="nsew", ipady=4)
        ctk.CTkLabel(card_pnl, text="📈 PNL NETO SIMULADO", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(6, 0))
        self.lbl_paper_pnl = ctk.CTkLabel(card_pnl, text="-$1,009.24 USD", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_ACCENT_RED)
        self.lbl_paper_pnl.pack(anchor="w", padx=12)
        ctk.CTkLabel(card_pnl, text="PnL acumulado del backtest", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 4))

        # Card 4: Drawdown Máximo
        card_dd = ctk.CTkFrame(kpi_frame, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        card_dd.grid(row=0, column=4, padx=(4, 0), sticky="nsew", ipady=4)
        ctk.CTkLabel(card_dd, text="🛡️ DRAW DOWN MÁX.", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(6, 0))
        self.lbl_paper_drawdown = ctk.CTkLabel(card_dd, text="-10.89%", font=ctk.CTkFont(family="Outfit", size=18, weight="bold"), text_color=COLOR_ACCENT_RED)
        self.lbl_paper_drawdown.pack(anchor="w", padx=12)
        ctk.CTkLabel(card_dd, text="Riesgo histórico máximo", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 4))

        # 2. Split Principal de Paper Trading
        paper_split = ctk.CTkFrame(p, fg_color="transparent")
        paper_split.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        paper_split.grid_columnconfigure(0, weight=5)
        paper_split.grid_columnconfigure(1, weight=5)
        paper_split.grid_rowconfigure(0, weight=1)

        # Columna Izquierda: Tabla de Operaciones Simuladas (Tema Cyber con scrollbar oscuro)
        table_card = ctk.CTkFrame(paper_split, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        table_card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        tbl_header = ctk.CTkFrame(table_card, fg_color="transparent")
        tbl_header.pack(fill="x", padx=14, pady=(10, 6))

        tbl_title_box = ctk.CTkFrame(tbl_header, fg_color="transparent")
        tbl_title_box.pack(side="left")

        ctk.CTkLabel(tbl_title_box, text="HISTORIAL DE OPERACIONES SIMULADAS", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")

        live_badge = ctk.CTkFrame(tbl_title_box, fg_color="#064e3b", corner_radius=6)
        live_badge.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(live_badge, text="🟢 En tiempo real", font=ctk.CTkFont(size=10, weight="bold"), text_color="#10b981").pack(padx=6, pady=2)

        btn_ref_paper = ctk.CTkButton(tbl_header, text="🔄 Actualizar", width=80, height=26, font=ctk.CTkFont(size=11, weight="bold"), fg_color="#1e293b", hover_color="#334155", command=lambda: self._refresh_paper_section(force=True))
        btn_ref_paper.pack(side="right")

        pairs, strats = gui_bridge.get_paper_unique_filters()

        self.combo_paper_strat_filter = ctk.CTkOptionMenu(tbl_header, values=strats, width=140, height=26, font=ctk.CTkFont(size=11), command=lambda e: self._refresh_paper_section(force=True))
        self.combo_paper_strat_filter.pack(side="right", padx=(0, 8))
        self.combo_paper_strat_filter.set("Todas")

        self.combo_paper_pair_filter = ctk.CTkOptionMenu(tbl_header, values=pairs, width=105, height=26, font=ctk.CTkFont(size=11), command=lambda e: self._refresh_paper_section(force=True))
        self.combo_paper_pair_filter.pack(side="right", padx=(0, 8))
        self.combo_paper_pair_filter.set("Todos")

        tree_frame = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("time", "pair", "tf", "dir", "strategy", "result", "profit")
        self.paper_trades_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", style="Cyber.Treeview")
        self.paper_trades_tree.heading("time", text="Hora")
        self.paper_trades_tree.heading("pair", text="Activo")
        self.paper_trades_tree.heading("tf", text="TF")
        self.paper_trades_tree.heading("dir", text="Dir.")
        self.paper_trades_tree.heading("strategy", text="Estrategia")
        self.paper_trades_tree.heading("result", text="Resultado")
        self.paper_trades_tree.heading("profit", text="PnL")

        self.paper_trades_tree.column("time", width=62, anchor="center")
        self.paper_trades_tree.column("pair", width=95, anchor="w")
        self.paper_trades_tree.column("tf", width=36, anchor="center")
        self.paper_trades_tree.column("dir", width=55, anchor="center")
        self.paper_trades_tree.column("strategy", width=140, anchor="w")
        self.paper_trades_tree.column("result", width=65, anchor="center")
        self.paper_trades_tree.column("profit", width=65, anchor="e")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.paper_trades_tree.yview, style="Cyber.Vertical.TScrollbar")
        self.paper_trades_tree.configure(yscrollcommand=tree_scroll.set)
        self.paper_trades_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.paper_trades_tree.tag_configure("win", foreground="#10b981")
        self.paper_trades_tree.tag_configure("loss", foreground="#ef4444")
        self.paper_trades_tree.tag_configure("draw", foreground="#9ca3af")
        self.paper_trades_tree.tag_configure("pending", foreground="#f59e0b")

        # Columna Derecha: Todas las Estrategias (Sin top 10) + Distribución de Estrategias y Donut 2D
        right_panel = ctk.CTkFrame(paper_split, fg_color="transparent")
        right_panel.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=5)
        right_panel.grid_rowconfigure(1, weight=5)
        right_panel.grid_columnconfigure(0, weight=1)

        # Card Arriba: Tabla por Estrategia (TODAS las estrategias sin limitar a Top 10)
        strat_card = ctk.CTkFrame(right_panel, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        strat_card.grid(row=0, column=0, pady=(0, 4), sticky="nsew")

        strat_hdr = ctk.CTkFrame(strat_card, fg_color="transparent")
        strat_hdr.pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(strat_hdr, text="RENDIMIENTO POR ESTRATEGIA", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        
        self.lbl_strat_count = ctk.CTkLabel(strat_hdr, text="", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
        self.lbl_strat_count.pack(side="right")

        strat_frame = ctk.CTkFrame(strat_card, fg_color="transparent")
        strat_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        s_cols = ("rank", "strategy", "ops", "wins", "losses", "draws", "wr", "pnl")
        self.paper_strat_tree = ttk.Treeview(strat_frame, columns=s_cols, show="headings", selectmode="browse", style="Cyber.Treeview")
        self.paper_strat_tree.heading("rank", text="#")
        self.paper_strat_tree.heading("strategy", text="Estrategia")
        self.paper_strat_tree.heading("ops", text="Ops.")
        self.paper_strat_tree.heading("wins", text="W")
        self.paper_strat_tree.heading("losses", text="L")
        self.paper_strat_tree.heading("draws", text="D")
        self.paper_strat_tree.heading("wr", text="Win Rate")
        self.paper_strat_tree.heading("pnl", text="PnL Sim.")

        self.paper_strat_tree.column("rank", width=28, anchor="center")
        self.paper_strat_tree.column("strategy", width=145, anchor="w")
        self.paper_strat_tree.column("ops", width=38, anchor="center")
        self.paper_strat_tree.column("wins", width=28, anchor="center")
        self.paper_strat_tree.column("losses", width=28, anchor="center")
        self.paper_strat_tree.column("draws", width=28, anchor="center")
        self.paper_strat_tree.column("wr", width=58, anchor="center")
        self.paper_strat_tree.column("pnl", width=62, anchor="e")

        strat_scroll = ttk.Scrollbar(strat_frame, orient="vertical", command=self.paper_strat_tree.yview, style="Cyber.Vertical.TScrollbar")
        self.paper_strat_tree.configure(yscrollcommand=strat_scroll.set)
        self.paper_strat_tree.pack(side="left", fill="both", expand=True)
        strat_scroll.pack(side="right", fill="y")

        self.paper_strat_tree.tag_configure("strat_green", foreground="#10b981")
        self.paper_strat_tree.tag_configure("strat_yellow", foreground="#f59e0b")
        self.paper_strat_tree.tag_configure("strat_red", foreground="#ef4444")
        self.paper_strat_tree.tag_configure("strat_gray", foreground="#9ca3af")

        # Card Abajo: Submódulo de Distribución de Estrategias y Donut 2D (Diseño exacto del mockup)
        dist_card = ctk.CTkFrame(right_panel, fg_color=COLOR_CARD_BG, corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER)
        dist_card.grid(row=1, column=0, pady=(4, 0), sticky="nsew")

        dist_hdr = ctk.CTkFrame(dist_card, fg_color="transparent")
        dist_hdr.pack(fill="x", padx=14, pady=(8, 4))

        self.lbl_dist_title = ctk.CTkLabel(dist_hdr, text="DISTRIBUCIÓN DE ESTRATEGIAS", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_TEXT_MAIN)
        self.lbl_dist_title.pack(side="left")

        mode_box = ctk.CTkFrame(dist_hdr, fg_color="transparent")
        mode_box.pack(side="right")

        self.btn_mode_pnl = ctk.CTkButton(
            mode_box, text="📊 PnL", width=55, height=22, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=COLOR_ACCENT_CYAN, text_color="#000000", hover_color="#38bdf8",
            command=lambda: self._set_dist_metric("pnl")
        )
        self.btn_mode_pnl.pack(side="left", padx=2)

        self.btn_mode_wr = ctk.CTkButton(
            mode_box, text="🎯 Win Rate", width=75, height=22, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1e293b", text_color="#9ca3af", hover_color="#334155",
            command=lambda: self._set_dist_metric("wr")
        )
        self.btn_mode_wr.pack(side="left", padx=2)

        self.btn_mode_ops = ctk.CTkButton(
            mode_box, text="📈 Ops.", width=55, height=22, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1e293b", text_color="#9ca3af", hover_color="#334155",
            command=lambda: self._set_dist_metric("ops")
        )
        self.btn_mode_ops.pack(side="left", padx=2)

        # Contenedor cuerpo dividido: 58% barras de estrategias individuales a la izquierda, 42% donut a la derecha
        dist_body = ctk.CTkFrame(dist_card, fg_color="transparent")
        dist_body.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        dist_body.grid_columnconfigure(0, weight=6)
        dist_body.grid_columnconfigure(1, weight=4)
        dist_body.grid_rowconfigure(0, weight=1)

        # Sub-panel Izquierdo: Barras de Estrategias Individuales (Scrollable con todas las 43 estrategias)
        self.strat_bars_frame = ctk.CTkScrollableFrame(
            dist_body,
            fg_color="#0b1120",
            corner_radius=8,
            border_width=1,
            border_color="#1e293b",
            scrollbar_button_color="#1e293b",
            scrollbar_button_hover_color="#334155"
        )
        self.strat_bars_frame.grid(row=0, column=0, padx=(0, 4), sticky="nsew")

        # Sub-panel Derecho: Donut Compacto + Resumen de Ganadoras/Perdedoras
        donut_panel = ctk.CTkFrame(dist_body, fg_color="#0b1120", corner_radius=8, border_width=1, border_color="#1e293b")
        donut_panel.grid(row=0, column=1, padx=(4, 0), sticky="nsew")

        self.donut_canvas_frame = ctk.CTkFrame(donut_panel, fg_color="transparent")
        self.donut_canvas_frame.pack(fill="both", expand=True, padx=4, pady=(2, 0))

        donut_footer = ctk.CTkFrame(donut_panel, fg_color="transparent")
        donut_footer.pack(fill="x", padx=6, pady=(0, 4))

        self.lbl_donut_wins = ctk.CTkLabel(donut_footer, text="🟢 0 ganadoras (0.0%)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#10b981")
        self.lbl_donut_wins.pack(anchor="w")

        self.lbl_donut_losses = ctk.CTkLabel(donut_footer, text="🔴 0 perdedoras (0.0%)", font=ctk.CTkFont(size=10, weight="bold"), text_color="#ef4444")
        self.lbl_donut_losses.pack(anchor="w")

    def _set_dist_metric(self, mode):
        """Alterna la métrica activa en el submódulo de distribución (PnL, Win Rate u Ops)."""
        self.dist_metric_mode = mode
        self.btn_mode_pnl.configure(
            fg_color=COLOR_ACCENT_CYAN if mode == "pnl" else "#1e293b",
            text_color="#000000" if mode == "pnl" else "#9ca3af"
        )
        self.btn_mode_wr.configure(
            fg_color=COLOR_ACCENT_CYAN if mode == "wr" else "#1e293b",
            text_color="#000000" if mode == "wr" else "#9ca3af"
        )
        self.btn_mode_ops.configure(
            fg_color=COLOR_ACCENT_CYAN if mode == "ops" else "#1e293b",
            text_color="#000000" if mode == "ops" else "#9ca3af"
        )
        self._refresh_paper_section(force=True)

    def _refresh_paper_section(self, force=False):
        """Actualiza KPIs, tabla de operaciones, tabla de estrategias y submódulo de distribución con Donut."""
        if not hasattr(self, 'paper_trades_tree'):
            return

        pair_filter = None
        if hasattr(self, 'combo_paper_pair_filter'):
            pair_filter = self.combo_paper_pair_filter.get()
            
        strat_filter = None
        if hasattr(self, 'combo_paper_strat_filter'):
            strat_filter = self.combo_paper_strat_filter.get()

        meta = gui_bridge.get_paper_file_meta()
        refresh_key = (meta, pair_filter, strat_filter, getattr(self, 'dist_metric_mode', 'pnl'))

        if not force and getattr(self, '_last_paper_refresh_key', None) == refresh_key:
            return
        self._last_paper_refresh_key = refresh_key

        # Actualizar opciones de filtros si hay nuevos registros en CSV
        try:
            pairs, strats = gui_bridge.get_paper_unique_filters()
            if hasattr(self, 'combo_paper_pair_filter'):
                curr_p = self.combo_paper_pair_filter.get()
                self.combo_paper_pair_filter.configure(values=pairs)
                if curr_p in pairs:
                    self.combo_paper_pair_filter.set(curr_p)
            if hasattr(self, 'combo_paper_strat_filter'):
                curr_s = self.combo_paper_strat_filter.get()
                self.combo_paper_strat_filter.configure(values=strats)
                if curr_s in strats:
                    self.combo_paper_strat_filter.set(curr_s)
        except Exception:
            pass

        paper_stats = gui_bridge.get_paper_stats(pair_filter=pair_filter, strat_filter=strat_filter)
        totals = paper_stats.get("totals", {})
        strategies = paper_stats.get("strategies", [])
        paper_trades = gui_bridge.get_paper_trades(limit=100, pair_filter=pair_filter, strat_filter=strat_filter)

        bal = totals.get("balance", 20.0)
        tot_trades = totals.get("total_trades", 0)
        wins = totals.get("wins", 0)
        losses = totals.get("losses", 0)
        draws = totals.get("draws", 0)
        wr = totals.get("win_rate", 0.0)
        pnl = totals.get("pnl", 0.0)

        # 1. 5 KPIs
        self.lbl_paper_balance.configure(text=f"${bal:.2f} USD")
        self.lbl_paper_total_ops.configure(text=f"{tot_trades:,} trades")
        
        wr_color = COLOR_ACCENT_GREEN if wr >= 60.0 else (COLOR_ACCENT_AMBER if wr >= 50.0 else COLOR_ACCENT_RED)
        self.lbl_paper_score.configure(text=f"{wins:,}W - {losses:,}L ({wr:.1f}%)", text_color=wr_color)
        self.lbl_paper_draws_sub.configure(text=f"{draws:,} Empates detectados")

        pnl_color = COLOR_ACCENT_GREEN if pnl >= 0 else COLOR_ACCENT_RED
        self.lbl_paper_pnl.configure(text=f"${pnl:+.2f} USD", text_color=pnl_color)

        dd_val = totals.get("max_drawdown", -10.89)
        if hasattr(self, 'lbl_paper_drawdown'):
            self.lbl_paper_drawdown.configure(text=f"{dd_val:.2f}%")

        if hasattr(self, 'badge_paper_motor'):
            if gui_bridge.is_running:
                self.badge_paper_motor.configure(text="🟢 Motor activo", text_color="#10b981")
            else:
                self.badge_paper_motor.configure(text="🔴 Motor detenido", text_color="#ef4444")

        # 2. Llenar tabla de trades de paper
        for item in self.paper_trades_tree.get_children():
            self.paper_trades_tree.delete(item)

        for t in paper_trades[:60]:
            res = str(t.get("result", "PENDING")).upper()
            tag = "draw"
            res_label = "DRAW"
            if res in ("WIN", "1", "GANADA"):
                tag = "win"
                res_label = "WIN"
            elif res in ("LOSS", "0", "PERDIDA"):
                tag = "loss"
                res_label = "LOSS"
            elif res == "PENDING":
                tag = "pending"
                res_label = "PENDING"

            dec = str(t.get("decision", "BUY")).upper()
            dec_label = "↑ BUY" if "BUY" in dec or "CALL" in dec else "↓ SELL"

            pnl_val = float(t.get("profit", 0.0))
            pnl_str = f"+${pnl_val:.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):.2f}"

            ts_raw = str(t.get("timestamp", ""))
            time_disp = ts_raw.split(" ")[-1] if " " in ts_raw else ts_raw

            self.paper_trades_tree.insert("", "end", values=(
                time_disp,
                t.get("pair", ""),
                t.get("timeframe", ""),
                dec_label,
                t.get("strategy", ""),
                res_label,
                pnl_str
            ), tags=(tag,))

        # 3. Llenar tabla de estrategias (TODAS las estrategias, sin recortar a top 10)
        for item in self.paper_strat_tree.get_children():
            self.paper_strat_tree.delete(item)

        for rank_idx, s in enumerate(strategies, 1):
            s_wr = s["win_rate"]
            tag = "strat_green" if s_wr >= 60.0 else ("strat_yellow" if s_wr >= 50.0 else "strat_red")
            if (s["wins"] + s["losses"]) == 0:
                tag = "strat_gray"
            self.paper_strat_tree.insert("", "end", values=(
                f"#{rank_idx}",
                s["strategy"],
                s["trades"],
                s["wins"],
                s["losses"],
                s["draws"],
                f"{s_wr:.1f}%",
                f"${s['pnl']:+.2f}"
            ), tags=(tag,))

        if hasattr(self, 'lbl_strat_count'):
            self.lbl_strat_count.configure(text=f"{len(strategies)} estrategias activas")

        # 4. Distribución de Estrategias Individuales (Scrollable con TODAS las 43 estrategias)
        if hasattr(self, 'lbl_dist_title'):
            self.lbl_dist_title.configure(text=f"DISTRIBUCIÓN DE ESTRATEGIAS ({len(strategies)}+)")

        if hasattr(self, 'strat_bars_frame'):
            # Ordenar estrategias individuales según la métrica activa
            if self.dist_metric_mode == "pnl":
                sorted_strats = sorted(strategies, key=lambda x: x["pnl"], reverse=True)
                max_metric = max([abs(s["pnl"]) for s in strategies] or [1.0])
            elif self.dist_metric_mode == "wr":
                sorted_strats = sorted(strategies, key=lambda x: x["win_rate"], reverse=True)
                max_metric = 100.0
            else: # ops
                sorted_strats = sorted(strategies, key=lambda x: x["trades"], reverse=True)
                max_metric = max([s["trades"] for s in strategies] or [1.0])

            VIBRANT_PALETTE = [
                "#06b6d4", "#8b5cf6", "#d946ef", "#f59e0b", "#eab308", "#10b981",
                "#38bdf8", "#ec4899", "#6366f1", "#14b8a6", "#f97316", "#84cc16",
                "#a855f7", "#0284c7", "#e11d48", "#059669", "#d97706", "#7c3aed"
            ]

            tot_ops_all = totals.get("total_trades", 1) or 1

            # Reutilizar widgets existentes en vez de destruirlos y recrearlos cada vez
            if not hasattr(self, '_strat_bar_widgets') or len(self._strat_bar_widgets) != len(sorted_strats):
                for w in self.strat_bars_frame.winfo_children():
                    w.destroy()
                self._strat_bar_widgets = []
                for idx, s in enumerate(sorted_strats):
                    row_f = ctk.CTkFrame(self.strat_bars_frame, fg_color="transparent", height=24)
                    row_f.pack(fill="x", padx=4, pady=2)

                    dot = ctk.CTkFrame(row_f, width=4, height=14, corner_radius=2)
                    dot.pack(side="left", padx=(0, 6))

                    lbl_name = ctk.CTkLabel(row_f, text="", font=ctk.CTkFont(size=10, weight="bold"), text_color="#f8fafc", anchor="w")
                    lbl_name.pack(side="left", fill="x", expand=True)

                    lbl_pct = ctk.CTkLabel(row_f, text="", font=ctk.CTkFont(size=9, weight="bold"), width=44, anchor="e")
                    lbl_pct.pack(side="left", padx=(2, 4))

                    lbl_val = ctk.CTkLabel(row_f, text="", font=ctk.CTkFont(size=9, weight="bold"), width=62, anchor="e")
                    lbl_val.pack(side="left", padx=(0, 6))

                    pbar = ctk.CTkProgressBar(row_f, width=46, height=6, fg_color="#1e293b", corner_radius=3)
                    pbar.pack(side="left", padx=(0, 2))

                    self._strat_bar_widgets.append((row_f, dot, lbl_name, lbl_pct, lbl_val, pbar))

            # Actualizar valores sin destruir widgets
            for idx, s in enumerate(sorted_strats):
                color = VIBRANT_PALETTE[idx % len(VIBRANT_PALETTE)]
                row_f, dot, lbl_name, lbl_pct, lbl_val, pbar = self._strat_bar_widgets[idx]
                dot.configure(fg_color=color)

                name = s["strategy"]
                if len(name) > 20:
                    name = name[:18] + ".."
                lbl_name.configure(text=name)

                trades_cnt = s["trades"]
                pnl_val = s["pnl"]
                wr_val = s["win_rate"]

                if self.dist_metric_mode == "pnl":
                    # Rendimiento ROI % en relación al volumen invertido (stake base $1.00 USD)
                    roi = (pnl_val / max(1.0, trades_cnt * 1.0)) * 100.0
                    if pnl_val >= 0:
                        pct_str = f"+{roi:.1f}%"
                        pct_col = "#10b981"
                        v_str = f"+${pnl_val:.2f}"
                        v_col = "#10b981"
                        bar_col = "#10b981"
                    else:
                        pct_str = f"-{abs(roi):.1f}%"
                        pct_col = "#ef4444"
                        v_str = f"-${abs(pnl_val):.2f}"
                        v_col = "#ef4444"
                        bar_col = "#ef4444"
                    norm = min(1.0, max(0.05, abs(pnl_val) / max(1.0, max_metric)))

                elif self.dist_metric_mode == "wr":
                    pct_str = f"{wr_val:.1f}%"
                    pct_col = "#10b981" if wr_val >= 60 else ("#f59e0b" if wr_val >= 50 else "#ef4444")
                    v_str = f"${pnl_val:+.2f}"
                    v_col = "#10b981" if pnl_val >= 0 else "#ef4444"
                    bar_col = pct_col
                    norm = min(1.0, max(0.05, wr_val / 100.0))

                else: # ops
                    share_pct = (trades_cnt / tot_ops_all) * 100.0
                    pct_str = f"{share_pct:.1f}%"
                    pct_col = "#94a3b8"
                    v_str = f"{trades_cnt:,} ops"
                    v_col = "#38bdf8"
                    bar_col = "#38bdf8"
                    norm = min(1.0, max(0.05, trades_cnt / max(1.0, max_metric)))

                lbl_pct.configure(text=pct_str, text_color=pct_col)
                lbl_val.configure(text=v_str, text_color=v_col)
                pbar.configure(progress_color=bar_col)
                pbar.set(norm)

        # 5. Donut 2D Compacto (Derecha) con soporte interactivo de mouse (Hover)
        if hasattr(self, 'donut_canvas_frame'):
            for w in self.donut_canvas_frame.winfo_children():
                w.destroy()
            try:
                fig, wedges, chart_data, center_texts = gui_bridge.generate_paper_compact_donut_figure(
                    figsize=(1.9, 1.9),
                    pair_filter=pair_filter,
                    strat_filter=strat_filter,
                    stats_data=paper_stats
                )
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                donut_canvas = FigureCanvasTkAgg(fig, master=self.donut_canvas_frame)
                donut_canvas.draw()
                donut_canvas.get_tk_widget().pack(fill="both", expand=True)

                self._donut_hover_idx = None

                w_strats = totals.get("winning_strats", 0)
                l_strats = totals.get("losing_strats", 0)
                w_pct = totals.get("winning_pct", 0.0)
                l_pct = totals.get("losing_pct", 0.0)

                def on_donut_mouse_move(event):
                    if not event.inaxes or event.x is None or event.y is None or not wedges:
                        if self._donut_hover_idx is not None:
                            reset_donut_hover()
                        return

                    hit_idx = None
                    for idx, w in enumerate(wedges):
                        if w.contains_point((event.x, event.y)):
                            hit_idx = idx
                            break

                    if hit_idx is not None:
                        if self._donut_hover_idx != hit_idx:
                            self._donut_hover_idx = hit_idx
                            s = chart_data[hit_idx]

                            # Resaltar sector seleccionado y atenuar el resto
                            for j, w in enumerate(wedges):
                                if j == hit_idx:
                                    w.set_alpha(1.0)
                                    w.set_edgecolor('#ffffff')
                                    w.set_linewidth(2.6)
                                else:
                                    w.set_alpha(0.35)
                                    w.set_edgecolor('#0b1120')
                                    w.set_linewidth(1.0)

                            # Actualizar texto central del donut
                            wr_color = '#10b981' if s['win_rate'] >= 60 else ('#f59e0b' if s['win_rate'] >= 50 else '#ef4444')
                            if center_texts:
                                center_texts["t1"].set_text(f"{s['win_rate']:.0f}%")
                                center_texts["t1"].set_color(wr_color)
                                center_texts["t2"].set_text("WIN RATE")
                                center_texts["t2"].set_color('#94a3b8')
                                center_texts["t3"].set_text(f"{s['trades']} Ops")
                                center_texts["t3"].set_color('#38bdf8')

                            # Actualizar footer debajo del donut
                            strat_name = s['strategy']
                            if len(strat_name) > 22:
                                strat_name = strat_name[:20] + ".."
                            pnl_col = "#10b981" if s['pnl'] >= 0 else "#ef4444"
                            if hasattr(self, 'lbl_donut_wins'):
                                self.lbl_donut_wins.configure(
                                    text=f"💡 #{hit_idx+1} {strat_name}",
                                    text_color=s.get("color", "#38bdf8")
                                )
                            if hasattr(self, 'lbl_donut_losses'):
                                self.lbl_donut_losses.configure(
                                    text=f"WR: {s['win_rate']:.1f}% | PnL: ${s['pnl']:+.2f} USD",
                                    text_color=pnl_col
                                )

                            donut_canvas.draw_idle()
                    else:
                        if self._donut_hover_idx is not None:
                            reset_donut_hover()

                def reset_donut_hover():
                    self._donut_hover_idx = None
                    for w in wedges:
                        w.set_alpha(0.95)
                        w.set_edgecolor('#0b1120')
                        w.set_linewidth(1.5)

                    if center_texts:
                        center_texts["t1"].set_text(f"{len(strategies)}+")
                        center_texts["t1"].set_color('#ffffff')
                        center_texts["t2"].set_text("ESTRATEGIAS")
                        center_texts["t2"].set_color('#94a3b8')
                        center_texts["t3"].set_text("ACTIVAS")
                        center_texts["t3"].set_color('#38bdf8')

                    if hasattr(self, 'lbl_donut_wins'):
                        self.lbl_donut_wins.configure(text=f"🟢 {w_strats} ganadoras   {w_pct:.1f}%", text_color="#10b981")
                    if hasattr(self, 'lbl_donut_losses'):
                        self.lbl_donut_losses.configure(text=f"🔴 {l_strats} perdedoras  {l_pct:.1f}%", text_color="#ef4444")
                    donut_canvas.draw_idle()

                donut_canvas.mpl_connect('motion_notify_event', on_donut_mouse_move)

            except Exception as e:
                print(f"Error rendering interactive compact donut: {e}")

    def _on_close(self):
        if gui_bridge.is_running:
            res = messagebox.askyesno("Detener Bot", "¿Querés detener el motor de trading antes de cerrar la terminal?")
            if res:
                gui_bridge.stop_bot_process()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    if not acquire_gui_single_instance_lock():
        # Ya existe una instancia abierta (traída al frente), salir limpiamente
        sys.exit(0)
    app = TradingTerminalApp()
    app.mainloop()
