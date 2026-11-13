"""Exercise the watcher with local command doubles, never with the bridge or recordings."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


WATCHER = Path(__file__).with_name("record-kerim.sh")
HUMAN = "/Users/kerim/recordings/kerim/20261113-190000"
PILOT = "/Users/kerim/recordings/pilot/20261113-190001"


def recording(directory=None):
    return {"recording": directory is not None, "dir": directory}


MOCK = """#!/usr/bin/env python3
import json, os, pathlib, sys
path = pathlib.Path(os.environ['TEST_ROOT']) / 'state.json'
state = json.loads(path.read_text())
name = pathlib.Path(sys.argv[0]).name
if name == 'curl':
    key = 'records' if sys.argv[-1].endswith('/record') else 'statuses'
    reply = state[key].pop(0)
else:
    action = sys.argv[2]
    state['actions'].append(action)
    reply = state['starts'].pop(0) if action == 'start' else {'ok': True}
path.write_text(json.dumps(state))
if reply is None:
    sys.exit(22)
print(reply if isinstance(reply, str) else json.dumps(reply))
"""


class RecordingOwnerTests(unittest.TestCase):
    def run_watch(self, records, *, humans=(False,), starts=(), quiet=1, cut=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "remoteplay/.venv/bin").mkdir(parents=True)
            for command in (root / "curl", root / "remoteplay/.venv/bin/ps5rp"):
                command.write_text(MOCK)
                command.chmod(0o755)
            state_file = root / "state.json"
            state_file.write_text(json.dumps({
                "records": records,
                "statuses": [{"human_input": value} for value in humans],
                "starts": list(starts),
                "actions": [],
            }))
            env = dict(os.environ, TEST_ROOT=folder, PATH=f"{folder}:{os.environ['PATH']}")
            # The watcher changes directory and asks for free space. Both stay inside these doubles.
            wrapper = '''
cd() { builtin cd "$TEST_ROOT"; }
df() { print 'Filesystem Size Used Avail'; print 'mock 100 1 99'; }
sleep() {
  (( test_left -= 1 ))
  (( test_left > 0 )) || exit 0
  if [[ "$test_cut" == yes ]]; then SECONDS=1300; fi
}
test_left=$1; test_cut=$2
source "$3" "$4"
'''
            result = subprocess.run(
                ["zsh", "-c", wrapper, "watch-test", str(len(humans)),
                 "yes" if cut else "no", str(WATCHER), str(quiet)],
                env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            return json.loads(state_file.read_text())["actions"], result.stdout

    def test_pilot_replaces_owned_recording_between_polls(self):
        actions, _ = self.run_watch([recording(HUMAN), recording(PILOT)])
        self.assertEqual(actions, [])

    def test_another_human_directory_is_not_the_owned_session(self):
        actions, _ = self.run_watch([recording(HUMAN), recording(HUMAN + "-other")])
        self.assertEqual(actions, [])

    def test_invalid_status_retains_owner_for_next_valid_poll(self):
        actions, _ = self.run_watch(
            [recording(HUMAN), "", recording(HUMAN), recording(HUMAN)],
            humans=(False, False),
        )
        self.assertEqual(actions, ["stop"])

    def test_recheck_before_stop_detects_replacement(self):
        actions, _ = self.run_watch(
            [recording(HUMAN), recording(HUMAN), recording(PILOT)],
        )
        self.assertEqual(actions, [])

    def test_failed_record_request_retains_owner_without_stopping(self):
        actions, _ = self.run_watch(
            [recording(HUMAN), None, recording(HUMAN), recording(HUMAN)],
            humans=(False, False),
        )
        self.assertEqual(actions, ["stop"])

    def test_invalid_human_status_does_not_stop_or_forget_recording(self):
        actions, _ = self.run_watch(
            [recording(HUMAN), recording(HUMAN), recording(HUMAN)],
            humans=(None, False),
        )
        self.assertEqual(actions, ["stop"])

    def test_already_stopped_recording_is_not_stopped_again(self):
        actions, _ = self.run_watch([recording(HUMAN), recording()])
        self.assertEqual(actions, [])

    def test_new_recording_owns_the_start_response_directory(self):
        actions, _ = self.run_watch(
            [recording(), recording(), recording(PILOT)],
            humans=(True, False), starts=(recording(HUMAN),),
        )
        self.assertEqual(actions, ["start"])

    def test_existing_pilot_recording_is_not_adopted(self):
        actions, _ = self.run_watch([recording(PILOT), recording(PILOT)], humans=(True,))
        self.assertEqual(actions, [])

    def test_twenty_minute_cut_still_stops_and_starts_owned_recording(self):
        actions, _ = self.run_watch(
            [recording(HUMAN)] * 4, humans=(True, True),
            starts=(recording(HUMAN + "-next"),), quiet=600, cut=True,
        )
        self.assertEqual(actions, ["stop", "start"])


if __name__ == "__main__":
    unittest.main()
