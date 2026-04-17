# Oanda Scalper

Bot de **scalping** en Python para operar en la API de **OANDA**. Está pensado
para correr dentro de un contenedor Docker, en una cuenta **demo (practice)**, y
empieza por defecto con dos instrumentos: **XAU_USD (Oro)** y **EUR_USD**.

> ⚠️  Aviso: el trading apalancado conlleva un alto riesgo de pérdida. Este
> proyecto se entrega con fines educativos. **Pruébalo siempre en cuenta demo
> antes de usarlo con dinero real.**

---

## Estrategia (nueva por defecto: `trend_pullback`)

Scalping **a favor de la tendencia** con entradas en pullback. Resumen:

1. **Filtro de tendencia (M1)**: EMA rápida (20) vs EMA lenta (50) + pendiente.
   - EMA_fast > EMA_slow y pendiente positiva → sólo **COMPRAS**.
   - EMA_fast < EMA_slow y pendiente negativa → sólo **VENTAS**.
2. **Filtro de fuerza**: `ADX(14) ≥ MIN_ADX` (default 20).
3. **Pullback RSI**:
   - COMPRA cuando el RSI entra en zona de corrección: `RSI ≤ RSI_BUY_THRESHOLD` (default 40).
   - VENTA cuando `RSI ≥ RSI_SELL_THRESHOLD` (default 60).
4. **Confirmación multi-timeframe (`HTF_CONFIRMATION=true`)**: la tendencia en
   M5 debe coincidir con la dirección de la entrada. Descarta señales contra la
   tendencia mayor.
5. **Filtro de sesión**: solo Londres (07:00–12:00 UTC) y Nueva York (13:00–17:00 UTC).
6. **Filtro de spread dinámico**: `spread < ATR × SPREAD_ATR_RATIO` (0.15 por defecto).
7. **Cooldown por instrumento**: tras cerrar un trade, espera
   `TRADE_COOLDOWN_SECONDS` (300 s) antes de considerar una nueva entrada en el
   mismo instrumento. Evita el revenge-trading.

Órdenes de mercado con `stopLossOnFill` y `takeProfitOnFill` basados en ATR:

- `SL = entry ± ATR × ATR_SL_MULT`  (default 1.2)
- `TP = entry ± ATR × ATR_TP_MULT`  (default 2.0)  → R:R ≈ **1:1.67**

### Gestión dinámica de trades activos

- **Breakeven**: al alcanzar `BREAKEVEN_TRIGGER_R` a favor (default 1R), el SL
  se mueve al precio de entrada.
- **Trailing**: una vez en breakeven, el SL se arrastra a
  `close ± TRAILING_ATR_MULT × ATR` (default 1.2).

### Gestión de riesgo

- **Riesgo por trade**: 1% del balance (configurable).
- **Tamaño de posición**: calculado para que la distancia hasta el stop iguale
  al riesgo permitido.
- **Máximo de operaciones simultáneas**: 2.
- **Drawdown diario sobre NAV**: si la equity (incluye P&L flotante) baja un 5 %,
  el bot se pausa hasta el día siguiente.
- **Una posición por instrumento** a la vez.

### Modo legacy: `mean_reversion`

Se mantiene activando `STRATEGY_MODE=mean_reversion`. Recomendación: usarlo
sólo con `MIN_ADX` bajo (≤ 20) y en mercados laterales probados.

---

## Backtesting

El módulo `src/backtest.py` incluye un backtester vectorial y `scripts/compare_strategies.py`
ejecuta la comparativa sobre tres escenarios sintéticos (trending / ranging / choppy).

```bash
pip install -r requirements.txt
PYTHONPATH=. python scripts/compare_strategies.py
```

Resultado típico (seeds fijos, random-walk sintético, R = riesgo por trade):

```
=== Baseline (mean-reversion + ADX>25 + RSI 35/60) ===
  [trending ] win_rate=20.0% | total_R=-2.33 | trades/día=1.7
  [ranging  ] win_rate=33.3% | total_R=-1.67 | trades/día=2.5
  [choppy   ] win_rate=10.0% | total_R=-7.33 | trades/día=2.0

=== Trend-pullback + BE@1R + trailing ===
  [trending ] win_rate=51.5% | total_R=+7.70 | trades/día=5.5
  [ranging  ] win_rate=38.6% | total_R=-4.47 | trades/día=7.3
  [choppy   ] win_rate=32.6% | total_R=-2.67 | trades/día=7.2
```

Con el filtro HTF activado en vivo los escenarios choppy se descartan casi por completo.

---

## Estructura del proyecto

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── src/
│   ├── config.py          # Carga de configuración
│   ├── oanda_client.py    # Wrapper de la API REST
│   ├── indicators.py      # RSI, ATR, ADX, EMA
│   ├── strategy.py        # Trend-pullback / mean-reversion
│   ├── sessions.py        # Detector de sesiones Londres/NY
│   ├── risk_manager.py    # Sizing, drawdown (NAV), cooldown
│   ├── trade_manager.py   # Breakeven + trailing stop
│   ├── backtest.py        # Backtester offline
│   ├── notifier.py        # Notificaciones a Telegram
│   ├── trade_logger.py    # Registro CSV de las entradas
│   ├── trader.py          # Bucle principal
│   └── main.py            # Entry-point
├── scripts/
│   └── compare_strategies.py
└── tests/
    ├── test_indicators.py
    ├── test_strategy.py
    ├── test_sessions.py
    ├── test_risk_manager.py
    ├── test_trade_logger.py
    └── test_backtest.py
```

---

## Puesta en marcha

### 1. Crear una cuenta demo en OANDA

1. Abre una cuenta gratuita en <https://www.oanda.com/demo-account/>.
2. Genera un **API token** desde *Manage API Access* en el panel de la cuenta.
3. Anota tu **Account ID** (formato `XXX-XXX-XXXXXXXX-XXX`).

### 2. Configurar variables de entorno

```bash
cp .env.example .env
$EDITOR .env   # rellena OANDA_API_KEY y OANDA_ACCOUNT_ID
```

Variables principales:

| Variable                | Descripción                                                | Default                            |
|-------------------------|------------------------------------------------------------|------------------------------------|
| `OANDA_API_KEY`         | Token personal de la API                                   | —                                  |
| `OANDA_ACCOUNT_ID`      | ID de la cuenta                                            | —                                  |
| `OANDA_ENVIRONMENT`     | `practice` (demo) o `live`                                 | `practice`                         |
| `INSTRUMENTS`           | Lista separada por comas                                   | `XAU_USD,EUR_USD`                  |
| `GRANULARITY`           | Velas de entrada                                           | `M1`                               |
| `GRANULARITY_HTF`       | Velas para confirmación de tendencia superior              | `M5`                               |
| `RISK_PER_TRADE`        | Fracción del balance a arriesgar por operación             | `0.01`                             |
| `MAX_CONCURRENT_TRADES` | Tope de trades abiertos                                    | `2`                                |
| `MAX_DAILY_LOSS`        | Drawdown diario máximo (NAV) antes de parar                | `0.05`                             |
| `ATR_SL_MULT`           | Multiplicador del ATR para el SL                           | `1.2`                              |
| `ATR_TP_MULT`           | Multiplicador del ATR para el TP                           | `2.0`                              |
| `STRATEGY_MODE`         | `trend_pullback` \| `mean_reversion`                       | `trend_pullback`                   |
| `MIN_ADX`               | ADX(14) mínimo para abrir trade                            | `20`                               |
| `RSI_BUY_THRESHOLD`     | RSI pullback para COMPRA                                   | `40`                               |
| `RSI_SELL_THRESHOLD`    | RSI pullback para VENTA                                    | `60`                               |
| `EMA_FAST`              | Periodo EMA rápida                                         | `20`                               |
| `EMA_SLOW`              | Periodo EMA lenta                                          | `50`                               |
| `HTF_CONFIRMATION`      | Exigir coincidencia con tendencia HTF                      | `true`                             |
| `BREAKEVEN_ENABLED`     | Mover SL a entry al alcanzar 1R                            | `true`                             |
| `BREAKEVEN_TRIGGER_R`   | Múltiplo de R para activar breakeven                       | `1.0`                              |
| `TRAILING_ENABLED`      | Activar trailing stop tras BE                              | `true`                             |
| `TRAILING_ATR_MULT`     | Distancia del trailing en múltiplos de ATR                 | `1.2`                              |
| `TRADE_COOLDOWN_SECONDS`| Tiempo de espera entre trades de un mismo instrumento      | `300`                              |
| `SPREAD_ATR_RATIO`      | Spread máximo permitido como fracción del ATR              | `0.15`                             |
| `SESSIONS_UTC`          | Sesiones permitidas                                        | `Londres:7-12,Nueva York:13-17`    |
| `LOOP_INTERVAL`         | Segundos entre análisis                                    | `20`                               |
| `LOG_LEVEL`             | `DEBUG`, `INFO`, `WARNING`, …                              | `INFO`                             |
| `TRADE_LOG_PATH`        | Fichero CSV con el histórico de entradas                   | `/app/logs/trades.csv`             |
| `TELEGRAM_BOT_TOKEN`    | Token del bot de Telegram (opcional)                       | *(vacío)*                          |
| `TELEGRAM_CHAT_ID`      | Chat ID al que enviar las notificaciones                   | *(vacío)*                          |

### Notificaciones por Telegram

Si defines `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en tu `.env`, el bot
enviará mensajes para arranque, aperturas/cierres de sesión, entradas
ejecutadas y errores. Si faltan credenciales, se silencian y el trading sigue.

### Registro CSV de entradas

Cada entrada persiste una fila en `TRADE_LOG_PATH` (por defecto
`/app/logs/trades.csv`). El directorio `./logs` está montado como volumen en
`docker-compose.yml`.

### 3. Ejecutar con Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f oanda-scalper
```

### 4. Ejecutar en local (sin Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

---

## Tests

```bash
pip install pytest pandas numpy python-dotenv
pytest -q
```

---

## Licencia

MIT
