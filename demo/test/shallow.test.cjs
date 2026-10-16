const assert = require('node:assert/strict');
const test = require('node:test');
const pricing = require('../src/pricing.cjs');
const { checkout } = require('../src/checkout.cjs');

test('shallow: sends the calculator result to the gateway', (context) => {
  context.mock.method(pricing, 'calculateTotal', () => 9000);
  const charge = context.mock.fn((amount) => ({ amount }));

  const result = checkout([{ priceCents: 10000 }], 10, { charge });

  assert.equal(charge.mock.calls[0].arguments[0], 9000);
  assert.deepEqual(result, { amount: 9000 });
});
