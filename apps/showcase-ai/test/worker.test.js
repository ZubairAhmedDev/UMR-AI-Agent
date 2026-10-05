import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import worker from "../worker/index.js";

const facts = JSON.parse(readFileSync(new URL("../public/data/runs.json", import.meta.url)));
const observations = [];
const env = {
  CHAT_TOTAL: { limit: async () => ({ success: true }) },
  CHAT_VISITOR: { limit: async () => ({ success: true }) },
  ASSETS: { fetch: async (request) => {
    const pathname = new URL(request.url).pathname;
    assert.equal(pathname, "/data/runs.json");
    return Response.json(facts);
  } },
  AI: { run: async (model, input) => {
    observations.push({ model, input });
    return { response: "The left knee needs review at frame 12; contact was not measured." };
  } }
};

function ask(data, headers = { "content-type": "application/json" }) {
  return worker.fetch(new Request("https://example.com/api/chat", {
    method: "POST", headers, body: JSON.stringify(data)
  }), env);
}

test("explains a chosen verified run with no execution capability", async () => {
  const response = await ask({ motionId: "run", question: "Which frames need review?" });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.motionId, "run");
  assert.equal(body.resultSha256, facts.runs[1].result_sha256);
  assert.match(observations.at(-1).input.messages[1].content, /left_knee_joint: frames 12/);
  assert.doesNotMatch(observations.at(-1).input.messages[1].content, /right_elbow_joint/);
});

test("rejects extra fields, unknown motions and oversized questions", async () => {
  const before = observations.length;
  for (const data of [
    { motionId: "run", question: "What happened?", command: "execute" },
    { motionId: "../secret", question: "What happened?" },
    { motionId: "run", question: "x".repeat(401) }
  ]) assert.equal((await ask(data)).status, 400);
  assert.equal(observations.length, before);
});

test("fails closed if AI binding is absent", async () => {
  const response = await worker.fetch(new Request("https://example.com/api/chat", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ motionId: "run", question: "Where are warnings?" })
  }), { ASSETS: env.ASSETS });
  assert.equal(response.status, 503);
});

test("limits public requests before model invocation", async () => {
  const before = observations.length;
  const response = await worker.fetch(new Request("https://example.com/api/chat", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ motionId: "run", question: "Where are warnings?" })
  }), { ...env, CHAT_TOTAL: { limit: async () => ({ success: false }) } });
  assert.equal(response.status, 429);
  assert.equal(observations.length, before);
});
