// Compatibility for the original npm start; Python now serves UI and API.
const {spawn} = require('child_process');
const {existsSync} = require('fs');
const path = require('path');
const python = path.join(__dirname, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python)) {
  console.error('Run setup-windows.bat first (or create .venv and install requirements.txt).');
  process.exit(1);
}
const child = spawn(python, ['run.py'], {cwd:__dirname, stdio:'inherit', env:process.env});
child.on('error', error => {console.error(error.message); process.exitCode=1;});
child.on('exit', code => {process.exitCode=code || 0;});
process.on('SIGINT', () => child.kill('SIGINT'));
process.on('SIGTERM', () => child.kill('SIGTERM'));
