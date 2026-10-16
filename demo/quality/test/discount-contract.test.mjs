import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const implementation = process.env.ENGINEERING_GUARD_DISCOUNT_IMPLEMENTATION;
if (!implementation) throw new Error('Set ENGINEERING_GUARD_DISCOUNT_IMPLEMENTATION to an implementation fixture.');
const { calculateDiscountedTotal } = await import(pathToFileURL(implementation).href);

test('calculates a percentage discount over the combined item subtotal', () => {
  assert.equal(calculateDiscountedTotal([{ priceCents: 1000 }, { priceCents: 2000 }], 10), 2700);
});

test('preserves the subtotal when no discount applies', () => {
  assert.equal(calculateDiscountedTotal([{ priceCents: 1000 }, { priceCents: 2000 }], 0), 3000);
});

test('returns zero when the full subtotal is discounted', () => {
  assert.equal(calculateDiscountedTotal([{ priceCents: 3000 }], 100), 0);
});
