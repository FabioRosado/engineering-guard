const assert = require('node:assert/strict');
const test = require('node:test');
const { checkout } = require('../src/checkout.cjs');

test('behavior: charges the percentage-discounted total', () => {
  const chargedAmounts = [];
  const paymentGateway = {
    charge(amount) {
      chargedAmounts.push(amount);
      return { accepted: true };
    },
  };

  checkout([{ priceCents: 10000 }], 10, paymentGateway);

  assert.deepEqual(chargedAmounts, [9000]);
});
