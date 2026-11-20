// Run with: npm test (Node strips the types from src/lib/csp.ts).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apiOrigins, contentSecurityPolicy } from '../src/lib/csp.ts';

const directives = (policy) => Object.fromEntries(policy.split('; ').map((part) => {
  const [name, ...values] = part.split(' ');
  return [name, values];
}));

test('production scripts need the nonce and nothing runs eval', () => {
  const csp = directives(contentSecurityPolicy('abc123', 'https://api.argus.test', false));
  assert.deepEqual(csp['script-src'], ["'self'", "'nonce-abc123'", "'strict-dynamic'"]);
  assert.deepEqual(csp['style-src'], ["'self'", "'nonce-abc123'"]);
  assert.deepEqual(csp['object-src'], ["'none'"]);
  assert.deepEqual(csp['frame-ancestors'], ["'none'"]);
  assert.ok('upgrade-insecure-requests' in csp);
});

test('the browser may reach only this origin and the API over HTTP and WebSocket', () => {
  const csp = directives(contentSecurityPolicy('n', 'https://api.argus.test/', false));
  assert.deepEqual(csp['connect-src'], ["'self'", 'https://api.argus.test', 'wss://api.argus.test']);
  assert.deepEqual(apiOrigins('http://localhost:8000'), ['http://localhost:8000', 'ws://localhost:8000']);
  assert.deepEqual(apiOrigins('not a url'), []);
});

test('development allows eval and inline styles for the dev overlay', () => {
  const csp = directives(contentSecurityPolicy('n', 'http://localhost:8000', true));
  assert.ok(csp['script-src'].includes("'unsafe-eval'"));
  assert.deepEqual(csp['style-src'], ["'self'", "'unsafe-inline'"]);
  assert.equal('upgrade-insecure-requests' in csp, false);
});
