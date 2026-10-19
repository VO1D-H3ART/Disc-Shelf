"""Read the kernel's mounted-filesystem list. No daemon, network, or writes."""
from pathlib import Path


def mounted_optical_discs() -> list[str]:
    """Return mountpoints of mounted /dev/sr* optical discs on Linux.

    Mounting itself is left to the desktop/OS for this first milestone.
    """
    mounts = Path('/proc/mounts')
    if not mounts.is_file():
        return []
    found = []
    try:
        for line in mounts.read_text(encoding='utf-8', errors='replace').splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue
            device, mountpoint, filesystem = fields[:3]
            # Include generic optical-drive aliases if mounted directly.
            if filesystem not in {'iso9660', 'udf'}:
                continue
            if not (device.startswith('/dev/sr') or device in {'/dev/cdrom', '/dev/dvd'}):
                continue
            # /proc/mounts encodes spaces as octal sequences.
            path = mountpoint.replace('\\040', ' ').replace('\\011', '\t')
            if Path(path).is_dir():
                found.append(path)
    except OSError:
        return []
    return sorted(set(found))
