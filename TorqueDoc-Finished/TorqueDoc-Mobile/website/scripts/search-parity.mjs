// Checks that the phone's search returns exactly what the laptop returns for the same library and questions.
import { readFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import sqlite3InitModule from '@sqlite.org/sqlite-wasm';
import { Library, queryTerms } from '../src/engine.js';

const MOBILE = dirname(dirname(fileURLToPath(import.meta.url)));
const ROOT = dirname(MOBILE);
const database = join(MOBILE, 'dist', 'library.db');
const sqlite3 = await sqlite3InitModule();
const library = new Library(sqlite3, new Uint8Array(readFileSync(database)));
const training = library.documents('training')[0].id;
const cases = [
  ['What is the cover bolt torque?', 'training', null], ['bolt', 'training', null], ['TRAIN-8 cover', 'training', null],
  ['coolant capacity', 'training', null], ['extraterrestrial fluxcapacitance', 'training', null], ['cover bolt torque', 'training', training],
  ['engine oil capacity', 'cat', null], ['swing torque', 'volvo', null], ['hydraulic tank', 'deere', null], ['operating weight', 'volvo', null],
  ['1R-0750', 'cat', null], ['E360 fault', 'cat', null], ['the of and', 'cat', null], ['ﬁlter replacing tightening', 'training', null],
];
const python = process.env.PYTHON || [join(ROOT, '.venv', 'Scripts', 'python.exe'), join(ROOT, '.venv', 'bin', 'python')].find(existsSync) || 'python3';
const expected = JSON.parse(execFileSync(python, [join(MOBILE, 'scripts', 'desktop_search.py'), database, JSON.stringify(cases)]).toString());
let failures = 0;
cases.forEach(([question, machine, documentId], i) => {
  const ids = library.search(question, machine, documentId).map(p => p.id);
  const terms = queryTerms(question);
  const same = JSON.stringify(ids) === JSON.stringify(expected[i].ids) && JSON.stringify(terms) === JSON.stringify(expected[i].terms);
  if (!same) failures++;
  console.log(`${same ? 'same' : 'DIFFERENT'}  ${machine.padEnd(8)} ${JSON.stringify(question).padEnd(40)} ${ids.length} result(s)${same ? '' : `\n   phone:  ${JSON.stringify(terms)} ${JSON.stringify(ids)}\n   laptop: ${JSON.stringify(expected[i].terms)} ${JSON.stringify(expected[i].ids)}`}`);
});
console.log(failures ? `${failures} difference(s)` : `All ${cases.length} searches identical to the laptop.`);
process.exit(failures ? 1 : 0);
