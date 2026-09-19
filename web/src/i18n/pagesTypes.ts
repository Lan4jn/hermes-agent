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
  whatsappPairWithQr: string;
  whatsappExistingConfigured: string;
  whatsappMode: string;
  whatsappBot: string;
  whatsappSelfChat: string;
  whatsappAllowedNumbers: string;
  whatsappAllowedPlaceholder: string;
  whatsappScanHint: string;
  whatsappQrNotBrowser: string;
  whatsappWaitingQr: string;
  whatsappSaveAndRestart: string;
  whatsappLinkedAs: (account: string) => string;
  whatsappDeviceLinked: string;
  whatsappOpenChatLink: string;
  whatsappExpired: string;
  whatsappStillWaiting: (error: string) => string;
  whatsappSavedRestarting: string;
  whatsappSavedRestartFailed: (error?: string) => string;
  telegramTitle: string;
  telegramSubtitle: string;
  telegramQuickSetup: string;
  telegramRecommended: string;
  telegramQuickSetupDesc: string;
  telegramCreateWithQr: string;
  telegramUseOwnBot: string;
  telegramUseOwnBotDesc: string;
  telegramManualSetup: string;
  telegramAlreadyConfigured: string;
  telegramFinishOrCancel: string;
  telegramAllowedUsers: string;
  telegramOwnerDetected: string;
  telegramAddAtLeastOne: string;
  telegramUserIdPlaceholder: string;
  telegramAdd: string;
  telegramOpenTelegram: string;
  telegramWaiting: string;
  telegramNumericError: string;
  telegramExpired: string;
  telegramStillWaiting: (error: string) => string;
  telegramSavedRestarting: string;
  telegramSavedRestartFailed: (error?: string) => string;
  telegramConnectBotIntro: string;
  telegramStep1: string;
  telegramStep2: string;
  telegramStep3: string;
  telegramOpenBotFather: string;
  telegramFindUserId: string;
  telegramAllowedUsersHint: string;
  gatewayRestartFailedManual: (exitCode: number) => string;
  ready: string;
  savingEllipsis: string;
  telegramFindUserIdTitle: string;
  allowedUsersPairingHint: string;
  redactedPlaceholder: string;
  enablePlatform: (name: string) => string;
  starting: string;
  whatsappLinkedHelp: string;
  whatsappPreparingHelp: string;
  whatsappStartingHelp: string;
  whatsappScanInstruction: string;
  whatsappLinkedAccountDetail: string;
  whatsappLinkedAccountDetailGeneric: string;
  whatsappMessageInstructionSelf: string;
  whatsappMessageInstructionDedicated: string;
  whatsappPairingKeepSaved: string;
  whatsappPairingSelfAllow: string;
  whatsappPairingCodeHint: string;
  expired: string;
  whatsappSaveAndRestartInstruction: string;
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
  refreshFiles: string;
  path: string;
  go: string;
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
  authWithOAuth: string;
  authenticate: string;
  installsFrom: string;
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
  description: string;
  deliverTo: string;
  deliverOnly: string;
  prompt: string;
  url: string;
  secret: string;
  status: string;
  events: string;
  actions: string;
  create: string;
  creating: string;
  save: string;
  cancel: string;
  delete: string;
  enable: string;
  disable: string;
  deliverOnlyBadge: string;
  disabledBadge: string;
  receiverDisabled: string;
  receiverDisabledDesc: string;
  enableWebhooks: string;
  enabling: string;
  subscriptions: (count: number) => string;
  subscriptionsHelp: string;
  allEvents: string;
  createdSecretHint: string;
  secretShownOnce: string;
  namePlaceholder: string;
  promptPlaceholder: string;
  descPlaceholder: string;
  eventsPlaceholder: string;
  copy: string;
  logTarget: string;
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

  // Stats
  cores: (count: number) => string;
  memory: string;
  disk: string;
  uptime: string;
  loadAvg: string;
  psutilNotice: string;
  checkForUpdates: string;
  updateWithCommand: (command: string) => string;
  updateAvailable: string;
  behind: (count: number) => string;
  latest: string;
  statOs: string;
  statArch: string;
  statHost: string;
  closeLog: string;
  timeoutSeconds: string;
  runningBadge: string;
  doneBadge: string;

  // Portal
  nousPortal: string;
  loggedIn: string;
  notLoggedIn: string;
  inferenceProvider: (provider: string) => string;
  manageSubscription: string;
  toolGatewayRouting: string;
  portalLoginHint: string;

  // Curator
  skillCurator: string;
  paused: string;
  active: string;
  disabled: string;
  everyHours: (hours: number) => string;
  lastRun: (time: string) => string;
  neverRun: string;
  pause: string;
  resume: string;
  runNow: string;

  // Gateway
  gateway: string;
  running: string;
  stopped: string;
  start: string;
  restart: string;
  stop: string;
  migrateToMultiplex: string;
  multiplexNotice: string;
  fixBlockersFirst: string;

  // Memory
  externalProvider: string;
  builtinOnly: string;
  changeInPlugins: string;
  providerSetup: string;
  configureInPlugins: string;
  providerMissingWarning: string;
  builtinFiles: (memory: string, user: string) => string;
  resetMemory: string;
  resetUser: string;
  resetAll: string;

  // Credential pool
  provider: string;
  apiKey: string;
  label: string;
  optional: string;
  addKey: string;
  noPooledCreds: string;
  removeCredential: string;

  // Operations
  openConsole: string;
  runDoctor: string;
  securityAudit: string;
  updateSkills: string;
  promptSize: string;
  supportDump: string;
  migrateConfig: string;

  // Backups
  fullBackup: string;
  createBackup: string;
  downloadBackup: string;
  noBackupYet: string;
  restoreUpload: string;
  chooseRestoreZip: string;
  noArchiveSelected: string;
  restoreUploadBtn: string;
  restorePath: string;
  restorePathBtn: string;

  // Share debug
  shareDebugReport: string;
  shareDebugDesc: string;
  generateShareLink: string;
  uploading: string;
  redactNotice: string;
  uploaded: string;
  redacted: string;
  notRedacted: string;
  autoDeletesIn: (hours: number) => string;
  copyAll: string;
  copyLink: (label: string) => string;
  someLogsFailedUpload: (errors: string) => string;

  // Checkpoints
  sessionsCount: (count: number, bytes: string) => string;
  pruneCheckpoints: string;
  noCheckpoints: string;

  // Hooks
  shellHooks: string;
  newHook: string;
  noShellHooks: string;
  matcher: (matcher: string) => string;
  notExecutable: string;
  allowed: string;
  notApproved: string;
  removeHook: string;

  // Modals & Dialogs
  resetMemoryTitle: (file: string) => string;
  resetMemoryDesc: (file: string) => string;
  resetAllMemoryTitle: string;
  resetAllMemoryDesc: string;
  deleteCredTitle: string;
  deleteCredDesc: string;
  pruneCheckpointsTitle: string;
  pruneCheckpointsDesc: string;
  removeHookTitle: string;
  removeHookDesc: string;
  restartTitle: string;
  restartDesc: string;
  updateConfirmTitle: string;
  updateConfirmDesc: string;
  updateNow: string;
  restartNow: string;
  prune: string;
  reset: string;
  remove: string;
  cancel: string;
  restoreFullTitle: string;
  restoreFullDesc: (target: string) => string;
  restore: string;

  // Hook modal
  newHookTitle: string;
  newHookDesc: string;
  eventLabel: string;
  eventPlaceholder: string;
  commandLabel: string;
  commandPlaceholder: string;
  matcherLabel: string;
  matcherPlaceholder: string;
  matcherHint: string;
  allowLabel: string;
  createHook: string;

  // Operation modal
  runningOp: (op: string) => string;
  opOutput: string;
  close: string;

  // Toasts
  gatewayActionFailed: (action: string, error: string) => string;
  gatewayActionStarted: (action: string) => string;
  gatewayActionSuccess: (action: string) => string;
  opFailed: (op: string, error: string) => string;
  credAdded: string;
  credAddFailed: (error: string) => string;
  credRemoved: string;
  credRemoveFailed: (error: string) => string;
  memoryResetSuccess: (target: string) => string;
  memoryResetFailed: (target: string, error: string) => string;
  checkpointsPruned: string;
  checkpointsPruneFailed: (error: string) => string;
  hookCreated: string;
  hookCreateFailed: (error: string) => string;
  hookRemoved: string;
  hookRemoveFailed: (error: string) => string;
  curatorToggled: (state: string) => string;
  curatorToggleFailed: (error: string) => string;
  copiedToClipboard: string;
  failedToCopy: string;
  backupCreated: (name: string) => string;
  backupCreateFailed: (error: string) => string;
  backupDownloaded: string;
  backupDownloadFailed: (error: string) => string;
  backupImportSuccess: string;
  backupImportFailed: (error: string) => string;
  debugShareSuccess: string;
  debugShareFailed: (error: string) => string;
  migrateStarted: string;
  migrateFailed: (error: string) => string;
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
  profileDescPlaceholder: string;
  pickModelDesc: string;
  filterModelsPlaceholder: string;
  loadingModels: string;
  useDefault: string;
  startFromFullBundle: string;
  chooseSkillsDesc: string;
  filterSkillsPlaceholder: string;
  loadingSkills: string;
  addFromSkillsHub: string;
  hubSkills: string;
  searchHubPlaceholder: string;
  searching: string;
  search: string;
  add: string;
  mcpServers: string;
  mcpServersDesc: string;
  configured: string;
  addServer: string;
  serverName: string;
  transport: string;
  authentication: string;
  bearerToken: string;
  command: string;
  args: string;
  environment: string;
  reviewName: string;
  reviewDescription: string;
  reviewModel: string;
  reviewSkills: string;
  reviewMcpServers: string;
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
  noBlueprints: string;
  loadingBlueprints: string;
  loadError: string;
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
  expensiveWarningTitle: string;
  switchAnyway: string;
  savesToConfigYaml: string;
  currentLabel: string;
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

export interface ModelsPageTranslations {
  title: string;
  subtitle: string;
  changeMainModel: string;
  manageMoa: string;
  currentMainModel: string;
  auxiliaryTasksTitle: string;
  auxiliaryTasksDesc: string;
  moaTitle: string;
  moaDesc: string;
  moaEnabled: string;
  moaDisabled: string;
  proposeMoaConfig: string;
  analyticsTitle: string;
  defaultModel: (model: string) => string;
  removeOverride: string;
  expensiveWarning: string;
  useAs: string;
  mainModel: string;
  current: string;
  auxiliaryTask: string;
  allAuxiliaryTasks: string;
  change: string;
  configure: string;
  configureMoaTitle: string;
  moaPresetsHelp: string;
  setDefault: string;
  deletePreset: string;
  newPresetPlaceholder: string;
  addPreset: string;
  defaultLabel: (name: string) => string;
  referenceModels: string;
  addReferenceModel: string;
  aggregator: string;
  remove: string;
  selectMoaModelTitle: string;
  recursiveMoaError: string;
  resetAllToAuto: string;
  auxiliaryTasksModalDesc: string;
  override: string;
  resetAuxiliaryConfirmTitle: string;
  resetAuxiliaryConfirmDesc: string;
  resetAll: string;
  expensiveWarningTitle: string;
  switchAnyway: string;
  tokenAnalyticsHiddenNotice: string;
}

export interface SkillsPageTranslations {
  title: string;
  subtitle: string;
  learnSkill: string;
  newSkill: string;
  searchHub: string;
  installed: string;
  hub: string;
  searchPlaceholder: string;
  noSkillsInstalled: string;
  noSkillsMatch: string;
  install: string;
  installing: string;
  installedBadge: string;
  uninstall: string;
  uninstalling: string;
  update: string;
  updating: string;
  clean: string;
  flagged: string;
  critical: string;
  confirmUninstallTitle: (name: string) => string;
  confirmUninstallDesc: string;
  learnSkillTitle: string;
  learnSkillDesc: string;
  learnUrlPlaceholder: string;
  teach: string;
  learning: string;
  configure: string;
  connectingHubs: string;
  searchHubPlaceholder: string;
  doneBadge: string;
  runningBadge: string;
  editSkillMd: string;
  editSkill: string;
}

export interface PairingTranslations {
  title: string;
  subtitle: string;
  clearPending: string;
  clearPendingConfirm: string;
  clearedPending: (count: number) => string;
  revokeAccessTitle: string;
  revokeAccessDesc: (user: string) => string;
  revoke: string;
  revoked: (user: string) => string;
  pendingRequests: (count: number) => string;
  noPendingRequests: string;
  approvedUsers: (count: number) => string;
  noApprovedUsers: string;
  approve: string;
  approved: (user: string) => string;
  minutesAgo: (minutes: number) => string;
  loadFailed: string;
  missingRequest: string;
}
