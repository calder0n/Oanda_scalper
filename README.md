# Oanda Scalper

Bot de **scalping** en Python para operar en la API de **OANDA**. Está pensado
para correr dentro de un contenedor Docker, en una cuenta **demo (practice)**, y
empieza por defecto con dos instrumentos: **XAU_USD (Oro)** y **EUR_USD**.

> ⚠️  Aviso: el trading apalancado conlleva un alto riesgo de pérdida. Este
> proyecto se entrega con fines educativos. **Pruébalo siempre en cuenta demo
> antes de usarlo con dinero real.**

---

## Estrategia

Scalping multi-confirmación, intentando entrar a favor de la tendencia y solo en
los retrocesos a la EMA rápida:

1. **Tendencia**: `EMA9 > EMA21 > EMA50` para largos (a la inversa para cortos).
2. **Pullback**: la última vela toca la EMA9 y cierra en sentido de la
   tendencia.
3. **Momento**: `MACD` por encima de su señal y el histograma creciendo (al
   revés para cortos).
4. **RSI**: dentro del rango operable (40-70 en largos, 30-60 en cortos) para
   evitar entradas extendidas.
5. **Filtro de volatilidad**: ancho de Bollinger por encima de un mínimo y
   `ATR > 0`, para no operar mercado plano.

Cada operación se ejecuta como una **orden de mercado** con `stopLossOnFill` y
`takeProfitOnFill` calculados con el ATR:

- `SL = entry ± ATR * 1.5`
- `TP = entry ± ATR * 2.5`  → ratio R:R ≈ **1:1.66**

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
│   ├── indicators.py      # EMA, RSI, ATR, MACD, Bollinger
│   ├── strategy.py        # Lógica de la señal de scalping
│   ├── risk_manager.py    # Sizing y drawdown diario
│   ├── trader.py          # Bucle principal
│   └── main.py            # Entry-point
└── tests/
    ├── test_indicators.py
    └── test_risk_manager.py
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

Las variables más importantes:

| Variable                | Descripción                                                | Default          |
|-------------------------|------------------------------------------------------------|------------------|
| `OANDA_API_KEY`         | Token personal de la API                                   | —                |
| `OANDA_ACCOUNT_ID`      | ID de la cuenta                                            | —                |
| `OANDA_ENVIRONMENT`     | `practice` (demo) o `live`                                 | `practice`       |
| `INSTRUMENTS`           | Lista separada por comas                                   | `XAU_USD,EUR_USD`|
| `GRANULARITY`           | Velas: `M1`, `M5`, `M15`, `M30`, `H1`, …                   | `M1`             |
| `RISK_PER_TRADE`        | Fracción del balance a arriesgar por operación             | `0.01`           |
| `MAX_CONCURRENT_TRADES` | Tope de trades abiertos                                    | `2`              |
| `MAX_DAILY_LOSS`        | Drawdown diario máximo antes de parar                      | `0.05`           |
| `ATR_SL_MULT`           | Multiplicador del ATR para el SL                           | `1.5`            |
| `ATR_TP_MULT`           | Multiplicador del ATR para el TP                           | `2.5`            |
| `LOOP_INTERVAL`         | Segundos entre análisis                                    | `20`             |
| `LOG_LEVEL`             | `DEBUG`, `INFO`, `WARNING`, …                              | `INFO`           |

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

- Backtesting offline con datos históricos antes de cambiar parámetros.
- Trailing stop dinámico cuando se alcanza 1R de beneficio.
- Filtro horario para operar solo en sesiones de alta liquidez (Londres / NY).
- Notificaciones (Telegram, Discord) cuando se abren o cierran trades.
- Persistencia de métricas en una base de datos para visualización en Grafana.

---

## Licencia

MIT
