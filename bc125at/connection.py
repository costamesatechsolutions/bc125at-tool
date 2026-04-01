"""
BC125AT USB Communication Layer

Handles direct USB communication with the BC125AT scanner via libusb,
bypassing the need for a kernel serial driver (which doesn't work on Apple Silicon).
"""

import usb.core
import usb.util
import time
import sys
import threading

UNIDEN_VENDOR_ID = 0x1965
BC125AT_PRODUCT_ID = 0x0017

# CDC ACM endpoints (confirmed from device enumeration)
DATA_INTERFACE = 1
EP_IN = 0x81
EP_OUT = 0x02


class ScannerConnection:
    """Direct USB connection to BC125AT scanner."""

    def __init__(self, timeout=2000):
        self.dev = None
        self.ep_in = None
        self.ep_out = None
        self.timeout = timeout
        self.in_program_mode = False
        self.claimed_interfaces = []
        self.command_lock = threading.Lock()

    def connect(self):
        """Find and connect to the BC125AT."""
        self.dev = usb.core.find(idVendor=UNIDEN_VENDOR_ID, idProduct=BC125AT_PRODUCT_ID)
        if self.dev is None:
            raise ConnectionError(
                "BC125AT not found. Make sure it's powered on and connected via USB."
            )

        # Detach kernel drivers if attached
        for iface in [0, 1]:
            try:
                if self.dev.is_kernel_driver_active(iface):
                    self.dev.detach_kernel_driver(iface)
            except (usb.core.USBError, NotImplementedError):
                pass

        self.dev.set_configuration()
        self.claimed_interfaces = []
        cfg = self.dev.get_active_configuration()
        data_iface = cfg[(DATA_INTERFACE, 0)]

        for iface in [0, DATA_INTERFACE]:
            try:
                usb.util.claim_interface(self.dev, iface)
                self.claimed_interfaces.append(iface)
            except usb.core.USBError:
                pass

        for ep in data_iface:
            if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT:
                self.ep_out = ep
            elif usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
                self.ep_in = ep

        if not self.ep_in or not self.ep_out:
            raise ConnectionError("Could not find USB bulk endpoints on BC125AT.")

        # Flush any stale data in the read buffer
        for _ in range(5):
            try:
                self.ep_in.read(512, timeout=100)
            except usb.core.USBError:
                break

        # Verify we're talking to the right device (retry a couple times)
        for attempt in range(3):
            resp = self.send_command("MDL")
            if resp and "BC125AT" in resp:
                break
            # Flush and retry
            try:
                self.ep_in.read(512, timeout=100)
            except usb.core.USBError:
                pass
        else:
            raise ConnectionError(f"Unexpected device response: {resp}")

        return self

    def disconnect(self):
        """Clean up and release the device."""
        if self.in_program_mode:
            try:
                self.exit_program_mode()
            except Exception:
                pass
        if self.dev:
            for iface in reversed(self.claimed_interfaces):
                try:
                    usb.util.release_interface(self.dev, iface)
                except usb.core.USBError:
                    pass
            self.claimed_interfaces = []
            usb.util.dispose_resources(self.dev)
            self.dev = None

    def _flush_input(self):
        """Flush any stale data from the input buffer."""
        for _ in range(5):
            try:
                self.ep_in.read(512, timeout=50)
            except usb.core.USBError:
                break

    def send_command(self, command, timeout=None):
        """Send a command and return the response string.

        The scanner may have buffered display data from active scanning,
        so we read multiple chunks until we find one that starts with our
        expected command prefix (e.g. "MDL," for "MDL" command).

        In program mode, the scanner stops scanning so responses are clean.
        """
        if not self.dev:
            raise ConnectionError("Not connected to scanner.")

        timeout = timeout or self.timeout
        cmd_bytes = (command + "\r").encode("ascii")

        with self.command_lock:
            # Only flush when NOT in program mode (scanning generates display data)
            if not self.in_program_mode:
                self._flush_input()

            try:
                self.ep_out.write(cmd_bytes, timeout=timeout)
            except usb.core.USBError as e:
                raise ConnectionError(f"USB write error: {e}")

            # The expected response starts with the command name
            cmd_prefix = command.split(",")[0]

            # Accumulate data until we have a complete \r-terminated response
            # that starts with our command prefix.
            accumulated = ""
            deadline = time.time() + (timeout / 1000.0)

            while time.time() < deadline:
                try:
                    raw = self.ep_in.read(512, timeout=min(500, timeout))
                    accumulated += bytes(raw).decode("ascii", errors="replace")
                except usb.core.USBError as e:
                    if "timeout" in str(e).lower():
                        if cmd_prefix in accumulated:
                            break
                        continue
                    raise ConnectionError(f"USB read error: {e}")

                if cmd_prefix in accumulated and "\r" in accumulated:
                    break

            for line in accumulated.split("\r"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith(cmd_prefix + ",") or line == cmd_prefix:
                    return line
                if line == "ERR":
                    return line

            if cmd_prefix in accumulated:
                idx = accumulated.find(cmd_prefix)
                end = accumulated.find("\r", idx)
                if end == -1:
                    return accumulated[idx:].strip()
                return accumulated[idx:end].strip()

            return accumulated.strip() if accumulated.strip() else None

    def enter_program_mode(self):
        """Enter program mode (required for most read/write operations)."""
        if self.in_program_mode:
            return True
        resp = self.send_command("PRG")
        if resp == "PRG,OK":
            self.in_program_mode = True
            return True
        raise ConnectionError(
            f"Could not enter program mode: {resp}. "
            "Make sure scanner is not in Menu Mode, Direct Entry, or Quick Save."
        )

    def exit_program_mode(self):
        """Exit program mode (scanner goes to Scan Hold)."""
        if not self.in_program_mode:
            return True
        resp = self.send_command("EPG")
        if resp == "EPG,OK":
            self.in_program_mode = False
            return True
        raise ConnectionError(f"Could not exit program mode: {resp}")

    def get_model(self):
        """Get scanner model (does not require program mode)."""
        return self.send_command("MDL")

    def get_version(self):
        """Get firmware version (does not require program mode)."""
        return self.send_command("VER")

    def get_status(self):
        """Get current scanner status (does not require program mode)."""
        return self.send_command("STS")

    def get_live_info(self):
        """Get current reception info (does not require program mode)."""
        return self.send_command("GLG")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
