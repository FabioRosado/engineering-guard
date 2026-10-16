function calculateTotal(items, discountPercent) {
  const subtotal = items.reduce((sum, item) => sum + item.priceCents, 0);
  return subtotal - discountPercent;
}

module.exports = { calculateTotal };
