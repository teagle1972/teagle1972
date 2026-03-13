import os
import sys


base_dir = getattr(sys, "_MEIPASS", "")
if base_dir:
    os.environ["TCL_LIBRARY"] = os.path.join(base_dir, "_tcl_data")
    os.environ["TK_LIBRARY"] = os.path.join(base_dir, "_tk_data")
