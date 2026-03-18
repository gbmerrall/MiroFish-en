# MiroFish Configuration Guide

This document outlines the core components of the MiroFish environment configuration and how to optimize them for large-scale simulations.

## 1. Core Components: LLM vs. ZEP

### LLM (Primary Inference Engine)
The **LLM** configuration is the "brain" of the project. It handles all high-level reasoning and text generation tasks:
*   **Ontology Generation:** Analyzing uploaded documents to define the world structure.
*   **Simulation Planning:** Determining time flow and agent activity patterns.
*   **Persona Creation:** Generating detailed character backgrounds (Agent Profiles).
*   **Report Generation:** Powering the **Report Agent** to analyze results and answer user questions.
*   **Primary Interaction:** Handles the Twitter-style ("Info Plaza") platform by default.

### ZEP (Memory & Knowledge Graph Layer)
**Zep** is the "world's memory." It is not an LLM, but a GraphRAG engine that stores the simulation state.

*   **SaaS Platform:** You can sign up and manage your knowledge graphs at [app.getzep.com](https://app.getzep.com/).
*   **API Key:** After signing up, you can generate your `ZEP_API_KEY` in the Project Settings or API Keys section of the Zep dashboard. The free tier monthly quota is typically sufficient for basic simulations.
*   **Temporal Knowledge Graph:** Records events, entities, and relationships as they evolve over time.
*   **Long-Term Memory:** Allows agents to "remember" past interactions across the entire simulation history.
*   **Semantic Retrieval:** Provides the deep search capabilities used by the Report Agent to find relationship chains and insights.

---

## 2. Recommended LLM Providers

MiroFish is compatible with any provider using the **OpenAI SDK format**. For best results, consider these alternatives to the default Alibaba Cloud setup:

*   **OpenAI (`gpt-4o-mini`):** The reliable standard. Fast, cheap, and excellent at reasoning.
*   **DeepSeek (`deepseek-chat`):** Extremely cost-effective with high-end performance. Perfect for token-heavy simulations.
*   **Groq:** The speed leader. Ideal for "Boost" configurations where you need instant replies from hundreds of agents.
*   **OpenRouter:** A single API to access models from Claude, OpenAI, and Meta. Great for testing different "brains" without changing your code.

---

## 3. Accelerated Dual-Platform Simulation (LLM_BOOST)

The `LLM_BOOST` configuration is an optional performance accelerator designed to solve the problem of **API Rate Limits (429 Errors)**.

### The Problem
During large simulations (Step 3), 50-100+ agents may attempt to post or reply simultaneously. Using a single API key for both Twitter and Reddit platforms will likely hit your provider's Requests Per Minute (RPM) or Tokens Per Minute (TPM) limits, causing the simulation to stall.

### The Solution
`LLM_BOOST` acts as a **secondary, independent LLM backend**. When running a parallel simulation:
1.  **Twitter Platform:** Sends requests to your primary `LLM_API_KEY`.
2.  **Reddit Platform:** Shards the workload by sending requests to the `LLM_BOOST_API_KEY`.

### Advantages
*   **Maximum Speed:** Double your throughput by utilizing two different providers or account tiers concurrently.
*   **Zero Conflict:** Prevents the activity on one social platform from slowing down the other.
*   **Cost & Capability Optimization:** You can use a "smarter" model (via OpenRouter/OpenAI) for orchestration and complex reasoning as your main engine, while using an "ultra-fast" model (via Groq) for the bulk of the social media interactions.

### Configuration Example
For a high-performance setup, use **OpenRouter** for logic and **Groq** for scale:

```env
# --- Main Engine (Reasoning & Orchestration) ---
LLM_API_KEY=your-openrouter-key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL_NAME=openai/gpt-4o-mini

# --- Accelerator (High-Speed Bulk Simulation) ---
LLM_BOOST_API_KEY=your-groq-key
LLM_BOOST_BASE_URL=https://api.groq.com/openai/v1
LLM_BOOST_MODEL_NAME=llama-3.3-70b-versatile
```
