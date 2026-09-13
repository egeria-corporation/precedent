import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // The parity fixture is 3.8 MB of real award records; loading it is the slow part and
    // it is the whole point of the test.
    testTimeout: 30_000,
  },
});
