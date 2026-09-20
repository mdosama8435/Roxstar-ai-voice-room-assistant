# RoxStar AI Voice Room Assistant - Agent Layer

LiveKit Agent orchestration, speech adapters, and dual-bot arbitration layer for the RoxStar AI Voice Room Assistant.

## Overview
This package contains:
- Persona definitions for **Roxstar AI Dost** and **Roxstar AI Sathi**.
- Abstract provider interfaces for Sarvam Saaras (STT) and Sarvam Bulbul v3 (TTS).
- Dual-bot arbitration and turn mutex locking protocols (`BotRouter`, `TurnLockManager`).
- Ephemeral session memory and semantic long-term memory protocols.

## Personas
- **Roxstar AI Dost**: Male, friendly Hindi/Hinglish persona with brotherly warmth. Voice: `bulbul-v3-male-hindi`.
- **Roxstar AI Sathi**: Female, warm Hindi/Hinglish persona with articulate nuance. Voice: `bulbul-v3-female-hindi`.

## Local Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Tests
```bash
python -m pytest tests/ -v
```

### 3. Run Agent Runner
```bash
python -m app.main
```
