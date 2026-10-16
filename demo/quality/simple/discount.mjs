export function calculateDiscountedTotal(items, discountPercent) {
  const subtotalCents = items.reduce((sum, item) => sum + item.priceCents, 0);
  return Math.round(subtotalCents * (1 - discountPercent / 100));
}
