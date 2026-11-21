"""The Docker log watch demo: the Target Project running as a small service that works through a job list.

`make crash` runs it as container "calculator". Each job prints a line, so the dashboard shows the log live.
The last job calls Calculator.power, which target/calculator/core.py does not have: the service crashes with
an AttributeError traceback, the watch sees it, and the Patch Loop adds the method. Run `make crash` again
afterwards: every job passes and the service ends with "all jobs done".
"""
import time

from calculator.core import Calculator

JOBS = [("add", 2, 3), ("multiply", 6, 7), ("divide", 10, 4), ("subtract", 9, 12), ("power", 2, 8)]

calculator = Calculator()
print("calculator service started", flush=True)
for name, a, b in JOBS:
    time.sleep(1.5)  # slow enough to watch the log arrive on the dashboard
    print(f"job {name}({a}, {b}) = {getattr(calculator, name)(a, b)}", flush=True)
print("all jobs done", flush=True)
