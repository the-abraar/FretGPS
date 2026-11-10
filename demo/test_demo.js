// node demo/test_demo.js: the page's JS placement must match fretmap.py's output in demo/data/ note for note.
const fs = require('fs'), path = require('path'), assert = require('assert');
const dir = __dirname, html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
const riff = html.match(/<script id="riff" type="application\/json">([\s\S]*?)<\/script>/)[1];
const code = html.match(/<script>\n([\s\S]*?)\n\/\/ Drawing/)[1];  // the placement logic only, no DOM
const { place } = new Function(code + '\nreturn { place };')();
const truth = JSON.parse(riff).notes;
for (const [file, mode, around] of [['riff_lowest.json', 'lowest'], ['riff_least.json', 'least'], ['riff_around7.json', 'around', 7]]) {
  const py = JSON.parse(fs.readFileSync(path.join(dir, 'data', file), 'utf8'));
  const keys = n => ({ start: n.start, end: n.end, midi: n.midi, true_string: n.true_string, true_fret: n.true_fret });
  assert.deepStrictEqual(py.notes.map(keys), truth, `${file}: inline riff == Python input`);
  const js = place(truth, mode, around);
  assert.deepStrictEqual(js.map(n => [n.start, n.string, n.fret]), py.notes.map(n => [n.start, n.string, n.fret]), file);
  const right = js.filter(n => n.string === n.true_string).length;
  assert.strictEqual(right, py.right_string);
  console.log(`${file}: ${js.length} notes match, ${right}/${truth.length} on the right string`);
}
assert(html.includes('upper bound'), 'hint results must say upper bound');
console.log('ok');
