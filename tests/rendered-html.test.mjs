import assert from "node:assert/strict";
import test from "node:test";

test("renders the FlexiGrid product metadata and first viewport", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  const html = await response.text();
  assert.match(html, /<title>FlexiGrid AI — Evidence-grounded energy planning<\/title>/i);
  assert.match(html, /Plan tomorrow(?:&#x27;|')s flexible energy/i);
  assert.match(html, /Elia snapshot/i);
  assert.doesNotMatch(html, /Starter Project/i);
  assert.match(html, /Planning lab/i);
  assert.match(html, /Plan with headroom/i);
});
