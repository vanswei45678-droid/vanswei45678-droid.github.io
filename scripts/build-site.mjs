import { gzipSync } from "node:zlib";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const html = readFileSync(join(root, "public", "index.html"));
const compressed = gzipSync(html, { level: 9 }).toString("base64");
const worker = `const HTML_GZIP_BASE64 = ${JSON.stringify(compressed)};

function decodeBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

const htmlGzip = decodeBase64(HTML_GZIP_BASE64);

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname !== "/" && url.pathname !== "/index.html") {
      return Response.redirect(url.origin + "/", 302);
    }
    const htmlStream = new Response(htmlGzip).body.pipeThrough(new DecompressionStream("gzip"));
    return new Response(htmlStream, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=120",
        "x-content-type-options": "nosniff"
      }
    });
  }
};
`;

mkdirSync(join(root, "dist", "server"), { recursive: true });
mkdirSync(join(root, "dist", ".openai"), { recursive: true });
writeFileSync(join(root, "dist", "server", "index.js"), worker);
writeFileSync(join(root, "dist", ".openai", "hosting.json"), readFileSync(join(root, ".openai", "hosting.json")));
console.log(`Built Sites worker with ${html.length.toLocaleString()} bytes of HTML.`);
