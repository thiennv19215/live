function childHasExited(child) {
  return !child || child.exitCode !== null || child.signalCode !== null || !child.pid;
}

function waitForChildExit(child, timeoutMs) {
  if (childHasExited(child)) return Promise.resolve(true);

  return new Promise((resolve) => {
    let settled = false;
    let timer;
    const finish = (exited) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.removeListener("exit", onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    child.once("exit", onExit);
    timer = setTimeout(() => finish(childHasExited(child)), timeoutMs);
  });
}

async function stopChildProcess(child, options = {}) {
  const {
    requestShutdown = async () => false,
    forceKill = async (target) => target.kill("SIGKILL"),
    gracefulTimeoutMs = 4500,
    forceTimeoutMs = 2000,
  } = options;

  if (childHasExited(child)) return { exited: true, forced: false };

  try {
    await requestShutdown();
  } catch {
    // The process wait below is authoritative; a failed HTTP request simply
    // advances to the force-kill fallback after the graceful timeout.
  }
  if (await waitForChildExit(child, gracefulTimeoutMs)) {
    return { exited: true, forced: false };
  }

  let forceError = null;
  try {
    await forceKill(child);
  } catch (error) {
    forceError = error;
  }
  const exited = await waitForChildExit(child, forceTimeoutMs);
  return { exited, forced: true, forceError };
}

module.exports = { childHasExited, stopChildProcess, waitForChildExit };
