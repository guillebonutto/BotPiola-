-- Script para crear la tabla de trades en Supabase
-- Copia y pega esto en el SQL Editor de tu dashboard de Supabase

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    pair TEXT,
    timeframe TEXT,
    decision TEXT,
    signal_score REAL,
    pattern_detected TEXT,
    price REAL,
    ema REAL,
    rsi REAL,
    ema_conf INTEGER,
    tf_signal INTEGER,
    atr REAL,
    triangle_active INTEGER,
    reversal_candle INTEGER,
    near_support BOOLEAN,
    near_resistance BOOLEAN,
    support_level REAL,
    resistance_level REAL,
    htf_signal INTEGER,
    result TEXT,
    profit_loss REAL,
    expiry_time INTEGER,
    notes TEXT
);

-- Habilitar RLS (opcional, pero recomendado)
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;

-- Crear política para permitir inserciones y actualizaciones (ajustar según necesidad)
CREATE POLICY "Allow all for now" ON trades FOR ALL USING (true) WITH CHECK (true);
