/**
 * The client's type surface. Import from here, never from `types.generated.ts`:
 * that file is overwritten by `npm run gen:types` and carries the document root
 * (`RelayAPI`), which is an artefact of the export, not a model.
 */
export type {
  AgentStats, AssetIn, AssetOut, AssetPatch, AssetType, AuthorType,
  CategoryIn, CategoryOut, CategoryPatch, Channel, ConversationDetail,
  ConversationPatch, ConversationStatus, ConversationSummary,
  CreateNoteRequest, CreateStaffRequest, CreateWorkOrder, DayBucket,
  DeliveryStatus, DepartmentBucket, DepartmentIn, DepartmentOut,
  DepartmentPatch, DepartmentType, Direction, DraftPromptOut,
  DraftPromptStatus, GuestDetail, GuestOut, GuestThread, GuestThreadMessage,
  HourBucket, ListQuery, LocationType, LoginRequest, MembershipOut,
  MessageOut, NoteOut, NotificationOut, Overview, PreviewRequest, Priority,
  PropertySettingsOut, PropertySettingsPatch, QuickReplyIn, QuickReplyOut,
  QuickReplyPatch, RenderRequest, RenderedQuickReply, ResponseBucket, Role,
  SendMessageRequest, SessionOut, SimEvent, SimGuest, SmsConsentStatus,
  StaffPatch, StaffUserOut, StayOut, StayStatus, UnreadCount, UserOut,
  WorkOrderBrief, WorkOrderDetail, WorkOrderEventOut, WorkOrderEventType,
  WorkOrderListQuery, WorkOrderOut, WorkOrderPatch, WorkOrderPhotoKind,
  WorkOrderPhotoOut, WorkOrderPrefill, WorkOrderStatus, WorkOrderType,
} from './types.generated'
