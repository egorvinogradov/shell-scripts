"""Tiny Chrome DevTools Protocol client (stdlib only) so tests can click through the viewer in headless Chrome."""
import base64, json, os, shutil, socket, struct, subprocess, tempfile, time, urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Chrome:
    def __init__(self, port=9341):
        self.udd = tempfile.mkdtemp(prefix="sublog-cdp-")
        self.proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                                      "--user-data-dir=" + self.udd, "--window-size=1300,900", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1))
                url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.1)
        if not url:
            self.close()
            raise RuntimeError("Chrome did not start")
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        path = url.split(str(port), 1)[1]
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(1)
        self.buf, self.n, self.errors = b"", 0, []
        self.call("Runtime.enable")
        self.call("Page.enable")

    def _send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        msg = b""
        while True:
            b1, b2 = self._recv_exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            msg += self._recv_exact(n)
            if b1 & 0x80:
                return json.loads(msg)

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self._send({"id": mid, "method": method, "params": params})
        while True:
            m = self._recv()
            if m.get("method") == "Runtime.exceptionThrown":
                self.errors.append(m["params"]["exceptionDetails"].get("exception", {}).get("description", "exception"))
            elif m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] == "error":
                self.errors.append(str(m["params"]["args"]))
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def wait(self, expr, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.js("!!(" + expr + ")"):
                return True
            time.sleep(0.1)
        raise AssertionError("timed out waiting for: " + expr + " | page text: " + str(self.js("document.body.innerText.slice(0,500)")))

    def goto(self, url):
        self.call("Page.navigate", url="about:blank")                 # a hash-only change would not reload the page
        self.wait("location.href === 'about:blank'")
        self.call("Page.navigate", url=url)
        self.wait("window.SUBLOG_READY === true")

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.udd, ignore_errors=True)
