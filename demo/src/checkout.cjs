const pricing = require('./pricing.cjs');

function checkout(items, discountPercent, paymentGateway) {
  const totalCents = pricing.calculateTotal(items, discountPercent);
  return paymentGateway.charge(totalCents);
}

module.exports = { checkout };
