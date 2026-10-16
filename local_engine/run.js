#!/usr/bin/env node
// Local replacement for the RCK /map endpoint (no API key needed).
// Reads one JSON request from stdin:
//   {"mapping": "<yarrrml>", "inputs": {"input": "<raw source text>"},
//    "functions": {"<full fn URI>": "<arrow fn source>"}, "options": {...}}
// Writes the JSON-LD result to stdout; on failure writes the error to stderr and exits 1.
const Y2R = require('@rmlio/yarrrml-parser/lib/rml-generator');
const N3 = require('n3');
const rocketrml = require('rocketrml');
const YAML = require('yamljs'); // the YAML parser yarrrml-parser itself uses
// yarrrml-parser logs "prefix \"['schema\" was not found" for every bracket-notation
// reference like $(['schema:name']) — harmless (RCK resolves them the same way),
// but it buries real errors. Keep only warnings/errors that aren't that one.
require('js-logger').setHandler((messages, context) => {
  const msg = Array.from(messages).join(' ');
  if (context.level.value >= 3000 && !/^prefix ".*" was not found\.$/.test(msg)) {
    process.stderr.write(`yarrrml-parser: ${msg}\n`);
  }
});

// RCK accepts POSITIONAL function parameters, e.g.
//   {fn: myfunc:f, pms: ["$(a)", "$(b)"]}
// Stock yarrrml-parser only understands [parameter, value] pairs and silently
// turns a bare value into the constant "undefined". RocketRML passes parameters
// to JS functions by position only, so the parameter predicate is irrelevant —
// rewrite bare values into pairs with synthetic predicates.
const PARAM_PREFIX = 'rmlgenparam';
function normalizePositionalParams(node) {
  if (Array.isArray(node)) {
    node.forEach(normalizePositionalParams);
    return;
  }
  if (!node || typeof node !== 'object') return;
  const hasFn = 'fn' in node || 'function' in node;
  for (const key of ['pms', 'parameters']) {
    if (hasFn && Array.isArray(node[key])) {
      node[key] = node[key].map((p, i) =>
        (p !== null && typeof p !== 'object') ? [`${PARAM_PREFIX}:p${i}`, p] : p);
    }
  }
  Object.values(node).forEach(normalizePositionalParams);
}

// Stock yarrrml-parser ends a $(...) reference at the FIRST ")", so references
// containing parentheses — JSONPath filters like $(a[?(@.b=='c')].d) — get cut
// in half. RCK balances parentheses. Swap every such reference for a plain
// placeholder before conversion and put the original back into the RML after.
function protectReferences(node, refs) {
  if (typeof node === 'string') {
    let out = '';
    let i = 0;
    while (i < node.length) {
      const start = node.indexOf('$(', i);
      if (start === -1) { out += node.slice(i); break; }
      let depth = 0;
      let end = -1;
      for (let j = start + 1; j < node.length; j++) {
        if (node[j] === '(') depth++;
        else if (node[j] === ')' && --depth === 0) { end = j; break; }
      }
      if (end === -1) { out += node.slice(i); break; }
      const expr = node.slice(start + 2, end);
      if (/[()]/.test(expr)) {
        const key = `RMLGENREF${refs.length}X`;
        refs.push(expr);
        out += node.slice(i, start) + `$(${key})`;
      } else {
        out += node.slice(i, end + 1);
      }
      i = end + 1;
    }
    return out;
  }
  if (Array.isArray(node)) return node.map((n) => protectReferences(n, refs));
  if (node && typeof node === 'object') {
    for (const k of Object.keys(node)) node[k] = protectReferences(node[k], refs);
  }
  return node;
}

function restoreReferences(quads, refs) {
  if (!refs.length) return quads;
  const { literal } = N3.DataFactory;
  const re = /RMLGENREF(\d+)X/g;
  return quads.map((q) => {
    if (q.object.termType !== 'Literal' || !re.test(q.object.value)) return q;
    re.lastIndex = 0;
    const value = q.object.value.replace(re, (_, n) => refs[Number(n)]);
    const obj = literal(value, q.object.language || q.object.datatype);
    return N3.DataFactory.quad(q.subject, q.predicate, obj, q.graph);
  });
}

function yarrrmlToRml(yarrrml) {
  const doc = YAML.parse(yarrrml);
  doc.prefixes = { ...(doc.prefixes || {}), [PARAM_PREFIX]: 'https://w3id.org/rml-mapping-generator/param/' };
  normalizePositionalParams(doc.mappings);
  const refs = [];
  doc.mappings = protectReferences(doc.mappings, refs);
  const y2r = new Y2R();
  const quads = restoreReferences(y2r.convert(JSON.stringify(doc)), refs); // JSON is valid YAML
  const prefixes = { ...y2r.getPrefixes(), '': y2r.getBaseIRI() };
  return new Promise((resolve, reject) => {
    const writer = new N3.Writer({ prefixes });
    writer.addQuads(quads);
    writer.end((err, ttl) => (err ? reject(err) : resolve(ttl)));
  });
}

async function main() {
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  const req = JSON.parse(raw);

  // Same defaults the RCK client sends (functions/rml.py).
  const options = { toRDF: false, replace: true, ignoreEmptyStrings: true, ...(req.options || {}) };
  if (req.functions) {
    // RCK accepts function bodies as strings; RocketRML wants real functions.
    options.functions = {};
    for (const [uri, src] of Object.entries(req.functions)) {
      // eslint-disable-next-line no-eval
      options.functions[uri] = (0, eval)(src);
    }
  }

  const rml = req.mappingType === 'rml' ? req.mapping : await yarrrmlToRml(req.mapping);
  const out = await rocketrml.parseFileLive(rml, req.inputs, options);
  process.stdout.write(JSON.stringify(out, null, 4));
}

main().catch((e) => {
  process.stderr.write(String(e && e.stack ? e.stack : e));
  process.exit(1);
});
