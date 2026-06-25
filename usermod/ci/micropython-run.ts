import fs from 'fs';
import minimist from 'minimist';
import { GDBTCPServer } from '../src/gdb/gdb-tcp-server.js';
import { Simulator } from '../src/simulator.js';
import { USBCDC } from '../src/usb/cdc.js';
import { ConsoleLogger, LogLevel } from '../src/utils/logging.js';
import { bootromB1 } from './bootrom.js';
import { loadCircuitpythonFlashImage, loadMicropythonFlashImage, loadUF2 } from './load-flash.js';

const args = minimist(process.argv.slice(2), {
  string: [
    'image',        // UF2 image to load
    'expect-text',  // exit 0 when this text appears on a serial line
    'exec',         // single line of Python to run after boot
    'run',          // .py file to run via exec("""...""") after boot
    'timeout',      // seconds before aborting with exit code 2
  ],
  boolean: ['gdb', 'circuitpython'],
});

const expectText  = args['expect-text'] as string | undefined;
const execCode    = args['exec']        as string | undefined;
const runFile     = args['run']         as string | undefined;
const timeoutSec  = args['timeout'] ? Number(args['timeout']) : undefined;

const simulator = new Simulator();
const mcu = simulator.rp2040;
mcu.loadBootrom(bootromB1);
mcu.logger = new ConsoleLogger(LogLevel.Error);

const imageName = args.circuitpython
  ? (args.image ?? 'adafruit-circuitpython-raspberry_pi_pico-en_US-8.0.2.uf2')
  : (args.image ?? 'RPI_PICO-20230426-v1.20.0.uf2');

console.log(`Loading uf2 image ${imageName}`);
loadUF2(imageName, mcu);

if (fs.existsSync('littlefs.img') && !args.circuitpython) {
  loadMicropythonFlashImage('littlefs.img', mcu);
} else if (fs.existsSync('fat12.img') && args.circuitpython) {
  loadCircuitpythonFlashImage('fat12.img', mcu);
}

if (args.gdb) {
  const gdbServer = new GDBTCPServer(simulator, 3333);
  console.log(`RP2040 GDB Server ready! Listening on port ${gdbServer.port}`);
}

if (timeoutSec) {
  setTimeout(() => { process.stderr.write(`Timeout after ${timeoutSec}s\n`); process.exit(2); },
    timeoutSec * 1000);
}

const cdc = new USBCDC(mcu.usbCtrl);

// ── Rate-limited serial queue ─────────────────────────────────────────────────
// Used only for --run; keeps CDC receive buffer from overflowing.
const BYTE_DELAY_MS  = 2;
const BYTES_PER_TICK = 4;
const byteQueue: number[] = [];
let queueRunning = false;

const drainQueue = () => {
  if (byteQueue.length === 0) { queueRunning = false; return; }
  const n = Math.min(BYTES_PER_TICK, byteQueue.length);
  for (let i = 0; i < n; i++) cdc.sendSerialByte(byteQueue.shift()!);
  setTimeout(drainQueue, BYTE_DELAY_MS);
};

const queueStr = (s: string) => {
  for (let i = 0; i < s.length; i++) byteQueue.push(s.charCodeAt(i));
  if (!queueRunning) { queueRunning = true; setTimeout(drainQueue, 0); }
};

const sendNow = (s: string) => {
  for (let i = 0; i < s.length; i++) cdc.sendSerialByte(s.charCodeAt(i));
};

// ── Boot ──────────────────────────────────────────────────────────────────────
cdc.onDeviceConnected = () => {
  if (!args.circuitpython) sendNow('\r\n');
  else cdc.sendSerialByte(3);
};

// ── Exit after script finishes ────────────────────────────────────────────────
// Called when the REPL shows '>>> ' after our code ran.
// Exits 1 if "FAILED" appears in the captured output (matches "N test(s) FAILED").
const exitAfterRun = () => {
  process.exit(serialBuf.includes('FAILED') ? 1 : 0);
};

// ── Serial data handler ───────────────────────────────────────────────────────
let serialBuf   = '';
let injected    = false;
let currentLine = '';

cdc.onSerialData = (value) => {
  process.stdout.write(value);
  serialBuf += String.fromCharCode(...value);

  for (const byte of value) {
    const char = String.fromCharCode(byte);
    if (char === '\n') {
      if (expectText && currentLine.includes(expectText)) process.exit(0);
      currentLine = '';
    } else {
      currentLine += char;
    }
  }

  // ── --exec: send single line, then wait for next '>>> ' ──────────────────
  if (execCode && !injected && serialBuf.includes('>>> ')) {
    injected = true;
    serialBuf = '';
    sendNow(execCode + '\r\n');
    return;
  }
  if (execCode && injected && !expectText && serialBuf.includes('>>> ')) {
    exitAfterRun();
  }

  // ── --run: send file as exec("""...""") rate-limited, same exit logic ─────
  if (runFile && !injected && serialBuf.includes('>>> ')) {
    injected = true;
    serialBuf = '';
    const src = fs.readFileSync(runFile, 'utf-8');
    const escaped = src.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
    queueStr('exec("""' + escaped + '""")\r\n');
    return;
  }
  if (runFile && injected && !expectText && serialBuf.includes('>>> ')) {
    exitAfterRun();
  }
};

// ── Interactive stdin ─────────────────────────────────────────────────────────
if (process.stdin.isTTY) process.stdin.setRawMode(true);
process.stdin.on('data', (chunk: Buffer) => {
  if (chunk[0] === 24) process.exit(0); // Ctrl+X
  for (const byte of chunk) cdc.sendSerialByte(byte);
});

simulator.rp2040.core.PC = 0x10000000;
simulator.execute();
