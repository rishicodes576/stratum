import { cp, access } from "node:fs/promises";
import { spawn } from "node:child_process";

await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
try {
  await access("public");
  await cp("public", ".next/standalone/public", { recursive: true });
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
const server = spawn(process.execPath, [".next/standalone/server.js"], {
  stdio: "inherit",
  env: { ...process.env, HOSTNAME: process.env.HOSTNAME || "127.0.0.1" },
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code || 0));
