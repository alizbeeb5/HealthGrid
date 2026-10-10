import { readFile, writeFile } from "node:fs/promises";
const source = new URL("../../../contracts/examples/feature-4/", import.meta.url);
const examples = await Promise.all(["DEMO-B.forecast.response.json", "insufficient-history.forecast.response.json"].map(async (name) => JSON.parse(await readFile(new URL(name, source), "utf8"))));
await writeFile(new URL("../src/lib/api/forecast-fixtures.generated.json", import.meta.url), `${JSON.stringify(examples, null, 2)}\n`);
