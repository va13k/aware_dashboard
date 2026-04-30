export function min(values: number[]): number {
  if (!values.length) return 0
  return Math.min(...values)
}

export function max(values: number[]): number {
  if (!values.length) return 0
  return Math.max(...values)
}

export function fmt(value: number, decimals = 2): string {
  return value.toFixed(decimals)
}
