import { access, readFile, writeFile } from "node:fs/promises";

const source = new URL("../../../contracts/examples/feature-2/", import.meta.url);
const output = new URL("../src/lib/api/capacity-fixtures.generated.json", import.meta.url);
try {
  await access(source);
} catch {
  await access(output);
  console.log("Using bundled synthetic capacity examples (shared contracts are outside this image).");
  process.exit(0);
}
const read = async (name) => JSON.parse(await readFile(new URL(name, source), "utf8"));
const responses = Object.fromEntries(await Promise.all(["DEMO-A", "DEMO-B", "DEMO-C"].map(async (id) =>
  [id, await read(`${id}.capacity.response.json`)],
)));
// Additional display fixtures cover states absent from the shared examples.
// These are test data, not API schemas or calculated observations.
const notConfigured = structuredClone(responses["DEMO-B"]);
notConfigured.services[0] = {
  ...notConfigured.services[0], profile_version: null, status: "not_configured",
  estimated_capacity: null, bottleneck_resource_ids: [], resource_limits: [],
  reason_codes: ["requirements_not_configured"],
};
const noServices = { ...structuredClone(responses["DEMO-B"]), services: [] };
await writeFile(output, `${JSON.stringify({ responses, stateExamples: { notConfigured, noServices } }, null, 2)}\n`);
console.log("Bundled the shared synthetic capacity examples and frontend state previews.");
