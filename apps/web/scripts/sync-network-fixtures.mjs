import { access, readFile, writeFile } from "node:fs/promises";

const source = new URL("../../../contracts/examples/feature-3/", import.meta.url);
const output = new URL("../src/lib/api/network-fixtures.generated.json", import.meta.url);
try {
  await access(source);
} catch {
  await access(output);
  console.log("Using bundled synthetic network examples.");
  process.exit(0);
}
const read = async (name) => JSON.parse(await readFile(new URL(name, source), "utf8"));
const [services, overview, unknownService] = await Promise.all([
  read("services.response.json"), read("emergency-care.overview.response.json"),
  read("unknown-service.overview.response.json"),
]);
await writeFile(output, `${JSON.stringify({ services, overview, unknownService }, null, 2)}\n`);
console.log("Bundled the shared synthetic network examples.");
