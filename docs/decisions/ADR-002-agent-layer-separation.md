# ADR 002: Separation of LiveKit Agent Worker from FastAPI Backend

## Status
Accepted

## Context
A common pitfall in voice application design is bundling long-running WebRTC worker processes into the HTTP request-response API gateway. WebRTC audio handling requires continuous event loops, low-latency audio frame buffers, and real-time state machines, whereas FastAPI is optimized for stateless REST/WebSocket operations (token issuing, session storage, health probes).

## Decision
Separate the codebase into two distinct Python modules:
1. `backend/`: FastAPI application handling HTTP REST APIs, system health monitoring, authentication, and data contracts.
2. `agents/`: Dedicated LiveKit Agents worker application responsible for WebRTC track handling, speech streaming, and turn arbitration.

## Consequences
- **Positive**: Independent scalability; agent worker restarts do not take down REST APIs; clear operational boundaries.
- **Negative**: Requires shared contract models or duplicate schemas if not maintained with care.
