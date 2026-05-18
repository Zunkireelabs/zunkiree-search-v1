# LLM Abstraction Layer

> Last Updated: December 26, 2024

---

## Overview

Zunkiree Search uses a clean LLM abstraction layer that allows models to be swapped or routed without refactoring. This design prioritizes cost efficiency, speed, and reliability at pilot scale.

---

## Model Tiers

| Tier | Model | Use Case | Cost |
|------|-------|----------|------|
| **Default** | `gpt-4o-mini` | All customer queries | ~$0.15/1M input tokens |
| **Premium** | `gpt-4o` | Complex/enterprise queries (future) | ~$2.50/1M input tokens |

**Design Principle:** Accuracy comes from retrieval quality, prompt grounding, and fallback rules - not from expensive models.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LLMService                            │
│  - generate_answer()                                     │
│  - _generate_suggestions()                               │
│                                                          │
│  Uses composition with BaseLLMProvider                   │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│               BaseLLMProvider (Abstract)                 │
│  + generate(system_prompt, user_message, ...)           │
└─────────────────────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│  OpenAIProvider  │          │  (Future)        │
│                  │          │  AnthropicProvider│
│  - gpt-4o-mini   │          │  AzureProvider    │
│  - gpt-4o        │          │  etc.             │
└──────────────────┘          └──────────────────┘
```

---

## Configuration

### Environment Variables

```env
# LLM Configuration
LLM_MODEL=gpt-4o-mini           # Default model
LLM_MODEL_PREMIUM=gpt-4o        # Premium model (future use)
LLM_PROVIDER=openai             # Provider selection (future)
```

### Python Config (`backend/app/config.py`)

```python
# LLM Configuration
llm_provider: str = "openai"
llm_model: str = "gpt-4o-mini"
llm_model_premium: str = "gpt-4o"
llm_temperature: float = 0.3
llm_max_tokens: int = 500
```

---

## Usage

### Default (gpt-4o-mini)

```python
from app.services.llm import get_llm_service

llm_service = get_llm_service()  # Uses default tier
result = await llm_service.generate_answer(
    question="What services do you offer?",
    context_chunks=[...],
    brand_name="Acme Corp",
)
```

### Premium (gpt-4o) - Future

```python
llm_service = get_llm_service(model_tier="premium")
```

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/llm.py` | LLM service with abstraction layer |
| `backend/app/config.py` | Configuration settings |
| `backend/.env` | Environment variables |

---

## Design Principles

1. **No hardcoding**: Model is configurable via environment variables
2. **Abstraction**: `BaseLLMProvider` interface enables future provider support
3. **Factory pattern**: `get_llm_service()` handles instantiation and caching
4. **Composition**: `LLMService` uses provider via composition, not inheritance
5. **Future-proof**: Model tier routing ready but not over-engineered

---

## Future Extensions (Not Built Yet)

- Query complexity scoring to auto-route to premium model
- Anthropic/Claude provider
- Azure OpenAI provider
- Per-customer model override in widget_configs table
- Fallback chain (if primary fails, try secondary)

---

## Related Documentation

- [Architecture](architecture.md) - System architecture overview
- [API Spec](api-spec.md) - API endpoint documentation
- [Implementation Plan](implementation-plan.md) - Build phases
