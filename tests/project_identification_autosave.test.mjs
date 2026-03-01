import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

async function loadAutosaveModule() {
  const source = await readFile(new URL('../static/js/projectIdentificationAutosave.js', import.meta.url), 'utf8');
  const dataUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
  return import(dataUrl);
}

test('computeChangedIdentificationPayload returns only changed values', async () => {
  const mod = await loadAutosaveModule();
  const fields = ['plot_number', 'cadastral_district', 'street', 'city'];
  const changed = mod.computeChangedIdentificationPayload(
    fields,
    { plot_number: '12/4', cadastral_district: '0001', street: 'Leśna', city: 'Warszawa' },
    { plot_number: '12/4', cadastral_district: '0001', street: 'Klonowa', city: 'Warszawa' },
  );
  assert.deepEqual(changed, { street: 'Leśna' });
});

test('autosave debounces input and persists only last value', async () => {
  const mod = await loadAutosaveModule();
  const calls = [];
  const autosave = mod.createIdentificationAutosave({
    fields: ['street'],
    debounceMs: 30,
    retryDelayMs: 30,
    onStatus: () => {},
    async persist(payload) {
      calls.push(payload);
      return { street: payload.street };
    },
  });

  autosave.setPersisted({ street: 'Klonowa' });
  autosave.updateDraftField('street', 'Le');
  autosave.updateDraftField('street', 'Leś');
  autosave.updateDraftField('street', 'Leśna');

  await new Promise((resolve) => setTimeout(resolve, 80));

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], { street: 'Leśna' });
});

test('autosave reports error and retries', async () => {
  const mod = await loadAutosaveModule();
  let attempts = 0;
  const statuses = [];
  const autosave = mod.createIdentificationAutosave({
    fields: ['city'],
    debounceMs: 10,
    retryDelayMs: 20,
    onStatus(status) {
      statuses.push(status);
    },
    async persist(payload) {
      attempts += 1;
      if (attempts === 1) {
        throw new Error('boom');
      }
      return { city: payload.city };
    },
  });

  autosave.setPersisted({ city: 'Warszawa' });
  autosave.updateDraftField('city', 'Kraków');

  await new Promise((resolve) => setTimeout(resolve, 100));

  assert.ok(statuses.includes('error'));
  assert.ok(statuses.includes('saved'));
  assert.equal(attempts, 2);
});
