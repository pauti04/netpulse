"""Live monitoring: a 24/7 RIS Live tap that detects BGP anomalies in real time.

`DetectionFeed` is the thread-safe handoff between the monitor thread
(producer) and the web handlers (consumers), so the whole live product
runs in a single process with no cross-process store locking.
"""
