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

  analyticsOverview: (propertyId: string, from: string, to: string) =>
    ['analytics', 'overview', propertyId, from, to] as const,
  analyticsAgents: (propertyId: string, from: string, to: string) =>
    ['analytics', 'agents', propertyId, from, to] as const,

  simGuests: ['sim', 'guests'] as const,
  simThread: (propertyId: string, phone: string) => ['sim', 'thread', propertyId, phone] as const,
  simEvents: ['sim', 'events'] as const,
}
