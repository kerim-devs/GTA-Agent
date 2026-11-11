import sys
import time
from threading import Barrier, Thread
from types import ModuleType

from pilot import apple


class Lazy(ModuleType):
    """A framework the way PyObjC serves it: the first lookup of a name is not safe between threads."""

    def __init__(self, name, names):
        super().__init__(name)
        self.__dict__["pending"] = dict.fromkeys(names, object())

    def __getattr__(self, name):
        if name not in self.pending:
            raise AttributeError(name)
        time.sleep(0.02)
        value = self.pending.pop(name)
        self.__dict__[name] = value
        return value


def test_two_readers_can_ask_for_the_frameworks_in_the_same_moment(monkeypatch):
    for name, names in apple.NAMES.items():
        monkeypatch.setitem(sys.modules, name, Lazy(name, names))
    monkeypatch.setitem(sys.modules, "objc", ModuleType("objc"))
    barrier, errors = Barrier(2), []

    def reader():
        barrier.wait()
        try:
            _, _, quartz, _ = apple.frameworks()
            assert quartz.CGDataProviderCreateWithCFData is not None
        except Exception as error:
            errors.append(error)

    threads = [Thread(target=reader) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert all(not sys.modules[name].pending for name in apple.NAMES)
