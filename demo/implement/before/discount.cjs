function calculateDiscountedTotal(a, b) {
  try {
    return Math.round(a.map((x) => x.priceCents).reduce((x, y) => x + y, 0) * (1 - b / 100));
  } catch {
    return 0;
  }
}

module.exports = { calculateDiscountedTotal };
