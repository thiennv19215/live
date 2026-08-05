const PRESETS = Object.freeze({
  "9:16": [1080, 1920],
  "16:9": [1920, 1080],
  "1:1": [1080, 1080],
  "4:5": [1080, 1350],
});

function readOption(argv, name, fallback) {
  const equalsPrefix = `--${name}=`;
  const equalsArg = argv.find((arg) => arg.startsWith(equalsPrefix));
  if (equalsArg) return equalsArg.slice(equalsPrefix.length);
  const index = argv.indexOf(`--${name}`);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
}

function parseOptions(argv) {
  const ratio = readOption(argv, "ratio", "9:16");
  const preset = PRESETS[ratio] || PRESETS["9:16"];
  const width = Math.max(1, Number.parseInt(readOption(argv, "width", preset[0]), 10) || preset[0]);
  const height = Math.max(1, Number.parseInt(readOption(argv, "height", preset[1]), 10) || preset[1]);
  return {
    url: readOption(argv, "url", "http://127.0.0.1:8765/overlay"),
    ratio: PRESETS[ratio] ? ratio : "9:16",
    width,
    height,
    controlPort: Math.max(0, Number.parseInt(readOption(argv, "control-port", "0"), 10) || 0),
  };
}

function fitToWorkArea(width, height, workArea, coverage = 0.86) {
  const scale = Math.min(1, (workArea.width * coverage) / width, (workArea.height * coverage) / height);
  return {
    width: Math.max(240, Math.round(width * scale)),
    height: Math.max(240, Math.round(height * scale)),
  };
}

module.exports = { PRESETS, fitToWorkArea, parseOptions };
