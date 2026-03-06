# roboclaw_3.py
# Python 3 compatible RoboClaw library (USB/Serial)
# Original source: BasicMicro API examples, adapted for Python 3
# Works with: RoboClaw 2x7A, 2x15A, 2x30A, 2x45A, 2x60A

import serial

class Roboclaw(object):
    def __init__(self, comport, baudrate):
        self.port = serial.Serial()
        self.port.port = comport
        self.port.baudrate = baudrate
        self.port.timeout = 0.01

    # ---------------------
    # Serial port open/close
    # ---------------------
    def Open(self):
        if not self.port.is_open:
            self.port.open()

    def Close(self):
        if self.port.is_open:
            self.port.close()

    # ---------------------
    # Internal helpers
    # ---------------------
    def _crc16(self, data):
        crc = 0
        for b in data:
            crc ^= (b << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
            crc &= 0xFFFF
        return crc

    def _write_checksum(self, address, cmd, *data):
        packet = bytearray()
        packet.append(address)
        packet.append(cmd)
        for d in data:
            packet.append(d)
        crc = self._crc16(packet)
        packet.append((crc >> 8) & 0xFF)
        packet.append(crc & 0xFF)
        self.port.write(packet)

    def _read_with_crc(self, expected_len):
        data = self.port.read(expected_len + 2)
        if len(data) < expected_len + 2:
            return (False, None)

        payload = data[:-2]
        crc_recv = (data[-2] << 8) | data[-1]
        crc_calc = self._crc16(payload)

        if crc_calc == crc_recv:
            return (True, payload)
        return (False, None)

    # ---------------------
    # Firmware Version
    # ---------------------
    def ReadVersion(self, address):
        self._write_checksum(address, 21)
        # version string up to 48 bytes
        data = self.port.read(48)
        if len(data) == 0:
            return (False, None)
        return (True, data.rstrip(b'\x00'))

    # ---------------------
    # Simple motor commands
    # ---------------------
    def ForwardM1(self, address, speed):
        self._write_checksum(address, 0, speed)

    def BackwardM1(self, address, speed):
        self._write_checksum(address, 1, speed)

    def SetMinVoltageMainBattery(self, address, voltage):
        self._write_checksum(address, 2, voltage)

    def SetMaxVoltageMainBattery(self, address, voltage):
        self._write_checksum(address, 3, voltage)

    def ForwardM2(self, address, speed):
        self._write_checksum(address, 4, speed)

    def BackwardM2(self, address, speed):
        self._write_checksum(address, 5, speed)

    def ForwardBackwardM1(self, address, speed):
        self._write_checksum(address, 6, speed)

    def ForwardBackwardM2(self, address, speed):
        self._write_checksum(address, 7, speed)

    # ---------------------
    # Read main battery voltage
    # ---------------------
    def ReadMainBatteryVoltage(self, address):
        self._write_checksum(address, 24)
        data = self.port.read(4)
        if len(data) != 4:
            return (False, 0)
        crc_calc = self._crc16(data[:2])
        crc_recv = (data[2] << 8) | data[3]
        if crc_calc == crc_recv:
            value = (data[0] << 8) | data[1]
            return (True, value)
        return (False, 0)

    # ---------------------
    # Read motor currents
    # ---------------------
    def ReadCurrents(self, address):
        self._write_checksum(address, 49)
        data = self.port.read(6)
        if len(data) != 6:
            return (False, 0, 0)
        crc_calc = self._crc16(data[:4])
        crc_recv = (data[4] << 8) | data[5]
        if crc_calc == crc_recv:
            m1 = (data[0] << 8) | data[1]
            m2 = (data[2] << 8) | data[3]
            return (True, m1, m2)
        return (False, 0, 0)
