import {defineConfig} from "vitest/config";

export default defineConfig({
  // esbuild handles the automatic JSX runtime, so no React plugin is needed for tests.
  esbuild: {jsx: "automatic"},
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"]
  }
});
