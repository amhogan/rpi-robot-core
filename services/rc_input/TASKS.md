# RC Input Service — Claude Code Tasks

This file tracks outstanding implementation work for the `rc_input` service
and its integration into the OSCAR stack. Pick up from here in Claude Code.

---

## Context

The `rc_input` Docker service reads PWM signals from a FlySky FS-iA6 RC
receiver wired to the Raspberry Pi 5 GPIO and publishes control commands
to MQTT. It enables manual RC override of OSCAR's autonomous operation.

**Hardware:**
- FlySky FS-i6 transmitter + FS-iA6 receiver
- GPIO17 (Pin 11) ← CH1 Steering
- GPIO27 (Pin 13) ← CH2 Throttle
- GPIO22 (Pin 15) ← CH5 Override switch (SwA)

**MQTT topics published:**
- `oscar/control/rc`   → `{steering, throttle, ch1_raw, ch2_raw, ch5_raw, timestamp}`
- `oscar/control/mode` → `"rc"` | `"auto"`

---

## TODO

### 1. Host setup — enable pigpiod on the Pi
`pigpiod` must run on the host (not in a container) so it has direct `/dev/gpiomem`
access. The container connects to it over TCP.

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
sudo systemctl status pigpiod
```

Verify pigpiod is listening:
```bash
ss -tlnp | grep 8888
```

### 2. Add `rc_input` service to `docker/docker-compose.yml`

Add the following service block. Note `extra_hosts` is required so the
container can resolve `host.docker.internal` to reach pigpiod on the host.

```yaml
  rc_input:
    build: ../services/rc_input
    container_name: oscar_rc_input
    restart: unless-stopped
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      PIGPIO_ADDR: host.docker.internal
      PIGPIO_PORT: "8888"
      GPIO_CH1: "17"
      GPIO_CH2: "27"
      GPIO_CH5: "22"
      MQTT_BROKER: mqtt
      MQTT_PORT: "1883"
      MQTT_TOPIC_RC: oscar/control/rc
      MQTT_TOPIC_MODE: oscar/control/mode
      PWM_MIN: "1000"
      PWM_CENTER: "1500"
      PWM_MAX: "2000"
      DEADBAND: "30"
      OVERRIDE_THRESHOLD: "1700"
      SIGNAL_TIMEOUT: "0.5"
      PUBLISH_INTERVAL: "0.05"
    depends_on:
      - mqtt
```

### 3. Calibrate PWM values for your specific FS-i6

The FS-i6 sub-trim and end-point settings affect actual min/max pulse widths.
After wiring, run this one-liner on the Pi host to watch raw GPIO pulses and
confirm your actual min/center/max values before setting the env vars:

```bash
python3 -c "
import pigpio, time
pi = pigpio.pi()
pi.set_mode(17, pigpio.INPUT)
while True:
    print('CH1:', pi.get_servo_pulsewidth(17),
          'CH2:', pi.get_servo_pulsewidth(27))
    time.sleep(0.1)
"
```

Update `PWM_MIN`, `PWM_CENTER`, `PWM_MAX` in the compose env accordingly.

### 4. Integrate RC override into the motor control container

The motor controller needs to subscribe to `oscar/control/mode` and
`oscar/control/rc` and give RC commands priority when mode == `"rc"`.

In the motor control service:
- Subscribe to `oscar/control/mode` — store current mode
- Subscribe to `oscar/control/rc` — on message, if mode == `"rc"`, convert
  steering/throttle (-1.0 to +1.0) to RoboClaw speed commands
- Subscribe to `oscar/control/cmd_vel` — if mode == `"auto"`, use these instead
- On signal loss (mode flips back to `"auto"`), send stop command to RoboClaw

### 5. Test procedure

Once wired and deployed:

1. `docker compose up -d rc_input`
2. `docker compose logs -f rc_input` — confirm pigpiod connection
3. Subscribe to MQTT to watch live output:
   ```bash
   mosquitto_sub -h localhost -t "oscar/control/#" -v
   ```
4. Flip SwA switch UP on transmitter — confirm `oscar/control/mode` → `"rc"`
5. Move sticks — confirm `oscar/control/rc` values change correctly
6. Flip SwA DOWN — confirm mode returns to `"auto"`
7. Power off transmitter — confirm mode returns to `"auto"` within 0.5s

---

## Files Added

```
services/rc_input/
  rc_input.py         Main service — PWM reader + MQTT publisher
  Dockerfile          Builds pigpio from source + Python deps
  requirements.txt    pigpio==1.78, paho-mqtt==1.6.1
```
