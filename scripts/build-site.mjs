import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const html = readFileSync(join(root, "public", "index.html"));

rmSync(join(root, "dist"), { recursive: true, force: true });
mkdirSync(join(root, "dist", "server"), { recursive: true });
mkdirSync(join(root, "dist", "client"), { recursive: true });
mkdirSync(join(root, "dist", ".openai"), { recursive: true });
copyFileSync(join(root, "public", "index.html"), join(root, "dist", "client", "index.html"));

const worker = `export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/" && url.pathname !== "/index.html") {
      return Response.redirect(url.origin + "/", 302);
    }
    const assetUrl = new URL("/index.html", request.url);
    return env.ASSETS.fetch(new Request(assetUrl, request));
  }
};
`;

writeFileSync(join(root, "dist", "server", "index.js"), worker);
writeFileSync(join(root, "dist", ".openai", "hosting.json"), readFileSync(join(root, ".openai", "hosting.json")));
console.log(`Built Sites static asset with ${html.length.toLocaleString()} bytes of HTML.`);
