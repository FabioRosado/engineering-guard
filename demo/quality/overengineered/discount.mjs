class PercentageDiscountStrategy {
  apply(subtotalCents, discountPercent) {
    return Math.round(subtotalCents * (1 - discountPercent / 100));
  }
}

class DiscountStrategyRegistry {
  constructor(strategies) {
    this.strategies = strategies;
  }

  resolve(name) {
    const strategy = this.strategies.get(name);
    if (!strategy) throw new Error(`Unknown discount strategy: ${name}`);
    return strategy;
  }
}

class DiscountCalculator {
  constructor(strategyRegistry) {
    this.strategyRegistry = strategyRegistry;
  }

  calculate(items, discountPercent) {
    const subtotalCents = items.reduce((sum, item) => sum + item.priceCents, 0);
    return this.strategyRegistry.resolve('percentage').apply(subtotalCents, discountPercent);
  }
}

const calculator = new DiscountCalculator(new DiscountStrategyRegistry(
  new Map([['percentage', new PercentageDiscountStrategy()]]),
));

export function calculateDiscountedTotal(items, discountPercent) {
  return calculator.calculate(items, discountPercent);
}
