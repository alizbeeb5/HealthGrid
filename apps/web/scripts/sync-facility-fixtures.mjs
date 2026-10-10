import { access, readFile, writeFile } from "node:fs/promises";

const source = new URL("../../../contracts/examples/feature-1/", import.meta.url);
const output = new URL("../src/lib/api/facilities-fixtures.generated.json", import.meta.url);
try {
  await access(source);
} catch {
  // The development Docker image copies only apps/web, including the generated bundle.
  await access(output);
  console.log("Using bundled synthetic hospital fixtures (shared contracts are outside this image).");
  process.exit(0);
}
const read = async (name) => JSON.parse(await readFile(new URL(name, source), "utf8"));
const list = await read("facilities.response.json");
const snapshots = Object.fromEntries(await Promise.all(list.items.map(async ({ facility_id }) =>
  [facility_id, await read(`${facility_id}.snapshot.response.json`)],
)));
await writeFile(output, `${JSON.stringify({ list, snapshots }, null, 2)}\n`);
console.log("Bundled the shared synthetic hospital examples.");
