-- Script para crear la tabla de trades de CUENTA REAL en Supabase
-- Copia y pega esto en el SQL Editor de tu dashboard de Supabase (https://supabase.com)

CREATE TABLE IF NOT EXISTS trades_real (
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

-- Habilitar RLS (Row Level Security)
ALTER TABLE trades_real ENABLE ROW LEVEL SECURITY;

-- Crear política para permitir inserciones y actualizaciones
CREATE POLICY "Allow all for trades_real" ON trades_real FOR ALL USING (true) WITH CHECK (true);
