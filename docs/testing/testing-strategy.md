# Testing Strategy & Quality Assurance

Quality assurance for the RoxStar AI Voice Room Assistant follows a strict multi-tier verification model.

---

## 1. Phase 1 Testing Scope
In Phase 1, tests strictly test real, implemented functionality:
- **Backend**:
  - `backend/tests/test_health.py`: Validates `/health` endpoint availability and response signature.
  - `backend/tests/test_config.py`: Validates graceful configuration defaults, environment overrides, and lack of crashes when optional keys are absent.
  - `backend/tests/test_schemas.py`: Validates Pydantic serialization, validation, and contract integrity across all data schemas.
- **Agent Layer**:
  - `agents/tests/test_contracts.py`: Validates persona definitions and arbitration structures.
  - `agents/tests/test_interfaces.py`: Validates that protocol contracts (STT, TTS, LLM, Router, Memory) conform to their expected signatures without instantiating fake external clients.
- **Frontend**:
  - TypeScript compilation and type checks (`tsc --noEmit`).
  - Next.js build verification (`npm run build`).

---

## 2. Testing Principles
- **No Fake Asserts**: Never write tests that mock fake AI conversations or hardcoded fake latency just to make a test pass.
- **Contract Driven**: Schemas are the source of truth between frontend, backend, and agent workers.
- **Fast Execution**: Unit and contract tests must run in < 5 seconds to enable fast developer feedback loops.
