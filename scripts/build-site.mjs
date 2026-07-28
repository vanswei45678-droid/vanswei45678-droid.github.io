import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });
await mkdir("dist/client", { recursive: true });
await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });

await cp("public", "dist/client", { recursive: true });
await cp(".openai/hosting.json", "dist/.openai/hosting.json");

const html = await readFile("public/index.html");
const gzipBase64 = gzipSync(html, { level: 9 }).toString("base64");

await writeFile(
  "dist/server/index.js",
  `const HTML_GZIP_BASE64 = ${JSON.stringify(gzipBase64)};

function decodeBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

const HTML_BYTES = decodeBase64(HTML_GZIP_BASE64);
const HTML_HEADERS = {
  "Content-Type": "text/html; charset=utf-8",
  "Content-Encoding": "gzip",
  "Cache-Control": "public, max-age=60",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({ ok: true });
    }

    if (url.pathname === "/" || url.pathname === "/index.html") {
      return new Response(request.method === "HEAD" ? null : HTML_BYTES, {
        headers: HTML_HEADERS,
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
`,
  "utf8",
);
