# Copyright 2026 OEDO Dynamics Inc.
# Licensed under the Apache License, Version 2.0

"""Make the package importable when pytest runs from a source checkout."""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
