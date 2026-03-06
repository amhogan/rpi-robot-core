## 2025-12-05 – Dashboard v1 online

- Retired legacy `video-dashboard` (8081).
- `robot-dashboard` (nginx:1.27-alpine) is now the single UI on port 8080.
- Features:
  - Live MJPEG camera feed via camera_server `/video.mjpg` proxied as `/video_feed`.
  - Manual drive controls hitting motion_status `/command`.
  - System status via netstatus `/status` (host + voice stack).
  - RoboClaw & battery status via motion_status `/status_motion`.
