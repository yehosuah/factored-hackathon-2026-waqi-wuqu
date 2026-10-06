import type { Locale } from './i18n.ts'

export const workflowCopy = {
  es: {
    unavailable: 'No disponible', updated: 'Actualización en la fuente', processDate: 'Fecha de proceso',
    cutoffNote: 'La fuente no informa una fecha de corte global. Su fecha de actualización no indica una operación en vivo.',
    cardContext: 'Tarjeta para esta consulta', choose: 'Selecciona una tarjeta',
    clarify: '¿Qué necesitas hacer?', pause: 'Pausa temporal', block: 'Pérdida o robo',
    pauseHelp: 'Puedes solicitar la reactivación de una tarjeta pausada.',
    blockHelp: 'El bloqueo por pérdida o robo no puede deshacerse automáticamente. Puedes solicitar un reemplazo o atención humana.',
    sendChoice: 'Enviar selección al chat', selectionNote: 'Enviar esta selección no confirma una acción. Revisa después la solicitud del servicio.',
    stubLimit: 'Este modo de prueba solo permite solicitar una pausa desde el chat. Para pérdida, robo o cargos, usa los controles de Tarjetas.',
    disabled: 'El servicio de conversación no está disponible. Puedes usar los controles de Tarjetas.',
    report: 'Continuar con atención humana', reported: 'Caso registrado para esta solicitud',
    chargeIdentityMissing: 'Esta solicitud no incluye un movimiento y una fecha de proceso válidos para continuar con atención humana.',
    reviewOnly: 'Se registró una solicitud de revisión. Esto no significa un reembolso ni una decisión sobre fraude.',
    supportSummary: 'Solicito revisión de un cargo que no reconozco.',
    question: '¿Cuál es el resultado de la revisión del cargo?',
    caseScope: 'El caso incluye referencias a esta solicitud. El servicio puede adjuntar otras acciones de la misma tarjeta; no es un expediente limitado a esta conversación.',
    chatMovement: 'Consultar este movimiento en el chat', movementContext: 'Movimiento para esta consulta',
    clearMovement: 'Quitar movimiento', sendCharge: 'Solicitar revisión en el chat',
    chargePrompt: 'No reconozco este cargo. Solicito registrar una revisión, sin afirmar que se aprobó un reembolso.',
    handoffPrompt: 'Solicito atención humana para esta conversación. Incluye mi solicitud, las acciones verificadas y las preguntas pendientes.',
    human: 'Solicitar atención para este chat', noCaseYet: 'La solicitud de atención debe ser registrada por el servicio antes de mostrar un caso.',
    transaction: 'Movimiento', request: 'Solicitud', conversation: 'Conversación de referencia',
    chargeConfirm: 'Solicitas una revisión; no se aprueba un reembolso.',
  },
  pt: {
    unavailable: 'Indisponível', updated: 'Atualização na fonte', processDate: 'Data de processamento',
    cutoffNote: 'A fonte não informa uma data de corte global. Sua data de atualização não indica uma operação ao vivo.',
    cardContext: 'Cartão para esta consulta', choose: 'Selecione um cartão',
    clarify: 'O que você precisa fazer?', pause: 'Pausa temporária', block: 'Perda ou roubo',
    pauseHelp: 'Você pode solicitar a reativação de um cartão pausado.',
    blockHelp: 'O bloqueio por perda ou roubo não pode ser desfeito automaticamente. Você pode solicitar substituição ou atendimento humano.',
    sendChoice: 'Enviar seleção ao chat', selectionNote: 'Enviar esta seleção não confirma uma ação. Revise depois a solicitação do serviço.',
    stubLimit: 'Este modo de teste só permite solicitar uma pausa pelo chat. Para perda, roubo ou cobranças, use os controles de Cartões.',
    disabled: 'O serviço de conversa está indisponível. Você pode usar os controles de Cartões.',
    report: 'Continuar com atendimento humano', reported: 'Caso registrado para esta solicitação',
    chargeIdentityMissing: 'Esta solicitação não inclui um movimento e uma data de processamento válidos para continuar com atendimento humano.',
    reviewOnly: 'Uma solicitação de revisão foi registrada. Isso não significa reembolso nem decisão sobre fraude.',
    supportSummary: 'Solicito revisão de uma cobrança que não reconheço.',
    question: 'Qual é o resultado da revisão da cobrança?',
    caseScope: 'O caso inclui referências a esta solicitação. O serviço pode anexar outras ações do mesmo cartão; não é um registro limitado a esta conversa.',
    chatMovement: 'Consultar este movimento no chat', movementContext: 'Movimento para esta consulta',
    clearMovement: 'Remover movimento', sendCharge: 'Solicitar revisão no chat',
    chargePrompt: 'Não reconheço esta cobrança. Solicito registrar uma revisão, sem afirmar que um reembolso foi aprovado.',
    handoffPrompt: 'Solicito atendimento humano para esta conversa. Inclua minha solicitação, as ações verificadas e as perguntas pendentes.',
    human: 'Solicitar atendimento para este chat', noCaseYet: 'A solicitação de atendimento precisa ser registrada pelo serviço antes de mostrar um caso.',
    transaction: 'Movimento', request: 'Solicitação', conversation: 'Conversa de referência',
    chargeConfirm: 'Você solicita uma revisão; nenhum reembolso é aprovado.',
  },
} satisfies Record<Locale, Record<string, string>>

const labels: Record<string, [string, string]> = {
  'Tarjeta Crédito': ['Tarjeta de crédito', 'Cartão de crédito'],
  'Tarjeta Débito': ['Tarjeta de débito', 'Cartão de débito'],
  team_synthetic: ['Datos sintéticos del equipo', 'Dados sintéticos da equipe'],
  organizer_synthetic: ['Datos sintéticos del organizador', 'Dados sintéticos do organizador'],
  team_fixture: ['Datos de demostración', 'Dados de demonstração'],
  historical_source_value: ['Valor histórico de la fuente', 'Valor histórico da fonte'],
  state_change_verified: ['Cambio de estado verificado', 'Mudança de estado verificada'],
  replacement_request_registered: ['Solicitud de reemplazo registrada', 'Solicitação de substituição registrada'],
  request_registered_for_human_review: ['Solicitud de revisión registrada', 'Solicitação de revisão registrada'],
  Compra: ['Compra', 'Compra'], Pago: ['Pago', 'Pagamento'], Retiro: ['Retiro', 'Saque'],
  Transferencia: ['Transferencia', 'Transferência'], Depósito: ['Depósito', 'Depósito'],
  Completada: ['Completada', 'Concluída'], Pendiente: ['Pendiente', 'Pendente'],
  Rechazada: ['Rechazada', 'Recusada'], Cancelada: ['Cancelada', 'Cancelada'],
  completed: ['Completada', 'Concluída'], pending: ['Pendiente', 'Pendente'],
  failed: ['Fallida', 'Falhou'], reversed: ['Revertida', 'Estornada'],
  Purchase: ['Compra', 'Compra'], Withdrawal: ['Retiro', 'Saque'], Transfer: ['Transferencia', 'Transferência'],
  Payment: ['Pago', 'Pagamento'], Deposit: ['Depósito', 'Depósito'], Adjustment: ['Ajuste', 'Ajuste'],
  Approved: ['Aprobada', 'Aprovada'], Declined: ['Rechazada', 'Recusada'], Pending: ['Pendiente', 'Pendente'],
  Reversed: ['Revertida', 'Estornada'], Completed: ['Completada', 'Concluída'],
  manual_review: ['Cola de revisión manual', 'Fila de revisão manual'],
  critical_review: ['Cola de revisión prioritaria', 'Fila de revisão prioritária'],
}
export function sourceLabel(value: string, locale: Locale) {
  return Object.hasOwn(labels, value) ? labels[value][locale === 'es' ? 0 : 1] : value
}

export function money(value: string | null, currency: string, locale: Locale) {
  if (value === null || value.trim() === '' || !Number.isFinite(Number(value))) return workflowCopy[locale].unavailable
  // Preserve source precision for unusually large values rather than silently rounding them.
  if (Math.abs(Number(value)) > Number.MAX_SAFE_INTEGER / 100) return `${value} ${currency}`
  try { return new Intl.NumberFormat(locale, { style: 'currency', currency, currencyDisplay: 'code' }).format(Number(value)) }
  catch { return `${value} ${currency}` }
}

export function sourceDate(value: string | null | undefined, locale: Locale) {
  if (!value || !/^\d{4}-\d{2}-\d{2}/.test(value)) return workflowCopy[locale].unavailable
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value.slice(0, 10) || Number(value.slice(0, 4)) < 1
    ? workflowCopy[locale].unavailable
    : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(date)
}
