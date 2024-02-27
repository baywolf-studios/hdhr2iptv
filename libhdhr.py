import logging
import os
from ctypes import *
from ctypes.util import find_library
import ipaddress

MAX_DEVICES = 16
HDHOMERUN_DEVICE_TYPE_TUNER = 0x00000001
HDHOMERUN_DEVICE_ID_WILDCARD = 0xFFFFFFFF


class TYPE_hdhomerun_discover_device_v3_t(Structure):
    _fields_ = [
        ("ip_addr", c_uint, 32),
        ("device_type", c_uint, 32),
        ("device_id", c_uint, 32),
        ("tuner_count", c_ubyte),
        ("is_legacy", c_bool),
        ("device_auth", c_char * 25),
        ("base_url", c_char * 29),
        ("storage_id", c_char * 37),
        ("lineup_url", c_char * 128),
        ("storage_url", c_char * 128),
    ]

    def to_hdhr_device(self):
        return {
            "IPAddress": str(ipaddress.ip_address(self.ip_addr)),
            "DeviceType": ("%X" % self.device_type),
            "DeviceID": ("%X" % self.device_id),
            "TunerCount": self.tuner_count,
            "IsLegacy": self.is_legacy,
            "DeviceAuth": self.device_auth.decode("utf-8"),
            "BaseURL": self.base_url.decode("utf-8"),
            "storage_id": self.storage_id.decode("utf-8"),
            "LineupURL": self.lineup_url.decode("utf-8"),
            "storage_url": self.storage_url.decode("utf-8"),
        }


def get_hdhr_devices():
    libhdhomerun_library = find_library("hdhomerun") or os.path.join(
        os.path.curdir, "libhdhomerun.so"
    )
    logging.info("libhdhomerun: Found library: %s" % libhdhomerun_library)

    libhdhomerun = cdll.LoadLibrary(libhdhomerun_library)

    CFUNC_hdhomerun_discover_find_devices_custom_v3 = (
        libhdhomerun.hdhomerun_discover_find_devices_custom_v3
    )
    CFUNC_hdhomerun_discover_find_devices_custom_v3.argtypes = [
        c_uint,
        c_uint,
        c_uint,
        TYPE_hdhomerun_discover_device_v3_t * MAX_DEVICES,
        c_int,
    ]

    devices = (TYPE_hdhomerun_discover_device_v3_t * MAX_DEVICES)()

    try:
        num_found = CFUNC_hdhomerun_discover_find_devices_custom_v3(
            0,
            HDHOMERUN_DEVICE_TYPE_TUNER,
            HDHOMERUN_DEVICE_ID_WILDCARD,
            devices,
            MAX_DEVICES,
        )
    except:
        logging.exception("libhdhomerun: Call to discover devices failed.")
        raise

    if num_found == -1:
        logging.warning("libhdhomerun: No HdHomeRun devices detected")
        return []

    logging.info("libhdhomerun: (%d) devices found." % (num_found))

    return (device.to_hdhr_device() for device in devices[0:num_found])
