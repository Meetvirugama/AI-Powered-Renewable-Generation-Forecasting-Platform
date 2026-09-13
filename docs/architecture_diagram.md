# GridMind — Architecture at a Glance

A one-page visual map. Each diagram is explained in
[system_architecture.md](system_architecture.md).

---

## The whole system

```mermaid
flowchart TB
    subgraph sources [External sources]
        OM["Open-Meteo<br/>72 h weather"]
        INV["OpenStreetMap · GPPD<br/>plant inventory"]
        PDF["CERC DSM regulations"]
        LLMS["Groq · Gemini"]
    end

    subgraph backend [FastAPI backend]
        direction TB
        subgraph predict [Predict]
            WX["Weather provider<br/>cached 15 min"]
            SOLAR["LightGBM<br/>P10 · P50 · P90<br/>24 / 48 / 72 h"]
            WINDE["Wind power curve"]
        end
        subgraph decide [Price and decide]
            DSM["DSM engine<br/>2024 · 2026 · 2031 rules"]
            OPT["Optimiser<br/>201 candidates per block"]
            BAT["Battery recourse"]
            POOL["Pooling"]
            ACT["Action cards"]
        end
        subgraph explain [Explain]
            RET["Retriever<br/>BM25 + pgvector"]
            GRD["Guardrail"]
        end
        PIPE["Daily pipeline"]
    end

    subgraph store [Storage]
        PG[("PostgreSQL<br/>10 tables + pgvector")]
        CFG["config/*.yaml"]
        MOD["prediction_bundle/models_v2"]
    end

    UI["React dashboard<br/>Overview · Forecast · Risk · Actions · Copilot"]

    OM --> WX
    WX --> SOLAR & WINDE
    MOD --> SOLAR
    SOLAR & WINDE -->|"P05–P95"| OPT & POOL
    CFG --> DSM
    DSM --> OPT & POOL
    OPT --> BAT
    OPT --> ACT
    INV --> PG
    PDF -->|"offline build"| PG
    PG --> RET --> GRD
    GRD <--> LLMS
    PIPE --> PG
    UI <-->|"REST / JSON"| backend
```

---

## Value chain

```mermaid
flowchart LR
    A["Weather"] --> B["Probabilistic<br/>forecast"]
    B --> C["₹ penalty<br/>per quantile"]
    C --> D["Minimum<br/>expected ₹ schedule"]
    D --> E["Actions and<br/>pooling"]
    E --> F["Cited<br/>explanation"]

    classDef compute fill:#1B2321,stroke:#CFF245,color:#E9EFEC
    classDef explain fill:#131917,stroke:#6EA8FF,color:#E9EFEC
    class A,B,C,D,E compute
    class F explain
```

Everything in the lime-bordered steps is deterministic code. The blue step is the only place a
language model is involved, and it receives the figures rather than producing them.

---

## Where each rupee figure comes from

```mermaid
flowchart LR
    FC["Forecast fan"] --> DSM["DSMEngine"]
    RULES["rule YAML"] --> DSM
    DSM --> OPTR["/optimize totals"]
    DSM --> DSMR["/dsm per block"]
    DSM --> POOLR["/pooling totals"]
    OPTR & DSMR --> UI["Dashboard tiles,<br/>heatmap, action cards"]
    DSMR -->|"context"| RAG["/rag/query"]
    RAG -->|"engine_values echoed"| UI
    RAG -.->|"answer prose,<br/>numbers guardrailed"| UI
```

---

## Forecast engine routing

```mermaid
flowchart TD
    REQ["generate_forecast(plant)"] --> T{"plant type"}
    T -- wind --> W["WindPhysicsEngine<br/>always"]
    T -- solar --> M{"FORECAST_ENGINE_TYPE"}
    M -- mock --> MK["MockForecastEngine"]
    M -- production --> LG["LGBMForecastEngine"]
    LG --> GATE{"physics gate<br/>and completeness"}
    GATE -- pass --> OUT["96 blocks, MW"]
    GATE -- fail --> ERR["refuse"]
    W --> OUT
    MK --> OUT
```

---

## Production deployment

```mermaid
flowchart LR
    USER["Operator browser"] --> VER["Vercel<br/>static React build"]
    USER -->|"HTTPS"| CADDY

    subgraph vm [Azure VM]
        CADDY["Caddy<br/>Let's Encrypt"] --> API["uvicorn<br/>systemd"]
    end

    API --> SUPA[("Supabase<br/>PostgreSQL")]
    API --> OMX["Open-Meteo"]
    API --> LLMX["Groq · Gemini"]

    GH["GitHub Actions<br/>ci → deploy"] -->|"SSH, health gate,<br/>auto rollback"| API
```

An alternative AWS path (CloudFront, S3, ALB, EC2, RDS, EventBridge, CloudWatch) is kept in
`infra/aws/` and `infra/terraform/`.

---

## Seed portfolio

The four plants in `config/plants.yaml`, used by tests and offline demos. Production serves 101
imported Gujarat plants.

| Plant | Type | Capacity | Location | Pool |
|---|---|---|---|---|
| GJ_SOLAR_A | solar | 50 MW | near Gandhinagar (23.22, 72.64) | GJ_POOL_1 |
| GJ_SOLAR_B | solar | 75 MW | near Rajkot (22.30, 70.80) | GJ_POOL_1 |
| GJ_WIND_C | wind | 40 MW, 120 m hub | near Kutch (23.61, 68.98) | GJ_POOL_1 |
| GJ_SOLAR_D | solar | 30 MW, bifacial | near Palanpur (24.19, 72.43) | GJ_POOL_2 |

---

## One day in blocks

A day is 96 fifteen-minute blocks. Block 1 is 00:00–00:15 IST. Block numbers are derived from
the IST wall clock, not UTC, so block 1 is always local midnight.

| Blocks | IST | Typical solar exposure |
|---|---|---|
| 1–24 | 00:00–06:00 | none |
| 25–40 | 06:00–10:00 | ramp-up, high relative error |
| 41–64 | 10:00–16:00 | peak output, largest absolute ₹ exposure |
| 65–76 | 16:00–19:00 | ramp-down |
| 77–96 | 19:00–24:00 | none |
