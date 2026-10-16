const assert = require('node:assert/strict');
const test = require('node:test');
const { calculateDiscountedTotal } = require('../src/discount.cjs');

test('calculates the percentage-discounted amount from item prices', () => {
  assert.equal(calculateDiscountedTotal([{ priceCents: 10000 }], 10), 9000);
});

test('keeps invalid input errors visible instead of returning a plausible amount', () => {
  assert.throws(() => calculateDiscountedTotal(null, 10), TypeError);
});
