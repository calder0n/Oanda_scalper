# Oanda Scalper

Bot de **scalping** en Python para operar en la API de **OANDA**. Está pensado
para correr dentro de un contenedor Docker, en una cuenta **demo (practice)**, y
empieza por defecto con dos instrumentos: **XAU_USD (Oro)** y **EUR_USD**.

> ⚠️  Aviso: el trading apalancado conlleva un alto riesgo de pérdida. Este
> proyecto se entrega con fines educativos. **Pruébalo siempre en cuenta demo
> antes de usarlo con dinero real.**

---

## Estrategia

Estrategia mean-reversion sobre RSI con filtros estrictos de calidad:

1. **Filtro horario** — solo se opera durante las sesiones de Londres
   (07:00–12:00 UTC) y Nueva York (13:00–17:00 UTC), las dos ventanas de mayor
   liquidez. Configurable con `SESSIONS_UTC`.
2. **Filtro de fuerza de tendencia** — `ADX(14) > 25`. Si el mercado está
   lateral, el bot no opera (evita el ruido de las laterales).
3. **Filtro de spread dinámico** — `spread < ATR × 0.15`. Si el spread se
   ensancha (típico fuera de horas o cerca de noticias), se descarta el trade.
   Crítico para XAU_USD.
4. **Disparador de entrada** sobre RSI(14):
   - **COMPRA** si `RSI ≤ 35`
   - **VENTA** si `RSI ≥ 60`

Cada operación se ejecuta como una **orden de mercado** con `stopLossOnFill` y
`takeProfitOnFill` calculados con el ATR:

- `SL = entry ± ATR × 1.5`
- `TP = entry ± ATR × 2.5`  → ratio R:R ≈ **1:1.66**

### Gestión de riesgo

- **Riesgo por trade**: 1% del balance (configurable).
- **Tamaño de posición**: calculado automáticamente para que la distancia hasta
  el stop iguale al riesgo permitido.
- **Máximo de operaciones simultáneas**: 2 (configurable).
- **Drawdown diario**: si la pérdida del día supera el 5% del balance inicial
  del día, el bot se pausa hasta el día siguiente.
- **Una posición por instrumento** a la vez.

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
│   ├── indicators.py      # RSI, ATR, ADX
│   ├── strategy.py        # Disparadores RSI + filtro ADX
│   ├── sessions.py        # Detector de sesiones Londres/NY
│   ├── risk_manager.py    # Sizing y drawdown diario
│   ├── notifier.py        # Notificaciones a Telegram
│   ├── trade_logger.py    # Registro CSV de las entradas
│   ├── trader.py          # Bucle principal
│   └── main.py            # Entry-point
└── tests/
    ├── test_indicators.py
    ├── test_strategy.py
    ├── test_sessions.py
    ├── test_risk_manager.py
    └── test_trade_logger.py
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
| `GRANULARITY`           | Velas: `M1`, `M5`, `M15`, `M30`, `H1`, …                   | `M1`                               |
| `RISK_PER_TRADE`        | Fracción del balance a arriesgar por operación             | `0.01`                             |
| `MAX_CONCURRENT_TRADES` | Tope de trades abiertos                                    | `2`                                |
| `MAX_DAILY_LOSS`        | Drawdown diario máximo antes de parar                      | `0.05`                             |
| `ATR_SL_MULT`           | Multiplicador del ATR para el SL                           | `1.5`                              |
| `ATR_TP_MULT`           | Multiplicador del ATR para el TP                           | `2.5`                              |
| `MIN_ADX`               | ADX(14) mínimo para abrir trade                            | `25`                               |
| `RSI_BUY_THRESHOLD`     | RSI(14) ≤ valor → señal de COMPRA                          | `35`                               |
| `RSI_SELL_THRESHOLD`    | RSI(14) ≥ valor → señal de VENTA                           | `60`                               |
| `SPREAD_ATR_RATIO`      | Spread máximo permitido como fracción del ATR              | `0.15`                             |
| `SESSIONS_UTC`          | Sesiones permitidas en formato `Nombre:H_inicio-H_fin`     | `Londres:7-12,Nueva York:13-17`    |
| `LOOP_INTERVAL`         | Segundos entre análisis                                    | `20`                               |
| `LOG_LEVEL`             | `DEBUG`, `INFO`, `WARNING`, …                              | `INFO`                             |
| `TRADE_LOG_PATH`        | Fichero CSV con el histórico de entradas                   | `/app/logs/trades.csv`             |
| `TELEGRAM_BOT_TOKEN`    | Token del bot de Telegram (opcional)                       | *(vacío)*                          |
| `TELEGRAM_CHAT_ID`      | Chat ID al que enviar las notificaciones                   | *(vacío)*                          |

### Notificaciones por Telegram

Si defines `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en tu `.env`, el bot
enviará mensajes para los siguientes eventos:

- 🟢 **Arranque del bot**: entorno, instrumentos, sesiones configuradas y balance.
- 📈 **Apertura de sesión** (Londres / Nueva York): nombre y horario de la sesión,
  hora actual UTC, instrumentos y balance.
- 🌙 **Cierre de sesión**: notificación de pausa hasta la siguiente sesión.
- 🟢/🔴 **Entrada ejecutada** con todos los valores que provocaron la decisión:
  sesión, dirección, unidades, entry, SL, TP, R:R, RSI, ADX, ATR, spread,
  balance, motivo y `order_id`.
- ⚠️ **Errores** críticos.

Cómo obtener un `chat_id`:

1. Crea tu bot con [@BotFather](https://t.me/BotFather) y guarda el token.
2. Inicia una conversación con tu bot y envíale cualquier mensaje.
3. Visita `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el valor de
   `"chat":{"id": …}`.

Si alguno de los dos valores queda vacío, las notificaciones se desactivan
silenciosamente y el trading sigue funcionando con normalidad.

### Registro CSV de entradas

Cada vez que el bot abre una operación, persiste una fila en
`TRADE_LOG_PATH` (por defecto `/app/logs/trades.csv`). El directorio `./logs`
está montado como volumen en `docker-compose.yml`, así que el fichero queda
también disponible en el host.

Columnas:

```
timestamp_utc, session, instrument, signal, units,
entry_price, stop_loss, take_profit,
atr, rsi, adx, spread,
balance, reason, order_id
```

### 3. Ejecutar con Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f oanda-scalper
```

Para detenerlo:

```bash
docker compose down
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

## Próximos pasos sugeridos

- Backtesting offline con datos históricos antes de tocar los parámetros.
- Trailing stop / break-even dinámico al alcanzar 1R de beneficio.
- Confirmación multi-timeframe (M1 → tendencia M5).
- Persistencia de métricas en una base de datos para visualización en Grafana.

---

## Licencia

MIT
