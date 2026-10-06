/** Reject calendar rollover before displaying backend historical metadata. */
export function validTimestamp(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(value) || !Number.isFinite(Date.parse(value))) return false
  const day = value.slice(0, 10)
  const parsed = Date.parse(`${day}T00:00:00Z`)
  return Number(day.slice(0, 4)) > 0 && Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === day
}
