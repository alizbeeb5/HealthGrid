import { access, readFile, writeFile } from "node:fs/promises";
const source = new URL("../../../contracts/examples/feature-4/", import.meta.url);
const output = new URL("../src/lib/api/forecast-fixtures.generated.json", import.meta.url);
try {
  await access(source);
} catch {
  // Development containers use the committed bundle when contracts are absent.
  await access(output);
  console.log("Using bundled synthetic forecast fixtures.");
  process.exit(0);
}
const examples = await Promise.all(["DEMO-B.forecast.response.json", "insufficient-history.forecast.response.json"].map(async (name) => JSON.parse(await readFile(new URL(name, source), "utf8"))));
await writeFile(output, `${JSON.stringify(examples, null, 2)}\n`);
