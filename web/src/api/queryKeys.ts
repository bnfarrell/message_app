export const qk = {
  session: ['session'] as const,

  conversations: (propertyId: string, filter: string, dept?: string | null) =>
    ['conversations', propertyId, filter, dept ?? null] as const,
  conversationsAll: (propertyId: string) => ['conversations', propertyId] as const,
  conversation: (propertyId: string, id: string) => ['conversation', propertyId, id] as const,

  workOrders: (propertyId: string, params: Record<string, string | boolean | null>) =>
    ['workOrders', propertyId, params] as const,
  workOrdersAll: (propertyId: string) => ['workOrders', propertyId] as const,
  workOrder: (propertyId: string, id: string) => ['workOrder', propertyId, id] as const,
  workOrderPrefill: (propertyId: string, conversationId: string) =>
    ['workOrderPrefill', propertyId, conversationId] as const,

  quickReplies: (propertyId: string, q?: string) => ['quickReplies', propertyId, q ?? ''] as const,
  quickRepliesAll: (propertyId: string) => ['quickReplies', propertyId] as const,
  quickReplyVariables: (propertyId: string) => ['quickReplyVariables', propertyId] as const,
  quickReplyPreview: (propertyId: string, body: string) =>
    ['quickReplyPreview', propertyId, body] as const,
  assets: (propertyId: string) => ['assets', propertyId] as const,
  assetsAll: (propertyId: string) => ['assets', propertyId] as const,
  categories: (propertyId: string) => ['categories', propertyId] as const,
  categoriesAll: (propertyId: string) => ['categories', propertyId] as const,
  departments: (propertyId: string) => ['departments', propertyId] as const,
  propertySettings: (propertyId: string) => ['propertySettings', propertyId] as const,
  staff: (propertyId: string) => ['staff', propertyId] as const,
  staffAll: (propertyId: string) => ['staff', propertyId] as const,
  guest: (propertyId: string, id: string) => ['guest', propertyId, id] as const,

  notifications: (propertyId: string, unreadOnly: boolean) =>
    ['notifications', propertyId, unreadOnly] as const,
  notificationsAll: (propertyId: string) => ['notifications', propertyId] as const,
  unreadCount: (propertyId: string) => ['unreadCount', propertyId] as const,

  staffConversationsAll: (propertyId: string) => ['staffConversations', propertyId] as const,
  staffConversation: (propertyId: string, id: string) =>
    ['staffConversation', propertyId, id] as const,
  staffDirectory: (propertyId: string) => ['staffDirectory', propertyId] as const,

  logFeed: (propertyId: string, params: Record<string, string | boolean | null>) =>
    ['logFeed', propertyId, params] as const,
  logFeedAll: (propertyId: string) => ['logFeed', propertyId] as const,
  logEntry: (propertyId: string, id: string) => ['logEntry', propertyId, id] as const,
  logMentionables: (propertyId: string) => ['logMentionables', propertyId] as const,
  logTemplatesAll: (propertyId: string) => ['logTemplates', propertyId] as const,
  logTemplatesUsable: (propertyId: string) => ['logTemplates', propertyId, 'usable'] as const,
  logTemplatesAdmin: (propertyId: string) => ['logTemplates', propertyId, 'admin'] as const,

  pmAll: (propertyId: string) => ['pm', propertyId] as const,
  pmUnits: (propertyId: string, params: Record<string, string | boolean | null>) =>
    ['pm', propertyId, 'units', params] as const,
  pmUnitsAll: (propertyId: string) => ['pm', propertyId, 'units'] as const,
  pmTemplates: (propertyId: string) => ['pm', propertyId, 'templates'] as const,
  pmSweep: (propertyId: string, params: Record<string, string | null>) =>
    ['pm', propertyId, 'sweep', params] as const,
  pmSweepAll: (propertyId: string) => ['pm', propertyId, 'sweep'] as const,
  pmCycles: (propertyId: string, templateId: string) =>
    ['pm', propertyId, 'cycles', templateId] as const,
  pmCyclesAll: (propertyId: string) => ['pm', propertyId, 'cycles'] as const,
  pmRun: (propertyId: string, id: string) => ['pm', propertyId, 'run', id] as const,
  pmInspections: (propertyId: string, params: Record<string, string | null>) =>
    ['pm', propertyId, 'inspections', params] as const,
  pmInspectionsAll: (propertyId: string) => ['pm', propertyId, 'inspections'] as const,
  pmCompliance: (propertyId: string, from: string, to: string) =>
    ['pm', propertyId, 'compliance', from, to] as const,

  ckAll: (propertyId: string) => ['ck', propertyId] as const,
  ckTemplates: (propertyId: string) => ['ck', propertyId, 'templates'] as const,
  ckInstances: (propertyId: string, params: Record<string, string | null>) =>
    ['ck', propertyId, 'instances', params] as const,
  ckInstancesAll: (propertyId: string) => ['ck', propertyId, 'instances'] as const,
  ckInstance: (propertyId: string, id: string) => ['ck', propertyId, 'instance', id] as const,
  ckMissedAll: (propertyId: string) => ['ck', propertyId, 'missed'] as const,
  ckLibrary: (propertyId: string) => ['ck', propertyId, 'library'] as const,

  hkAll: (propertyId: string) => ['hk', propertyId] as const,
  hkBoardAll: (propertyId: string) => ['hk', propertyId, 'board'] as const,
  hkMyRoomsAll: (propertyId: string) => ['hk', propertyId, 'my-rooms'] as const,
  hkInspectionsAll: (propertyId: string) => ['hk', propertyId, 'inspections'] as const,
  hkRoom: (propertyId: string, id: string) => ['hk', propertyId, 'room', id] as const,

  analyticsOverview: (propertyId: string, from: string, to: string) =>
    ['analytics', 'overview', propertyId, from, to] as const,
  analyticsAgents: (propertyId: string, from: string, to: string) =>
    ['analytics', 'agents', propertyId, from, to] as const,

  simGuests: ['sim', 'guests'] as const,
  simThread: (propertyId: string, phone: string) => ['sim', 'thread', propertyId, phone] as const,
  simEvents: ['sim', 'events'] as const,
}
