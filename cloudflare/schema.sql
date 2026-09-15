CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health (
  source TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS market_quotes (
  source TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  price REAL,
  bid REAL,
  ask REAL,
  volume REAL,
  quote_ts TEXT,
  received_at TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (source, market, symbol)
);

CREATE TABLE IF NOT EXISTS buy_ideas (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  price REAL,
  action TEXT NOT NULL,
  setup_grade TEXT,
  safety_status TEXT NOT NULL,
  technical_score REAL,
  validation_status TEXT,
  rr REAL,
  reason TEXT,
  price_updated_at TEXT,
  signal_updated_at TEXT,
  data_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, symbol)
);

CREATE TABLE IF NOT EXISTS positions (
  platform TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  quantity REAL,
  avg_buy REAL,
  current_price REAL,
  pnl_pct REAL,
  action TEXT,
  reason TEXT,
  price_updated_at TEXT,
  signal_updated_at TEXT,
  data_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (platform, market, symbol)
);

CREATE TABLE IF NOT EXISTS closed_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market TEXT,
  symbol TEXT,
  entry_price REAL,
  exit_price REAL,
  pnl_pct REAL,
  exit_reason TEXT,
  closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_buy_action ON buy_ideas(action);
CREATE INDEX IF NOT EXISTS idx_buy_updated ON buy_ideas(updated_at);
CREATE INDEX IF NOT EXISTS idx_pos_action ON positions(action);
CREATE INDEX IF NOT EXISTS idx_quote_symbol ON market_quotes(market, symbol);
