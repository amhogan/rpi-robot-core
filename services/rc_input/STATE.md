# Robot Project Status Report
**Date:** 2025-08-10  
**System:** RPi-Robot (Raspberry Pi 5, Ubuntu, Docker, ROS 2 Iron)

## 1. Current Working Components
- Video Stream: operational via web_video_server (`/stream?topic=/camera/image_raw`).
- System Metrics: CPU temperature + uptime displayed correctly.
- Networking: Nginx proxy healthy; dashboard reachable; inter-container DNS OK.

## 2. Partially Working / In Progress
- Dashboard Stats: CPU%, memory%, disk% placeholders still blank.
- netstatus: serving temp/uptime; needs more metrics endpoints.
- RoboClaw: in bootloader recovery; USB recognized; Motion Studio pending.

## 3. Outstanding Issues
1) Extend netstatus to expose CPU%, Mem%, Disk%, (optional) Net I/O.
2) Complete RoboClaw firmware recovery and regain motor control.
3) Verify all containers restart on boot.
4) Add backup automation via systemd timer (script exists).
5) RC Input — host setup: enable pigpiod on Pi (`sudo systemctl enable pigpiod && sudo systemctl start pigpiod`).
6) RC Input — add `rc_input` service block to `docker/docker-compose.yml` (see `services/rc_input/TASKS.md`).
7) RC Input — calibrate PWM min/center/max values for the FS-i6 transmitter and update compose env vars.
8) RC Input — integrate RC override into motor control container (subscribe to `oscar/control/mode` and `oscar/control/rc`).
9) RC Input — end-to-end test procedure (see `services/rc_input/TASKS.md` §5).

## 4. Next Steps
- Short-term: expand netstatus; wire up dashboard; retest.
- RC Input: wire FS-iA6 receiver to GPIO → enable pigpiod → add service to compose → integrate motor override.
- Long-term: GPS integration; patrol/security features; manual driving controls.


## ✅ Completed Since Last Update
- 2025-08-14 – CHECK FAIL: Web Video Server streams not reachable at http://localhost:8080/streams.
- 2025-08-14 – CHECK PASS: Netstatus via Nginx reachable at http://localhost:8081/status.
- 2025-08-14 – CHECK PASS: Dashboard root reachable at http://localhost:8081/.
- 2025-08-14 – Added convenience links: `/home/pi/robot-docker.new` and `/home/pi/robot-dashboard.new`.
- 2025-08-14 – Consolidated repos into `/home/pi/robot-project` monorepo layout.
- 2025-08-14 – Migrated ROS 2 workspace: `/home/pi/robot-docker/robot_ws` → `/home/pi/robot-project/robot_ws`.
- 2025-08-14 – Migrated dashboard static files: `/home/pi/robot-dashboard` → `/home/pi/robot-project/site`.
- 2025-08-12 – CHECK FAIL: Web Video Server streams not reachable at http://localhost:8080/streams.
- 2025-08-12 – CHECK PASS: Netstatus via Nginx reachable at http://localhost:8081/status.
- 2025-08-12 – CHECK PASS: Dashboard root reachable at http://localhost:8081/.
- 2025-08-12 – Added convenience links: `/home/pi/robot-docker.new` and `/home/pi/robot-dashboard.new`.
- 2025-08-12 – Consolidated repos into `/home/pi/robot-project` monorepo layout.
- 2025-08-12 – Created `Makefile` (make up / logs / rebuild / ps / restart).
- 2025-08-12 – Added `docker/.env` with default ports.
- 2025-08-12 – Created compose scaffold: `docker/compose/ros.yml`.
- 2025-08-12 – Created compose scaffold: `docker/compose/web.yml`.
- 2025-08-12 – Created compose scaffold: `docker/compose/base.yml`.
- 2025-08-12 – Migrated ROS 2 workspace: `/home/pi/robot-docker/robot_ws` → `/home/pi/robot-project/robot_ws`.
- 2025-08-12 – Migrated dashboard static files: `/home/pi/robot-dashboard` → `/home/pi/robot-project/site`.
