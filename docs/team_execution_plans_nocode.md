# 🚀 Senior Engineer's Master Execution Plan
## AI-Powered Renewable Generation Forecasting Platform
**Team Size:** 4 Members (1 ML Expert, 3 SWE/Infra) | **Rule:** No Code in this document, only actionable architecture and workflows.

---

## 🤖 Member 1: ML Engineer (The Sole ML Expert)
**Your Mission:** You own the core intelligence of the platform. You must transform raw weather data into probabilistic generation forecasts, and write the mathematical engine that calculates the financial penalties (DSM). 

### 1. Data & Physics Simulation
*   **Data Acquisition:** Download the NASA POWER solar dataset (hourly) and the Open-Meteo "Previous Runs" dataset. *Crucial:* Do not use ERA5 reanalysis; use the "as-issued" forecasts to simulate what the model would actually know the day before.
*   **Resolution Alignment:** Convert all hourly weather data into 15-minute blocks using linear interpolation. Add Indian Standard Time (IST) for display but keep UTC for internal math. Add block numbers (1 to 96) for each day.
*   **Physics Layer:** Build a solar physics simulator using the `pvlib` library. It must take the weather data and plant coordinates to calculate Sun Position, Plane-of-Array Irradiance, Cell Temperature, and finally theoretical DC/AC power. Do a similar exercise for wind using a fitted sigmoid power curve. *This is not the final forecast—it is the strongest feature for your ML model.*

### 2. Machine Learning Pipeline
*   **Feature Engineering:** Create features for solar geometry, clear-sky index, cyclical time (sine/cosine of hour and day of year), and historical generation lags.
*   **Leakage Prevention:** Ensure your minimum lag is at least 96 blocks (24 hours). If you feed a 1-hour lag into a day-ahead model, the model will cheat, and it will fail in production.
*   **LightGBM Quantile Model:** Train a LightGBM model using a quantile objective. You must train it to output 19 different percentiles (P05, P10 ... P90, P95). This creates the "Fan Chart" uncertainty bands. Use isotonic regression to ensure quantiles don't cross (e.g., P10 should never be higher than P90).
*   **Chronos-2 Integration:** Set up Amazon's Chronos-2-small model for zero-shot forecasting. Use this specifically for "cold start" scenarios where a new plant has no historical data.
*   **Evaluation:** Create a rolling-origin backtest. Do not use random train/test splits for time series. Calculate CRPS (Continuous Ranked Probability Score), Pinball Loss, and Mean Absolute Error (MAE).

### 3. DSM Math & Optimization
*   **The Engine:** Read the CERC 2024 and 2026 Amendment PDFs carefully. Write a pure Python class that takes a scheduled MW and actual MW, applies the "X-trajectory" tolerance band, and applies the frequency multipliers. *Remember: Use the Renewable Generator (Seller) formula, not the Discom (Buyer) formula.*
*   **Optimization:** Write a grid-search algorithm that tests every possible schedule (from 0 to plant capacity) against all 19 of your ML quantiles to find the schedule that minimizes the *expected* ₹ penalty.
*   **Battery LP:** Formulate a Linear Programming problem (using PuLP) to dispatch a battery across the 96 blocks to further minimize DSM penalties.

**Handoffs:** You will hand over pre-trained model files, feature schemas, and pure Python classes for the DSM engine and optimizer to Member 2.

---

## 🔧 Member 2: Backend Engineer
**Your Mission:** You are the glue. You take Member 1's math and models, wrap them in a fast, robust REST API using FastAPI, and build the automated daily pipeline that stores everything in PostgreSQL.

### 1. Database & Schema Design
*   **ORM Setup:** Use SQLAlchemy and Alembic. Design tables for `plants`, `weather_forecasts`, `probabilistic_forecasts`, `schedules`, `dsm_results`, and `actions` (curtailment/battery).
*   **Foreign Keys:** Everything hinges on `plant_id` and `timestamp` (15-min block valid time). Ensure strict indexing on these columns for fast dashboard queries.

### 2. Daily Data Pipeline (The "Cron Job")
*   **Live Ingestion:** Write a script that hits the live Open-Meteo API to get the next 72 hours of weather for all plants in the database.
*   **Data Quality:** Write a validator that checks for missing data. If gaps are less than an hour, forward-fill them. If greater, flag the block as "low confidence" so the UI can warn the operator. Convert the hourly pull to 15-min blocks.
*   **Orchestration:** Build a single script that runs the daily flow: Fetch Weather -> Run Feature Engineering -> Call Member 1's ML Model -> Call Member 1's Optimizer -> Save the final P50 and optimized schedules to the DB. 

### 3. API Development
*   **Endpoints:** Build the API endpoints the frontend needs: `/plants`, `/forecast`, `/dashboard`, `/dsm` (for what-if calculations), and `/pooling` (to calculate savings if multiple plants are combined).
*   **Performance:** Do *not* run ML inference while the user waits for an HTTP response. The dashboard endpoints should only query pre-calculated results from the database. The only dynamic endpoint is the RAG chat and the "What-If" slider (which runs the fast DSM math, not the ML model).

**Handoffs:** You will provide a Swagger/OpenAPI spec and a base URL to Member 3 on Day 1.

---

## ⚛️ Member 3: Frontend Engineer
**Your Mission:** The judges will judge the book by its cover. You must build a React dashboard that looks like a high-end enterprise SCADA system. 

### 1. Mock-First Development
*   **Rule #1:** Do not wait for the Backend API to be ready. Ask Member 1 for a sample CSV of the data. Convert it to JSON and build your entire UI against this static JSON file. You will swap the base URL to the real API on Day 12.

### 2. Core Visualizations
*   **The Fan Chart:** Use Recharts or D3 to build the core forecasting chart. It must have 96 blocks on the X-axis. You need a dark center line (P50), a medium shaded band (P25-P75), and a light shaded band (P10-P90). Plot the "Submitted Schedule" as a dashed orange line over this.
*   **Risk Heatmap:** Build a 96-block grid. Color code it: Green (no penalty), Yellow (small penalty), Red (high penalty exposure). This instantly tells the grid operator where their day is at risk.
*   **Financial Impact:** Build side-by-side bar charts showing "Naive Schedule Penalty ₹" vs "AI-Optimized Schedule Penalty ₹". Show the exact percentage of money saved.

### 3. Interactivity & "What-If" Tools
*   **Regulation Slider:** Build a slider with the years 2026, 2027, 2028, 2030, 2031. When the user slides it, hit the `/dsm` API to recalculate the penalties using the stricter future rules, and instantly update the heatmap.
*   **Pooling Toggle:** Add a switch to "Combine Portfolios". Show how combining a wind and solar plant reduces the net penalty.
*   **RAG Copilot Panel:** Build a chat interface. When the user asks "Why am I penalized in block 40?", show the response with clickable citation badges that reference CERC legal clauses.

**Handoffs:** You will package the final static build (HTML/CSS/JS) and give it to Member 4 to deploy on AWS CloudFront.

---

## ☁️ Member 4: Infra + RAG Engineer
**Your Mission:** You ensure the platform is live on the internet, secure, and you build the Generative AI component that explains the complex regulations to the users.

### 1. RAG Copilot (Generative AI)
*   **Document Ingestion:** Take the CERC DSM 2024, 2026, and IEGC 2023 PDFs. Do not use a naive character splitter. Write a script using PyMuPDF that splits the text based on actual legal clauses (e.g., "Clause 4.1"). Add metadata for Page Number and Document Name.
*   **Vector Database:** Embed these chunks using a fast embedding model (like bge-m3). Store them in the PostgreSQL database using the `pgvector` extension.
*   **Hybrid Retrieval:** When a user asks a question, search using both vector similarity (dense) and keyword matching (BM25). Rerank the top results to get the most relevant 5 paragraphs.
*   **LLM Integration:** Use LiteLLM to route the prompt to Groq (Llama 3 70B for blazing speed) with a fallback to Gemini Flash. 
*   **Prompt Engineering:** *Crucial Constraint:* You must instruct the LLM that it is an explainer, not a calculator. It must read the ₹ penalty value from the API payload and explain the *why* using the retrieved documents. It must never invent a ₹ number.

### 2. Infrastructure & Deployment
*   **Dockerization:** Write a `Dockerfile` for the FastAPI backend and a `docker-compose.yml` that stands up the backend, the PostgreSQL DB, and pgvector together. Ensure the team can run `docker compose up` locally.
*   **AWS Setup:** Spin up an EC2 instance for the backend container. Set up a managed RDS PostgreSQL database. 
*   **Frontend Hosting:** Put the React build artifacts into an S3 bucket and serve it globally via Amazon CloudFront.
*   **CI/CD:** Write GitHub Actions. Whenever code is pushed to the `main` branch, it should automatically run tests, build the Docker image, push it to ECR, and restart the EC2 service.
*   **Secrets:** Never commit API keys. Store the Groq/Gemini keys and DB passwords in AWS SSM Parameter Store.

**Handoffs:** You will provide the live, public URLs for the frontend and backend to the team, and manage the Git repository's branch protections.
