"""Minimal Wwise Authoring API client over HTTP (no third-party packages needed).

WwiseConsole's `waapi-server` mode runs Wwise headless and accepts WAAPI calls as
JSON over HTTP POST, so we never have to open the Wwise GUI.
"""
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request


class WaapiError(RuntimeError):
    pass


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class WaapiServer:
    """Starts `WwiseConsole waapi-server <project>` and talks to it.

    Use as a context manager so the server is always shut down.
    """

    def __init__(self, wwise_console, project, log_path=None):
        self.wwise_console = wwise_console
        self.project = project
        self.log_path = log_path
        self.port = _free_port()
        self.proc = None
        self._log = None

    def __enter__(self):
        self._log = open(self.log_path, "w", encoding="utf-8") if self.log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [self.wwise_console, "waapi-server", self.project, "--allow-migration",
             "--http-port", str(self.port), "--wamp-port", str(_free_port())],
            stdout=self._log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.time() + 180
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise WaapiError(f"WwiseConsole exited early (code {self.proc.returncode}). See {self.log_path}")
            try:
                self.call("ak.wwise.core.getInfo", timeout=5)
                return self
            except (urllib.error.URLError, ConnectionError, socket.timeout, OSError):
                time.sleep(1)
        raise WaapiError("Timed out waiting for the Wwise scripting server to start.")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self._log not in (None, subprocess.DEVNULL):
            self._log.close()

    def call(self, uri, args=None, options=None, timeout=600):
        body = json.dumps({"uri": uri, "args": args or {}, "options": options or {}}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/waapi", body,
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise WaapiError(f"{uri} failed: {detail}") from None

    # --- convenience helpers -------------------------------------------------

    def create(self, parent, type_, name, on_conflict="merge", **extra):
        args = {"parent": parent, "type": type_, "name": name, "onNameConflict": on_conflict}
        args.update(extra)
        return self.call("ak.wwise.core.object.create", args)

    def get(self, path_or_id, fields=("id", "name", "type", "path")):
        res = self.call("ak.wwise.core.object.get",
                        {"from": {"path" if path_or_id.startswith("\\") else "id": [path_or_id]}},
                        {"return": list(fields)})
        objs = res.get("return", [])
        return objs[0] if objs else None

    def children(self, path_or_id, fields=("id", "name", "type", "path")):
        key = "path" if path_or_id.startswith("\\") else "id"
        res = self.call("ak.wwise.core.object.get",
                        {"from": {key: [path_or_id]}, "transform": [{"select": ["children"]}]},
                        {"return": list(fields)})
        return res.get("return", [])

    def set_property(self, obj, prop, value, platform=None):
        args = {"object": obj, "property": prop, "value": value}
        if platform:
            args["platform"] = platform
        return self.call("ak.wwise.core.object.setProperty", args)

    def set_reference(self, obj, ref, value):
        return self.call("ak.wwise.core.object.setReference", {"object": obj, "reference": ref, "value": value})

    def delete(self, obj):
        return self.call("ak.wwise.core.object.delete", {"object": obj})


def find_wwise_console(configured=None):
    candidates = []
    if configured:
        candidates.append(configured)
    root = os.environ.get("WWISEROOT")
    if root:
        candidates.append(os.path.join(root, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe"))
    for base in (r"C:\Audiokinetic", r"C:\Program Files (x86)\Audiokinetic", r"C:\Program Files\Audiokinetic"):
        if os.path.isdir(base):
            for d in sorted(os.listdir(base), reverse=True):
                if d.startswith("Wwise2021.1"):
                    candidates.append(os.path.join(base, d, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None
