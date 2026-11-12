"""Apple's frameworks for the text readers, with their names looked up by one thread at a time."""

from threading import Lock

# PyObjC looks a framework's function up when it is first asked for, and that lookup is not safe
# between threads: two readers asking for the same function in the same moment leave one of them
# with a KeyError. Live on 11 November the scene reader and the GPS reader did exactly that on the
# first tick, and the session ended there.
NAMES = {
    "Foundation": ("NSData",),
    "Quartz": ("CGDataProviderCreateWithCFData", "CGImageCreate", "CGColorSpaceCreateDeviceRGB"),
    "Vision": (
        "VNRecognizeTextRequest",
        "VNImageRequestHandler",
        "VNRequestTextRecognitionLevelFast",
        "VNRequestTextRecognitionLevelAccurate",
    ),
}
_lock = Lock()


def frameworks():
    """Foundation, objc, Quartz and Vision, every name the readers call already looked up."""
    with _lock:
        import Foundation
        import objc
        import Quartz
        import Vision

        for module in (Foundation, Quartz, Vision):
            for name in NAMES[module.__name__]:
                getattr(module, name)
    return Foundation, objc, Quartz, Vision
