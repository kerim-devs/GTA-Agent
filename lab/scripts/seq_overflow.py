"""Does a feedback packet survive a sequence number past 16 bits? No daemon, no network."""
from ps5_remoteplay_mcp.vendor.pyremoteplay.const import TYPE_PS5
from ps5_remoteplay_mcp.vendor.pyremoteplay.stream_packets import (
    ControllerState,
    FeedbackHeader,
    FeedbackPacket,
)

for seq in (65535, 65536):
    for kind, kwargs in (
        (FeedbackHeader.Type.STATE, {"state": ControllerState()}),
        (FeedbackHeader.Type.EVENT, {"data": b"\x80\x87\x99"}),
    ):
        try:
            out = FeedbackPacket(kind, sequence=seq, host_type=TYPE_PS5, **kwargs).bytes()
            print(seq, kind.name, "ok", len(out))
        except Exception as err:
            print(seq, kind.name, "FAILED", type(err).__name__, err)
