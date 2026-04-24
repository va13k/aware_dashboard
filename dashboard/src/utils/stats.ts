export function mean(values: number[]): number {
  if (!values.length) return 0
  return values.reduce((a, b) => a + b, 0) / values.length
}

export function median(values: number[]): number {
  if (!values.length) return 0
  const s = [...values].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

export function fmt(value: number, decimals = 2): string {
  return value.toFixed(decimals)
}
