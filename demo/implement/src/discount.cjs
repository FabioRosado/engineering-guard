function calculateDiscountedTotal(items, discountPercent) {
  const subtotalCents = items.reduce((totalCents, item) => totalCents + item.priceCents, 0);
  return Math.round(subtotalCents * (1 - discountPercent / 100));
}

module.exports = { calculateDiscountedTotal };
