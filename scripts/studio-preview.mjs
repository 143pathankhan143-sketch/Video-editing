#!/usr/bin/env node
/**
 * Arena Live Preview launcher for HyperFrames Studio.
 *
 * - Runs `hyperframes preview` internally on 127.0.0.1:13002 so HyperFrames'
 *   loopback host/origin guard is satisfied.
 * - Exposes a public reverse proxy on 0.0.0.0:3002 (HTTP + WebSocket/HMR + Range video streaming)
 *   that cleanly serves inside Arena's iframe live preview without X-Frame-Options/Host 403 blocks.
 */
import http from "node:http";
import net from "node:net";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, "..");
const PROJECT_DIR = path.resolve(ROOT_DIR, process.argv[2] || "hyperframes-property");

const PUBLIC_PORT = Number(process.env.PORT || 3002);
const INTERNAL_PORT = Number(process.env.HF_INTERNAL_PORT || 13002);
const BROWSER_PATH = process.env.HYPERFRAMES_BROWSER_PATH || "/opt/hyperframes-deps/bin/chrome-headless-shell";

const hfBin = path.resolve(ROOT_DIR, "node_modules/.bin/hyperframes");
const child = spawn(
  hfBin,
  ["preview", PROJECT_DIR, "--port", String(INTERNAL_PORT), "--foreground", "--no-open"],
  {
    cwd: ROOT_DIR,
    stdio: "inherit",
    env: {
      ...process.env,
      HYPERFRAMES_BROWSER_PATH: BROWSER_PATH,
      HYPERFRAMES_PREVIEW_HOST: "127.0.0.1",
    },
  }
);

child.on("exit", (code) => {
  process.exit(code ?? 0);
});

function rewriteHeaders(headers) {
  const out = { ...headers };
  delete out["x-frame-options"];
  delete out["content-security-policy"];
  return out;
}

const server = http.createServer((req, res) => {
  const proxyHeaders = {
    ...req.headers,
    host: `127.0.0.1:${INTERNAL_PORT}`,
    origin: `http://127.0.0.1:${INTERNAL_PORT}`,
    referer: `http://127.0.0.1:${INTERNAL_PORT}/`,
  };

  const upstream = http.request(
    {
      hostname: "127.0.0.1",
      port: INTERNAL_PORT,
      path: req.url,
      method: req.method,
      headers: proxyHeaders,
    },
    (upRes) => {
      res.writeHead(upRes.statusCode || 502, rewriteHeaders(upRes.headers));
      upRes.pipe(res);
    }
  );

  upstream.on("error", (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
    }
    res.end(`HyperFrames Studio starting up... (${err.message})`);
  });

  req.pipe(upstream);
});

// Forward WebSocket upgrades (used by Studio live reload & timeline sync)
server.on("upgrade", (req, clientSocket, head) => {
  const upstreamSocket = net.connect(INTERNAL_PORT, "127.0.0.1", () => {
    const lines = [`${req.method} ${req.url} HTTP/${req.httpVersion}`];
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const k = req.rawHeaders[i];
      const v = req.rawHeaders[i + 1];
      const lower = k.toLowerCase();
      if (lower === "host") {
        lines.push(`Host: 127.0.0.1:${INTERNAL_PORT}`);
      } else if (lower === "origin") {
        lines.push(`Origin: http://127.0.0.1:${INTERNAL_PORT}`);
      } else {
        lines.push(`${k}: ${v}`);
      }
    }
    lines.push("", "");
    upstreamSocket.write(lines.join("\r\n"));
    if (head && head.length) upstreamSocket.write(head);
    clientSocket.pipe(upstreamSocket).pipe(clientSocket);
  });

  upstreamSocket.on("error", () => clientSocket.destroy());
  clientSocket.on("error", () => upstreamSocket.destroy());
});

server.listen(PUBLIC_PORT, "0.0.0.0", () => {
  console.log(`[HyperFrames Preview Proxy] Listening on http://0.0.0.0:${PUBLIC_PORT} -> http://127.0.0.1:${INTERNAL_PORT}`);
});

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => {
    child.kill(sig);
    server.close(() => process.exit(0));
  });
}
