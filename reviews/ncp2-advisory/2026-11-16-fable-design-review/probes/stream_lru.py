"""Probe T1: a subscriber at its stream limit forgets a live stream and accepts it again as joined.

Usage: python3 -I -B stream_lru.py SDK_PYTHON_DIR
"""
import sys

sys.path.insert(0, sys.argv[1])
import ncp  # noqa: E402

CONTRACT = "0" * 64
frames = {}
subscriber = ncp.Subscriber([CONTRACT], max_streams=4)
publishers = [ncp.Publisher(f"cam{i}", CONTRACT, frames.setdefault(i, []).append) for i in range(5)]
for p in publishers:
    p.publish({"n": 1})
for i in range(5):
    print("first message of stream", i, "->", subscriber.receive(frames[i][0]).status)
# Stream 0 was evicted by stream 4. An OLD copy of its first message is accepted again.
print("replayed first message of stream 0 ->", subscriber.receive(frames[0][0]).status)
publishers[0].publish({"n": 2}); publishers[0].publish({"n": 3})
d = subscriber.receive(frames[0][2])
print("message 3 of stream 0 (message 2 lost) ->", d.status, "lost:", d.lost)
# And a stale stream replays into a subscriber without state (spec section 8, last paragraph).
fresh = ncp.Subscriber([CONTRACT])
print("old message 3 into a new subscriber ->", fresh.receive(frames[0][2]).status)
