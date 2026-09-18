export interface ChannelsTranslations {
  title: string;
  subtitle: string;
  restartBannerText: string;
  restartNow: string;
  restarting: string;
  restartGateway: string;
  gatewayNotRunning: string;
  channelsConfigured: (configured: number, total: number, envPath: string) => string;
  statusConnected: string;
  statusPendingRestart: string;
  statusGatewayStopped: string;
  statusStartupFailed: string;
  statusConfigured: string;
  statusNotConfigured: string;
  saveAndEnable: string;
  saving: string;
  cancel: string;
  test: string;
  configure: string;
  callbackUrl: string;
  nothingToSave: string;
  fixHighlightedFields: string;
  fieldRequired: (field: string) => string;
  useTelegramBot: string;
  configurePlatform: (name: string) => string;
  botFatherGuide: string;
  setupGuide: string;
  savedGatewayConnecting: (name: string) => string;
  saved: (name: string) => string;
  failedToSave: (error: string) => string;
  failedToRestart: (error: string) => string;
  gatewayRestarting: string;
}

export interface FilesTranslations {
  title: string;
  subtitle: string;
  uploadFiles: string;
  chooseFiles: string;
  dragFilesHint: string;
  newFolder: string;
  createFolder: string;
  folderName: string;
  create: string;
  deleteFile: string;
  deleteFolder: string;
  confirmDelete: (name: string) => string;
  delete: string;
  cancel: string;
  name: string;
  size: string;
  modified: string;
  actions: string;
  emptyDirectory: string;
  loadingFiles: string;
  fileUploaded: string;
  fileDeleted: string;
  folderCreated: string;
}

export interface McpTranslations {
  title: string;
  subtitle: string;
  addServer: string;
  yourServers: (count: number) => string;
  noServers: string;
  catalog: (count: number) => string;
  catalogDesc: string;
  noCatalog: string;
  restartNote: string;
  testConnection: string;
  enable: string;
  disable: string;
  delete: string;
  install: string;
  installed: string;
  installing: string;
  removeServerTitle: string;
  removeServerDesc: (name: string) => string;
  addServerTitle: string;
  name: string;
  transport: string;
  url: string;
  auth: string;
  bearerToken: string;
  command: string;
  args: string;
  environment: string;
  add: string;
  adding: string;
  connectedNoTools: string;
  toolsCount: (count: number) => string;
  connectionFailed: string;
  installTitle: (name: string) => string;
  installRequiredEnv: string;
  endpoint: string;
  runs: string;
  oauthHint: string;
}

export interface WebhooksTranslations {
  title: string;
  subtitle: string;
  newWebhook: string;
  editWebhook: string;
  deleteWebhook: string;
  confirmDelete: (name: string) => string;
  noWebhooks: string;
  name: string;
  url: string;
  secret: string;
  status: string;
  events: string;
  actions: string;
  create: string;
  save: string;
  cancel: string;
  delete: string;
}

export interface SystemPageTranslations {
  title: string;
  subtitle: string;
  doctor: string;
  operations: string;
  audit: string;
  curator: string;
  portal: string;
  backups: string;
  migration: string;
  hooks: string;
  checkpoints: string;
  credentialPool: string;
  restartGateway: string;
  cleanCache: string;
  exportDiagnostics: string;
  reloadConfig: string;
  healthy: string;
  warning: string;
  error: string;
  status: string;
}

export interface ProfileBuilderTranslations {
  title: string;
  subtitle: string;
  stepIdentity: string;
  stepModel: string;
  stepSkills: string;
  stepMcps: string;
  stepReview: string;
  profileName: string;
  profileDescription: string;
  systemPrompt: string;
  defaultModel: string;
  fallbackModel: string;
  createProfile: string;
  saveChanges: string;
  cloneFromDefault: string;
  next: string;
  back: string;
  cancel: string;
}

export interface BlueprintsTranslations {
  title: string;
  subtitle: string;
  useBlueprint: string;
  customize: string;
  preview: string;
  categoryCoding: string;
  categoryResearch: string;
  categoryOperations: string;
  categoryWriting: string;
  builtin: string;
  community: string;
  experimental: string;
}

export interface ModelPickerTranslations {
  title: string;
  searchPlaceholder: string;
  filterCapabilities: string;
  thinking: string;
  vision: string;
  toolCalling: string;
  contextWindow: string;
  selectModel: string;
  noMatches: string;
  noAuthenticatedProviders: string;
  refreshModels: string;
  persistGlobalHint: string;
  persistGlobalCheckbox: string;
  pickProviderHint: string;
  modelsCount: (count: number) => string;
}

export interface ModelInfoTranslations {
  loading: string;
  contextWindow: string;
  autoDetected: string;
  override: (auto: string) => string;
  maxOutput: string;
  tools: string;
  vision: string;
  reasoning: string;
  reasoningEffort: string;
  capabilities: string;
}

export interface SkillEditorTranslations {
  newSkill: string;
  editSkill: (name: string) => string;
  newSkillDesc: string;
  editSkillDesc: string;
  name: string;
  namePlaceholder: string;
  category: string;
  categoryPlaceholder: string;
  skillContent: string;
  save: string;
  saving: string;
  cancel: string;
  nameRequired: string;
  contentRequired: string;
}

export interface ToolsetConfigTranslations {
  active: string;
  inactive: string;
  enabledFor: (platform: string) => string;
  disabledFor: (platform: string) => string;
  noConfigurableBackends: string;
  noProvidersAvailable: string;
  runningPostSetup: string;
  runSetup: string;
  apiKeys: string;
  saveProviderSettings: string;
  saving: string;
  close: string;
}
