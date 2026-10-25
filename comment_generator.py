import os
import json
import random
import asyncio

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

STOIC_TRADING_QUOTES = {
    "win": [
        "\"El mercado es un dispositivo para transferir dinero del impaciente al paciente.\" - Warren Buffett",
        "\"No te enfoques en hacer dinero, enfócate en proteger lo que tienes.\" - Paul Tudor Jones",
        "\"Un buen trader no se emociona con las ganancias ni se deprime con las pérdidas.\" - Mark Douglas",
        "\"El riesgo viene de no saber lo que estás haciendo.\" - Warren Buffett",
        "\"Controla tus emociones o ellas te controlarán a ti. Buena disciplina hoy.\"",
        "\"Deja correr tus ganancias y corta tus pérdidas rápido. Gran ejecución.\"",
        "\"La excelencia no es un acto, sino un hábito. Sumando al capital de a poco.\" - Aristóteles"
    ],
    "loss": [
        "\"La pérdida es la matrícula que pagas para aprender a operar.\" - Mark Douglas",
        "\"A veces ganas, a veces aprendes. Nunca pierdes si sacas una lección.\"",
        "\"El estoicismo no es no sentir emociones, sino no ser controlado por ellas. A seguir.\"",
        "\"Un trader perdedor puede hacer poco para transformarse en un ganador si no aprende a aceptar el riesgo.\" - Mark Douglas",
        "\"Sufres más en la imaginación que en la realidad. La gestión de riesgo te protege.\" - Séneca",
        "\"No puedes controlar el mercado, solo tu reacción a él. Mantén el plan.\"",
        "\"Aceptar la pérdida te libera mentalmente para la siguiente oportunidad.\""
    ]
}

class CommentGenerator:
    def __init__(self, gemini_api_key=None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")

    async def generate_ai_comment(self, pair: str, profit: float, is_win: bool, api_key: str = None):
        """Genera un comentario sarcástico/épico con Gemini AI."""
        key = api_key or self.gemini_api_key
        if not _GENAI_AVAILABLE or not key:
            return None

        profit_str = f"+${profit:.2f} USD" if is_win else f"-${abs(profit):.2f} USD"
        result_str = "GANADO" if is_win else "PERDIDO"
        
        prompt = f"""Actúa como un trader veterano y estoico pero con mucho sentido del humor criollo / argentino.
Un trade acaba de cerrarse con estos datos:
- Resultado: {result_str}
- Par/Activo: {pair}
- Monto: {profit_str}

Genera un ÚNICO comentario de 1 o 2 oraciones para enviar por Telegram a modo de notificación.
Si el trade es ganador, haz un halago exagerado y épico.
Si el trade es perdedor, haz un "roast" (burla sarcástica pero graciosa) o un lamento teatral.
REGLA: Usa emojis. Sé creativo y que no suene a bot genérico. NUNCA inventes números distintos a {profit_str}.

Devuelve ÚNICAMENTE el texto del comentario."""

        def call_ai():
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(prompt)
            return res.text.strip()

        try:
            raw_text = await asyncio.wait_for(asyncio.to_thread(call_ai), timeout=4.5)
            return raw_text.strip()
        except Exception as e:
            return None

    def get_stoic_quote(self, is_win: bool):
        category = "win" if is_win else "loss"
        return random.choice(STOIC_TRADING_QUOTES[category])

    async def generate_close_comment(self, pair: str, profit: float, is_win: bool, api_key: str = None):
        """Elige aleatoriamente entre IA (roast/halago) o frase estoica."""
        # 50% probabilidad de IA vs Frase estoica
        use_ai = random.choice([True, False])
        
        comment = None
        if use_ai:
            comment = await self.generate_ai_comment(pair, profit, is_win, api_key)
            
        if not comment:
            # Fallback a frase si falla IA o si tocó frase
            comment = self.get_stoic_quote(is_win)
            
        return comment

# Instancia global exportada
comment_generator = CommentGenerator()
