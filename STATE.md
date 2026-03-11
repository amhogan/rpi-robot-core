## 2025-12-05 – Dashboard v1 online

- Retired legacy `video-dashboard` (8081).
- `robot-dashboard` (nginx:1.27-alpine) is now the single UI on port 8080.
- Features:
  - Live MJPEG camera feed via camera_server `/video.mjpg` proxied as `/video_feed`.
  - Manual drive controls hitting motion_status `/command`.
  - System status via netstatus `/status` (host + voice stack).
  - RoboClaw & battery status via motion_status `/status_motion`.

## RC Input (Pending)
- RC Input — host setup: enable pigpiod on Pi (`sudo systemctl enable pigpiod && sudo systemctl start pigpiod`).
- RC Input — add `rc_input` service block to `docker/docker-compose.yml` (see `services/rc_input/TASKS.md`).
- RC Input — calibrate PWM min/center/max values for the FS-i6 transmitter and update compose env vars.
- RC Input — integrate RC override into motor control container (subscribe to `oscar/control/mode` and `oscar/control/rc`).
- RC Input — end-to-end test procedure (see `services/rc_input/TASKS.md` §5).
