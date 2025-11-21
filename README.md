# rpi-robot-core

**rpi-robot-core** is the lean, Docker-first codebase for running and actively developing **RPi-Robot** — a Quantum J4 powerbase driven by a Raspberry Pi 5, containers, and ROS-inspired services.

The goals of this repo:

- Keep the runtime stack **modular and containerized** (voice, video, telemetry, motion, etc.).
- Make development **AI-assisted** using VS Code (Gemini, Copilot, or similar).
- Be the **single source of truth** for robot code, configs, and bring-up scripts.

---

## High-level architecture

At a high level, RPi-Robot is:

- A **Raspberry Pi 5** running Linux as the robot “brain”.
- A **Quantum J4** powerbase with **Roboclaw** motor controller for differential drive.
- A set of **Docker containers** providing:
  - Core services (MQTT, telemetry, robot orchestration)
  - Voice stack (Piper TTS, Whisper STT, voice gateway)
  - Video stack (camera streaming, web dashboard)
- A **web dashboard** for status, video, and eventually manual driving.
- An **AI-friendly dev flow** using VS Code dev containers.

---

## Repository layout

```text
rpi-robot-core/
  compose/        # docker compose files (stacks & overlays)
  docker/         # Dockerfiles and build contexts
  services/       # Python services (netstatus, voice gateway, drivers, etc.)
  site/           # Web dashboard (HTML/JS/CSS) served via nginx or similar
  scripts/        # Helper scripts for bring-up, maintenance, dev tooling
  .env.example    # Example environment variables for the stack
  MANIFEST.keep   # Placeholder for tracking generated / mounted paths
  README.md       # This file
