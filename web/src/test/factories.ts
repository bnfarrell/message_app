import type {
  ConversationDetail,
  ConversationSummary,
  DepartmentOut,
  DraftPromptOut,
  GuestOut,
  MessageOut,
  NoteOut,
  NotificationOut,
  QuickReplyOut,
  AssetOut,
  StaffUserOut,
  StayOut,
  WorkOrderDetail,
  WorkOrderOut,
} from '../api/types'

export function aGuest(over: Partial<GuestOut> = {}): GuestOut {
  return {
    id: 'g-1',
    phoneE164: '+15551234567',
    firstName: 'Sarah',
    lastName: 'Chen',
    email: null,
    loyaltyTier: 'gold',
    notesSummary: null,
    smsConsentStatus: 'opted_in',
    vip: false,
    ...over,
  }
}

export function aStay(over: Partial<StayOut> = {}): StayOut {
  return {
    id: 's-1',
    roomNumber: '412',
    roomType: 'King',
    status: 'checked_in',
    arrivalDate: '2026-09-09',
    departureDate: '2026-09-12',
    adults: 2,
    children: 0,
    stayCount: 4,
    isReturnGuest: true,
    ...over,
  }
}

export function aConversation(over: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 'c-1',
    status: 'open',
    channelPrimary: 'sms',
    guest: aGuest(),
    roomNumber: '412',
    assignedUserId: null,
    assignedDepartmentId: null,
    lastMessagePreview: "The AC in our room isn't working at all",
    lastGuestMessageAt: '2026-09-10T18:41:00Z',
    lastStaffMessageAt: null,
    slaDueAt: '2026-09-10T18:56:00Z',
    snoozedUntil: null,
    openWorkOrderCount: 0,
    unanswered: true,
    ...over,
  }
}

export function aMessage(over: Partial<MessageOut> = {}): MessageOut {
  return {
    id: 'm-1',
    conversationId: 'c-1',
    direction: 'inbound',
    channel: 'sms',
    authorType: 'guest',
    authorUserId: null,
    body: "The AC in our room isn't working at all",
    deliveryStatus: 'delivered',
    sentAt: '2026-09-10T18:41:00Z',
    deliveredAt: '2026-09-10T18:41:02Z',
    providerErrorCode: null,
    providerErrorMessage: null,
    digitalAssetId: null,
    redacted: false,
    ...over,
  }
}

export function aNote(over: Partial<NoteOut> = {}): NoteOut {
  return {
    id: 'n-1',
    authorUserId: 'u-ava',
    authorName: 'Ava',
    body: 'Guest is Gold, 4th stay.',
    mentions: [],
    createdAt: '2026-09-10T18:43:00Z',
    ...over,
  }
}

export function aDraftPrompt(over: Partial<DraftPromptOut> = {}): DraftPromptOut {
  return {
    id: 'd-1',
    workOrderId: 'w-204',
    workOrderTitle: 'AC not cooling',
    body: 'Hi Sarah — engineering has repaired the AC in 412 and it is cooling now.',
    status: 'pending',
    createdAt: '2026-09-10T18:56:00Z',
    ...over,
  }
}

export function aConversationDetail(over: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id: 'c-1',
    status: 'open',
    channelPrimary: 'sms',
    guest: aGuest(),
    stay: aStay(),
    assignedUserId: null,
    assignedDepartmentId: null,
    resolutionCategoryId: null,
    lastGuestMessageAt: '2026-09-10T18:41:00Z',
    lastStaffMessageAt: null,
    slaDueAt: '2026-09-10T18:56:00Z',
    snoozedUntil: null,
    archivedAt: null,
    firstResponseSeconds: null,
    messages: [aMessage()],
    notes: [],
    workOrders: [],
    draftPrompts: [],
    ...over,
  }
}

export function aWorkOrder(over: Partial<WorkOrderOut> = {}): WorkOrderOut {
  return {
    id: 'w-204',
    title: 'AC not cooling',
    description: 'Guest reports the AC in 412 is not working.',
    type: 'maintenance',
    status: 'open',
    priority: 'urgent',
    locationType: 'room',
    locationRef: '412',
    departmentId: 'dept-eng',
    assignedUserId: null,
    reportedByUserId: 'u-ava',
    sourceConversationId: 'c-1',
    sourceMessageId: 'm-1',
    dueAt: null,
    acknowledgedAt: null,
    startedAt: null,
    completedAt: null,
    verifiedAt: null,
    guestNotifiedAt: null,
    createdAt: '2026-09-10T18:42:00Z',
    updatedAt: '2026-09-10T18:42:00Z',
    ...over,
  }
}

export function aWorkOrderDetail(over: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return { ...aWorkOrder(), events: [], photos: [], guestName: 'Sarah Chen', roomNumber: '412', ...over }
}

export function aDepartment(over: Partial<DepartmentOut> = {}): DepartmentOut {
  return { id: 'dept-eng', name: 'Engineering', type: 'engineering', escalationMinutes: 15, active: true, ...over }
}

export function aStaffUser(over: Partial<StaffUserOut> = {}): StaffUserOut {
  return {
    id: 'u-ava',
    email: 'ava@hvh.test',
    firstName: 'Ava',
    lastName: 'Nolan',
    role: 'agent',
    departmentId: 'dept-fd',
    avatarUrl: null,
    status: 'active',
    ...over,
  }
}

export function aQuickReply(over: Partial<QuickReplyOut> = {}): QuickReplyOut {
  return {
    id: 'q-1',
    shortcut: '/wifi',
    title: 'WiFi details',
    body: 'Hi {{guest_first_name}} — the network is Harbourview-Guest, no password needed.',
    departmentId: null,
    category: null,
    locale: 'en',
    active: true,
    usageCount: 212,
    ...over,
  }
}

export function aAsset(over: Partial<AssetOut> = {}): AssetOut {
  return {
    id: 'a-1',
    name: 'WiFi card',
    type: 'file',
    url: 'https://example.test/wifi.pdf',
    shortCode: 'wifi1',
    description: null,
    thumbnailUrl: null,
    category: null,
    departmentId: null,
    validFrom: null,
    validUntil: null,
    sendCount: 12,
    active: true,
    ...over,
  }
}

export function aNotification(over: Partial<NotificationOut> = {}): NotificationOut {
  return {
    id: 'nt-1',
    type: 'sla.breach',
    title: 'SLA breached in 412',
    body: 'Sarah Chen has been waiting 16 minutes.',
    entityType: 'conversation',
    entityId: 'c-1',
    readAt: null,
    createdAt: '2026-09-10T18:57:00Z',
    ...over,
  }
}
