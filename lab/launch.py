"""Linux subprocess wrapper: kill the engine if the arena coordinator dies."""
import ctypes
import os
import signal
import sys

parent = int(sys.argv[1])
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
    raise OSError(ctypes.get_errno(), 'prctl(PR_SET_PDEATHSIG) failed')
if os.getppid() != parent:
    raise SystemExit('Arena coordinator exited during launch')
os.execv(sys.argv[2], sys.argv[2:])
