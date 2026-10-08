// Money display for education blocks. Must match backend/app/services/money.py: a backend test runs MONEY_VECTORS
// through the Python formatter, so the two cannot drift apart.
//
// NPR/INR use Indian digit grouping ("NPR 25,00,000"); USD/GBP/EUR use their symbol ("£20,000"); any other currency
// uses its code ("AUD 20,000"). Amounts are whole units. Grouping is written out (not toLocaleString) so the result does
// not depend on the visitor's browser locale.

const ALIASES: Record<string, string> = {
  '$': 'USD', usd: 'USD', 'us$': 'USD', '£': 'GBP', gbp: 'GBP', '€': 'EUR', eur: 'EUR',
  'a$': 'AUD', aud: 'AUD', 'c$': 'CAD', cad: 'CAD',
  npr: 'NPR', nrs: 'NPR', nr: 'NPR', '₹': 'INR', inr: 'INR',
}
const SYMBOLS: Record<string, string> = { USD: '$', GBP: '£', EUR: '€' }
const INDIAN_GROUPING = new Set(['NPR', 'INR'])

// Blocks stored before currencies were ISO codes carry a symbol ("$"); both forms are accepted.
export function normalizeCurrency(value: string): string {
  const token = (value || '').trim()
  const known = ALIASES[token.toLowerCase()]
  if (known) return known
  return /^[A-Za-z]{3}$/.test(token) ? token.toUpperCase() : token
}

function group(n: number, indian: boolean): string {
  const digits = String(Math.abs(n))
  let grouped: string
  if (indian && digits.length > 3) {
    const head = digits.slice(0, -3).replace(/(\d)(?=(\d{2})+$)/g, '$1,')
    grouped = `${head},${digits.slice(-3)}`
  } else {
    grouped = digits.replace(/\B(?=(\d{3})+$)/g, ',')
  }
  return n < 0 ? `-${grouped}` : grouped
}

export function formatMoney(amount: number, currency: string): string {
  const code = normalizeCurrency(currency)
  const grouped = group(Math.round(amount), INDIAN_GROUPING.has(code))
  const symbol = SYMBOLS[code]
  if (symbol) return `${symbol}${grouped}`
  return code ? `${code} ${grouped}` : grouped
}

// [amount, currency as stored, expected text]
export const MONEY_VECTORS: [number, string, string][] = [
  [2500000, 'NPR', 'NPR 25,00,000'],
  [2500000, 'npr', 'NPR 25,00,000'],
  [999, 'NPR', 'NPR 999'],
  [1000, 'INR', 'INR 1,000'],
  [100000, 'INR', 'INR 1,00,000'],
  [12345678, 'NPR', 'NPR 1,23,45,678'],
  [20000, 'GBP', '£20,000'],
  [30000, 'USD', '$30,000'],
  [30000, '$', '$30,000'],
  [45000, 'EUR', '€45,000'],
  [20000, 'AUD', 'AUD 20,000'],
  [1234567, 'CAD', 'CAD 1,234,567'],
  [0, 'USD', '$0'],
  [-1500, 'NPR', 'NPR -1,500'],
  [14999.6, 'USD', '$15,000'],
  [1234, 'Zorb', 'Zorb 1,234'],
  [5000, '', '5,000'],
]
