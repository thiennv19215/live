const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { stopChildProcess, waitForChildExit } = require("../backend-process");

class FakeChild extends EventEmitter {
  constructor(pid = 1234) {
    super();
    this.pid = pid;
    this.exitCode = null;
    this.signalCode = null;
    this.killCalls = 0;
  }

  exit(code = 0, signal = null) {
    this.exitCode = code;
    this.signalCode = signal;
    this.emit("exit", code, signal);
  }

  kill() {
    this.killCalls += 1;
    this.exit(null, "SIGKILL");
    return true;
  }
}

test("waitForChildExit resolves after the process exits", async () => {
  const child = new FakeChild();
  setImmediate(() => child.exit(0));
  assert.equal(await waitForChildExit(child, 100), true);
});

test("stopChildProcess prefers graceful backend shutdown", async () => {
  const child = new FakeChild();
  const result = await stopChildProcess(child, {
    requestShutdown: async () => child.exit(0),
    gracefulTimeoutMs: 20,
    forceTimeoutMs: 20,
  });
  assert.deepEqual(result, { exited: true, forced: false });
  assert.equal(child.killCalls, 0);
});

test("stopChildProcess force-kills a backend that misses its deadline", async () => {
  const child = new FakeChild();
  let forcedPid = 0;
  const result = await stopChildProcess(child, {
    requestShutdown: async () => false,
    forceKill: async (target) => {
      forcedPid = target.pid;
      target.kill();
    },
    gracefulTimeoutMs: 5,
    forceTimeoutMs: 20,
  });
  assert.equal(forcedPid, 1234);
  assert.equal(result.exited, true);
  assert.equal(result.forced, true);
});
