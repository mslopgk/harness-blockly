// Generate src/data/robotSpecs.json — a hand-curated LibrarySpec for dobotkit (Dobot Magician
// Lite arm + Magician GO car), registered as built-in "dobotkit" toolbox blocks at app startup
// (offline, no runtime introspection). dobotkit's API is class/method-heavy and raw introspection
// is noisy (enum/exception boilerplate: bit_length/with_traceback/...), so — like cv2 in
// gen-stdlib-blocks.cjs — only the curriculum-essential subset is hand-authored here.
// Signatures verified via `python -c "import inspect, dobotkit; ..."` on 2026-07-19 (dobotkit 0.1.x):
//   MagicianLite.move_to(x, y, z, r=0, *, ...); set_speed(velocity, acceleration); ...
//   MagicianGO.open(port_name='COM5'); forward(speed); move(x=0,y=0,r=0); drive_for(x,y,r,seconds); ...
// Re-generate with: node scripts/gen-robot-blocks.cjs
const fs = require('fs');
const path = require('path');

const P = (...names) => names.map((n) => ({ name: n, kind: 'positional', hasDefault: false }));
// method on the arm/car receiver: title "<recv>.<name>", lowers "<recv>.<name>(args)".
// returns:false → command (green statement) block; returns:true → value (reporter) block.
const armCmd = (name, ...args) => ({ kind: 'method', owner: 'Arm', name, params: P(...args), returns: false });
const armVal = (name, ...args) => ({ kind: 'method', owner: 'Arm', name, params: P(...args), returns: true });
const carCmd = (name, ...args) => ({ kind: 'method', owner: 'Car', name, params: P(...args), returns: false });
const carVal = (name, ...args) => ({ kind: 'method', owner: 'Car', name, params: P(...args), returns: true });

const spec = {
  module: 'dobotkit',
  entries: [
    // ── 팔 (MagicianLite) — 수신자 변수 arm ──
    { kind: 'class', name: 'MagicianLite', qualName: 'dobotkit.MagicianLite', params: [], returns: true }, // arm = dobotkit.MagicianLite()
    armCmd('home'),
    armCmd('move_to', 'x', 'y', 'z'),
    armCmd('move_relative', 'dx', 'dy', 'dz'),
    armCmd('suck', 'on'),
    armCmd('grip', 'on'),
    armCmd('pump_off'),
    armCmd('set_speed', 'velocity', 'acceleration'),
    armVal('get_pose'),
    // ── 차 (MagicianGO) — 수신자 변수 car ──
    // 연결은 classmethod open: from dobotkit import MagicianGO → car = MagicianGO.open("COM5")
    { kind: 'function', name: 'open', module: 'dobotkit.MagicianGO', qualName: 'dobotkit.MagicianGO.open', params: P('port_name'), returns: true },
    carCmd('forward', 'speed'),
    carCmd('backward', 'speed'),
    carCmd('spin', 'speed'),
    carCmd('strafe', 'speed'),
    carCmd('move', 'x', 'y', 'r'),
    carCmd('drive_for', 'x', 'y', 'r', 'seconds'),
    carCmd('stop'),
    carCmd('buzzer'),
    carVal('battery'),
    carVal('ultrasonic'),
    carVal('imu_angle'),
  ],
};

const dest = path.join(__dirname, '..', 'src', 'data', 'robotSpecs.json');
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, JSON.stringify([spec], null, 1));
console.log(`[robot] wrote dobotkit spec (${spec.entries.length} entries) -> ${path.relative(path.join(__dirname, '..'), dest)}`);
