import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    """Scripts read/write config.ini, session.log, *.json in the cwd."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def process_calls(monkeypatch):
    """Never let a test kill the real Steam. Records every subprocess.run call."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 128, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls
