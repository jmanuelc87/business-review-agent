# Dataset sintético para la demo de QBR (Business Review ejecutivo)

Paquete de datos coherente para la demo capstone con LangGraph: **el analista
text-to-SQL encuentra el _qué_ (los números) y el RAG encuentra el _por qué_
(tickets + notas)**, hablando siempre de las mismas cuentas ficticias.

- **Empresa proveedora:** *Nimbus Cloud* (SaaS B2B). Es quien hace el QBR.
- **Periodo:** Q1-2026 (ene–mar) y Q2-2026 (abr–jun). El QBR es del **Q2**.
- **Reproducible:** `python3 generate_qbr_data.py` regenera todo idéntico (semilla fija).

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `qbr.db` | Base **SQLite** → fuente del **analista text-to-SQL** (`SQLDatabaseToolkit`) |
| `docs_rag/*.md` | Un `.md` por cuenta (nota + sus tickets) → corpus del **RAG** (vector store) |
| `notas_cuenta/*.md` | Solo las notas cualitativas, por si las quieres por separado |
| `*.csv` | Misma data en CSV (para inspección rápida o si prefieres cargar a pandas) |
| `generate_qbr_data.py` | El generador, por si quieres ajustar la historia |

## La historia plantada (tu "cheat sheet" como presentador)

Cada cuenta demuestra **una combinación distinta** de señales. Esto es lo que hace
buena a la demo: muestra por qué necesitas *ambos* agentes.

| Cuenta | Arco | Ingresos Q1→Q2 | Uso Q1→Q2 | Tickets / CSAT Q2 | Lo que prueba |
|---|---|---|---|---|---|
| **Acme** | Riesgo **ruidoso** | ↓ -24% (con notas de crédito) | ↓ -24% | 37 / 1.8 | El riesgo se ve en **números Y texto** (caídas P1, champion se fue, evalúa competidor) |
| **Hooli** | **Churn silencioso** | = plano | ↓ **-37%** | **1** / — | El riesgo se ve **solo en los números**; casi no hay tickets → necesitas al analista |
| **Initech** | **Fricción** | = plano | ≈ plano | 22 / 2.9 | La señal está **sobre todo en el texto** (bugs de reportes) → necesitas al RAG |
| **Globex** | **Expansión** | ↑ +17% | ↑ +15% | sano | La buena noticia / oportunidad de upsell |
| **Umbrella** | **Logo nuevo** | ↑ (rampa) | ↑ +91% | onboarding | Cuenta joven adoptando bien |
| **Soylent** | **Estrella estable** | = alto | = alto | pocos / alto | Cuenta de referencia / case study |

> El contraste **Acme vs Hooly** es el momento de oro: ambas renuevan en Q3-2026 y
> ambas están en riesgo, pero una grita y la otra está callada. Si solo miraras
> facturación, perderías a Hooli.

## Esquema de `qbr.db`

- `accounts` — `account_id, name, industry, country, region, segment, csm_owner, contract_start, renewal_quarter, seats_contracted`
- `subscriptions` — `account_id, product, plan_tier, seats, monthly_price`
- `invoices` — `invoice_id, account_id, invoice_date, quarter, amount, status` (status incluye `credited`)
- `usage_monthly` — `account_id, month, active_users, api_calls, logins, feature_adoption_score`
- `support_tickets` — `ticket_id, account_id, created_date, quarter, channel, category, priority, status, csat, subject, description`
- `account_health` — `account_id, quarter, nps, csat_avg, health_score`

## Preguntas que funcionan bien en la demo

**Para el analista (text-to-SQL):**
- "¿Qué cuentas tuvieron caída de ingresos del Q1 al Q2 de 2026?"
- "Muéstrame el cambio porcentual de usuarios activos por cuenta entre Q1 y Q2."
- "¿Qué cuentas renuevan en Q3-2026 y cuál es su health score?"
- "Top 3 cuentas por volumen de tickets P1 en Q2."

**Para el RAG (cualitativo):**
- "¿Por qué cayó la cuenta de Acme este trimestre?" → caídas P1, salida del champion, competidor.
- "¿Qué problema concentra los tickets de Initech?" → reportes/tableros (bugs y solicitudes).
- "¿Hay alguna cuenta con churn silencioso?" → Hooli (nota lo explica).

**La pregunta capstone (necesita los dos):**
- "Genera el business review del Q2-2026: identifica las cuentas en riesgo, con los números que lo respaldan y la explicación de qué está pasando en cada una."
  → el analista trae la caída de Acme y de Hooli (números); el RAG explica el porqué;
  el redactor sintetiza el informe.
