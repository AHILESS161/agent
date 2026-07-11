import type {
  User, Client, Application, NiceClassSuggestion, LegalReview,
  LegalFinding, ConflictSearchResult, RecommendationMemo, DocumentPackage,
  Notification, AuditLog, CompletenessCheck, StatusHistoryEntry, GoodsServicesItem,
} from "@shared/schema";

// ========== USERS ==========
export const mockUsers: User[] = [
  { id: 1, email: "admin@demo.ru", fullName: "Петров Алексей Иванович", role: "admin", isActive: true },
  { id: 2, email: "lawyer@demo.ru", fullName: "Козлова Елена Сергеевна", role: "lawyer", isActive: true },
  { id: 3, email: "manager@demo.ru", fullName: "Сидоров Дмитрий Олегович", role: "manager", isActive: true },
  { id: 4, email: "client@demo.ru", fullName: "Иванова Мария Петровна", role: "client", isActive: true },
  { id: 5, email: "lawyer2@demo.ru", fullName: "Новикова Анна Владимировна", role: "lawyer", isActive: true },
];

// ========== CLIENTS ==========
export const mockClients: Client[] = [
  {
    id: 1, type: "company", fullNameOrCompanyName: "ООО \"ТехноИнновация\"", shortName: "ТехноИнновация",
    contactPerson: "Иванова Мария Петровна", email: "info@technoinnovation.ru", phone: "+7 (495) 123-45-67",
    address: "г. Москва, ул. Тверская, д. 12, оф. 401", inn: "7712345678", ogrnOrOgrnip: "1177746123456",
    createdAt: "2025-09-15T10:00:00Z",
  },
  {
    id: 2, type: "company", fullNameOrCompanyName: "АО \"Сибирские Сладости\"", shortName: "СибСладости",
    contactPerson: "Кузнецов Павел Николаевич", email: "office@sibsweets.ru", phone: "+7 (383) 234-56-78",
    address: "г. Новосибирск, пр. Красный, д. 54", inn: "5401234567", ogrnOrOgrnip: "1175401234567",
    createdAt: "2025-10-02T14:30:00Z",
  },
  {
    id: 3, type: "individual", fullNameOrCompanyName: "Волков Артём Викторович", shortName: "Волков А.В.",
    contactPerson: "Волков Артём Викторович", email: "volkov.art@mail.ru", phone: "+7 (916) 345-67-89",
    address: "г. Москва, ул. Ленина, д. 5, кв. 12", inn: "772012345678", ogrnOrOgrnip: "",
    createdAt: "2025-11-10T09:00:00Z",
  },
  {
    id: 4, type: "sole_proprietor", fullNameOrCompanyName: "ИП Смирнова Ольга Андреевна", shortName: "ИП Смирнова",
    contactPerson: "Смирнова Ольга Андреевна", email: "smirnova.ip@yandex.ru", phone: "+7 (926) 456-78-90",
    address: "г. Санкт-Петербург, Невский пр., д. 88", inn: "780123456789", ogrnOrOgrnip: "318784700012345",
    createdAt: "2025-12-01T11:00:00Z",
  },
  {
    id: 5, type: "company", fullNameOrCompanyName: "ООО \"Зелёная Долина\"", shortName: "Зелёная Долина",
    contactPerson: "Морозов Игорь Дмитриевич", email: "gd@greenvale.ru", phone: "+7 (812) 567-89-01",
    address: "г. Санкт-Петербург, ул. Садовая, д. 30", inn: "7801234567", ogrnOrOgrnip: "1187847012345",
    createdAt: "2026-01-15T16:00:00Z",
  },
];

// ========== APPLICATIONS ==========
export const mockApplications: Application[] = [
  {
    id: 1, clientId: 1, status: "awaiting_lawyer_review", markType: "word", markName: "ТЕХНОПАРК",
    markText: "ТЕХНОПАРК", colorsClaimed: "", transliteration: "TEKHNOPARK", translation: "Technopark",
    descriptionOfMark: "Словесное обозначение, выполненное стандартным шрифтом заглавными буквами русского алфавита",
    businessDescription: "Разработка и продажа программного обеспечения, IT-консалтинг, облачные технологии",
    goodsServicesRaw: "Программное обеспечение, облачные вычисления, IT-консалтинг, разработка мобильных приложений",
    territory: "Российская Федерация", priorityClaim: "", notes: "Срочная регистрация",
    assigneeId: 2, createdAt: "2026-01-20T10:30:00Z", updatedAt: "2026-03-15T14:00:00Z",
  },
  {
    id: 2, clientId: 2, status: "conflict_search_running", markType: "combined", markName: "СИБИРСКИЙ МЁД",
    markText: "СИБИРСКИЙ МЁД", colorsClaimed: "Золотой, коричневый, белый",
    transliteration: "SIBIRSKIY MYOD", translation: "Siberian Honey",
    descriptionOfMark: "Комбинированное обозначение: стилизованное изображение медведя с сотами, с текстом «СИБИРСКИЙ МЁД»",
    businessDescription: "Производство и продажа натурального мёда и продуктов пчеловодства",
    goodsServicesRaw: "Мёд натуральный, продукты пчеловодства, прополис, пыльца, маточное молочко, медовые напитки",
    territory: "Российская Федерация", priorityClaim: "", notes: "",
    assigneeId: 2, createdAt: "2026-02-01T09:00:00Z", updatedAt: "2026-03-20T11:30:00Z",
  },
  {
    id: 3, clientId: 3, status: "draft", markType: "figurative", markName: "ART WAVE",
    markText: "", colorsClaimed: "Синий, фиолетовый", transliteration: "", translation: "Волна искусства",
    descriptionOfMark: "Абстрактное изображение волны в стиле модерн",
    businessDescription: "Художественная галерея, продажа предметов искусства, организация выставок",
    goodsServicesRaw: "Произведения искусства, организация выставок, галерейная деятельность",
    territory: "Российская Федерация", priorityClaim: "", notes: "Клиент ещё не предоставил все данные",
    assigneeId: undefined, createdAt: "2026-03-01T15:00:00Z", updatedAt: "2026-03-01T15:00:00Z",
  },
  {
    id: 4, clientId: 4, status: "recommendation_ready", markType: "word", markName: "ЧИСТЫЙ ДОМ",
    markText: "ЧИСТЫЙ ДОМ", colorsClaimed: "", transliteration: "CHISTYY DOM", translation: "Clean Home",
    descriptionOfMark: "Словесное обозначение стандартным шрифтом",
    businessDescription: "Клининговые услуги для дома и офиса, продажа моющих средств",
    goodsServicesRaw: "Клининговые услуги, средства для уборки, моющие средства, дезинфекция помещений",
    territory: "Российская Федерация", priorityClaim: "", notes: "",
    assigneeId: 2, createdAt: "2026-02-10T12:00:00Z", updatedAt: "2026-03-18T16:45:00Z",
  },
  {
    id: 5, clientId: 5, status: "completed", markType: "combined", markName: "ЗЕЛЁНАЯ ДОЛИНА",
    markText: "ЗЕЛЁНАЯ ДОЛИНА", colorsClaimed: "Зелёный, белый",
    transliteration: "ZELYONAYA DOLINA", translation: "Green Valley",
    descriptionOfMark: "Комбинированное обозначение: стилизованный ландшафт с текстом",
    businessDescription: "Фермерское хозяйство, производство экологически чистых продуктов",
    goodsServicesRaw: "Овощи, фрукты, молочные продукты, экологические продукты питания",
    territory: "Российская Федерация", priorityClaim: "", notes: "Успешно зарегистрирован",
    assigneeId: 5, createdAt: "2025-06-15T08:00:00Z", updatedAt: "2026-01-10T10:00:00Z",
  },
  {
    id: 6, clientId: 1, status: "submitted", markType: "word", markName: "ЦИФРОВОЙ ЩИТЪ",
    markText: "ЦИФРОВОЙ ЩИТЪ", colorsClaimed: "",
    transliteration: "TSIFROVOY SHCHIT", translation: "Digital Shield",
    descriptionOfMark: "Словесное обозначение с использованием буквы Ъ",
    businessDescription: "Кибербезопасность, защита данных, IT-инфраструктура",
    goodsServicesRaw: "Услуги кибербезопасности, защита данных, антивирусное ПО, аудит безопасности",
    territory: "Российская Федерация", priorityClaim: "", notes: "",
    assigneeId: 2, createdAt: "2025-11-01T13:00:00Z", updatedAt: "2026-02-28T09:00:00Z",
  },
  {
    id: 7, clientId: 2, status: "rejected", markType: "word", markName: "НАТУРАЛЬНЫЙ",
    markText: "НАТУРАЛЬНЫЙ", colorsClaimed: "", transliteration: "NATURALNYY", translation: "Natural",
    descriptionOfMark: "Словесное обозначение, одно слово",
    businessDescription: "Продажа натуральных продуктов питания",
    goodsServicesRaw: "Натуральные продукты, органические товары",
    territory: "Российская Федерация", priorityClaim: "", notes: "Отклонено: описательный характер",
    assigneeId: 5, createdAt: "2025-08-20T10:00:00Z", updatedAt: "2026-01-05T15:30:00Z",
  },
  {
    id: 8, clientId: 4, status: "awaiting_client_data", markType: "combined", markName: "БЛЕСК ПЛЮС",
    markText: "БЛЕСК ПЛЮС", colorsClaimed: "Голубой, серебристый",
    transliteration: "BLESK PLYUS", translation: "Shine Plus",
    descriptionOfMark: "Комбинированное обозначение: стилизованная звёздочка с текстом",
    businessDescription: "Расширение линейки клининговых услуг, премиум-сегмент",
    goodsServicesRaw: "Премиум клининг, химчистка, реставрация мебели",
    territory: "Российская Федерация", priorityClaim: "", notes: "Ожидаем скан логотипа от клиента",
    assigneeId: 3, createdAt: "2026-03-10T08:00:00Z", updatedAt: "2026-03-25T12:00:00Z",
  },
];

// ========== GOODS/SERVICES ITEMS ==========
export const mockGoodsServicesItems: GoodsServicesItem[] = [
  { id: 1, applicationId: 1, rawText: "Программное обеспечение", normalizedText: "Программное обеспечение для обработки данных", proposedClass: 9, approvedClass: 9, source: "ai" },
  { id: 2, applicationId: 1, rawText: "Облачные вычисления", normalizedText: "Предоставление облачных вычислительных сервисов", proposedClass: 42, approvedClass: 42, source: "ai" },
  { id: 3, applicationId: 1, rawText: "IT-консалтинг", normalizedText: "Консультационные услуги в области информационных технологий", proposedClass: 42, approvedClass: null, source: "ai" },
  { id: 4, applicationId: 2, rawText: "Мёд натуральный", normalizedText: "Мёд", proposedClass: 30, approvedClass: 30, source: "ai" },
  { id: 5, applicationId: 2, rawText: "Продукты пчеловодства", normalizedText: "Продукты пчеловодства, а именно прополис", proposedClass: 30, approvedClass: null, source: "ai" },
];

// ========== NICE CLASS SUGGESTIONS ==========
export const mockNiceClassSuggestions: NiceClassSuggestion[] = [
  {
    id: 1, applicationId: 1, classNumber: 9, classDescription: "Научные, исследовательские, навигационные приборы и инструменты; программное обеспечение",
    rationale: "Основной продукт заявителя — программное обеспечение, которое прямо охраняется в классе 9",
    confidence: 0.95, category: "primary", risksIfOmitted: "Потеря охраны основного продукта", risksIfIncluded: "Минимальные", approved: true,
  },
  {
    id: 2, applicationId: 1, classNumber: 42, classDescription: "Научные и технологические услуги; проектирование и разработка программного обеспечения",
    rationale: "IT-консалтинг и облачные услуги относятся к классу 42",
    confidence: 0.92, category: "primary", risksIfOmitted: "Потеря охраны сервисной составляющей", risksIfIncluded: "Минимальные", approved: true,
  },
  {
    id: 3, applicationId: 1, classNumber: 35, classDescription: "Реклама; управление бизнесом; административные функции",
    rationale: "Возможная розничная торговля ПО через интернет",
    confidence: 0.55, category: "borderline", risksIfOmitted: "Средние — конкуренты могут зарегистрировать", risksIfIncluded: "Расширение объёма пошлин", approved: null,
  },
  {
    id: 4, applicationId: 2, classNumber: 30, classDescription: "Кофе, чай, какао; мёд; кондитерские изделия",
    rationale: "Мёд — основной товар заявителя, прямо указан в классе 30",
    confidence: 0.98, category: "primary", risksIfOmitted: "Критическая потеря охраны основного товара", risksIfIncluded: "Минимальные", approved: true,
  },
  {
    id: 5, applicationId: 2, classNumber: 5, classDescription: "Фармацевтические препараты; диетические вещества для медицинских целей",
    rationale: "Прополис и маточное молочко могут быть биологически активными добавками",
    confidence: 0.60, category: "secondary", risksIfOmitted: "Конкуренты могут использовать обозначение для БАДов", risksIfIncluded: "Дополнительные пошлины", approved: null,
  },
  {
    id: 6, applicationId: 4, classNumber: 37, classDescription: "Строительство; ремонт; установочные работы",
    rationale: "Клининговые услуги включены в класс 37",
    confidence: 0.93, category: "primary", risksIfOmitted: "Потеря охраны основных услуг", risksIfIncluded: "Минимальные", approved: true,
  },
  {
    id: 7, applicationId: 4, classNumber: 3, classDescription: "Моющие и чистящие средства",
    rationale: "Продажа собственных моющих средств",
    confidence: 0.85, category: "primary", risksIfOmitted: "Потеря охраны товарной линейки", risksIfIncluded: "Минимальные", approved: null,
  },
];

// ========== LEGAL REVIEWS ==========
export const mockLegalReviews: LegalReview[] = [
  {
    id: 1, applicationId: 1, reviewType: "precheck",
    absoluteGroundsSummary: "Обозначение «ТЕХНОПАРК» может быть признано описательным в отношении IT-услуг. Статья 1483 ГК РФ, п.1, пп.3 — обозначения, характеризующие товары.",
    relativeGroundsSummary: "Обнаружено 2 сходных знака в классах 9 и 42. Знак «ТЕХНОПАРК» (рег. №654321) принадлежит ООО «ТехноМаркет».",
    riskLevel: "medium", confidenceScore: 0.78, reviewerDecision: null, overrideReason: "",
    createdAt: "2026-03-10T10:00:00Z",
  },
  {
    id: 2, applicationId: 2, reviewType: "precheck",
    absoluteGroundsSummary: "Обозначение «СИБИРСКИЙ МЁД» содержит географическое указание (Сибирь) и описательный элемент (мёд). Высокий риск отказа по ст. 1483 ГК РФ.",
    relativeGroundsSummary: "Найдены аналогичные обозначения: «СИБИРСКИЙ МЁДЪ» (рег. №789012), «МЁД СИБИРИ» (заявка №2025/123).",
    riskLevel: "high", confidenceScore: 0.85, reviewerDecision: null, overrideReason: "",
    createdAt: "2026-03-12T14:00:00Z",
  },
  {
    id: 3, applicationId: 4, reviewType: "full",
    absoluteGroundsSummary: "Обозначение «ЧИСТЫЙ ДОМ» имеет описательный характер для клининговых услуг. Риск отказа средний — возможно доказать приобретённую различительную способность.",
    relativeGroundsSummary: "Зарегистрированных идентичных знаков не обнаружено. Есть сходные: «ЧИСТОТА В ДОМЕ» (кл. 37).",
    riskLevel: "medium", confidenceScore: 0.72, reviewerDecision: "modify", overrideReason: "Рекомендовано добавить графический элемент для усиления различительной способности",
    createdAt: "2026-03-15T09:00:00Z",
  },
];

// ========== LEGAL FINDINGS ==========
export const mockLegalFindings: LegalFinding[] = [
  {
    id: 1, legalReviewId: 1, findingType: "absolute_ground", groundArticle: "ст. 1483 п.1 пп.3 ГК РФ",
    description: "Обозначение может быть расценено как характеризующее вид и назначение товаров/услуг",
    severity: "medium", confidence: 0.75,
    evidence: "«Технопарк» — общеупотребительный термин для технологических кластеров",
    sourceReference: "Решение Роспатента по заявке №2024/567890",
    recommendation: "Рассмотреть комбинированное обозначение с оригинальным графическим элементом",
  },
  {
    id: 2, legalReviewId: 1, findingType: "relative_ground", groundArticle: "ст. 1483 п.6 ГК РФ",
    description: "Обнаружено сходство до степени смешения с ранее зарегистрированным знаком",
    severity: "high", confidence: 0.82,
    evidence: "Знак «ТЕХНОПАРК» (рег. №654321) зарегистрирован для товаров/услуг классов 9, 35",
    sourceReference: "Реестр товарных знаков ФИПС, рег. №654321",
    recommendation: "Провести детальный анализ перечня товаров/услуг и рассмотреть сужение заявленного перечня",
  },
  {
    id: 3, legalReviewId: 2, findingType: "absolute_ground", groundArticle: "ст. 1483 п.1 пп.3 ГК РФ",
    description: "Географическое указание «Сибирский» в сочетании с родовым названием товара «мёд»",
    severity: "high", confidence: 0.90,
    evidence: "Практика Роспатента по отказам в регистрации географических обозначений с описательными элементами",
    sourceReference: "Методические рекомендации Роспатента, п. 4.3.2",
    recommendation: "Усилить различительную способность через оригинальный графический элемент и стилизацию текста",
  },
  {
    id: 4, legalReviewId: 3, findingType: "absolute_ground", groundArticle: "ст. 1483 п.1 пп.3 ГК РФ",
    description: "Описательный характер обозначения для заявленных услуг",
    severity: "medium", confidence: 0.70,
    evidence: "«Чистый дом» — распространённое выражение для клининговых услуг",
    sourceReference: "Анализ рынка и судебная практика",
    recommendation: "Добавить графический элемент, рассмотреть стилизацию шрифта",
  },
];

// ========== CONFLICT SEARCH RESULTS ==========
export const mockConflictResults: ConflictSearchResult[] = [
  {
    id: 1, applicationId: 1, matchedMark: "ТЕХНОПАРК", owner: "ООО «ТехноМаркет»",
    classes: "9, 35", status: "active", similarityScore: 0.95, phoneticScore: 1.0,
    conflictReason: "Тождественное обозначение в совпадающих классах", reviewerDecision: null,
  },
  {
    id: 2, applicationId: 1, matchedMark: "ТЕХНО-ПАРК", owner: "ИП Григорьев С.А.",
    classes: "42", status: "active", similarityScore: 0.88, phoneticScore: 0.95,
    conflictReason: "Высокая степень фонетического сходства", reviewerDecision: null,
  },
  {
    id: 3, applicationId: 2, matchedMark: "СИБИРСКИЙ МЁДЪ", owner: "ООО «Пасека Сибири»",
    classes: "30", status: "active", similarityScore: 0.92, phoneticScore: 0.97,
    conflictReason: "Высокая степень сходства по фонетическому и семантическому критериям", reviewerDecision: null,
  },
  {
    id: 4, applicationId: 2, matchedMark: "МЁД СИБИРИ", owner: "АО «Алтай-Мёд»",
    classes: "30, 5", status: "pending", similarityScore: 0.75, phoneticScore: 0.70,
    conflictReason: "Семантическое сходство, обратный порядок элементов", reviewerDecision: null,
  },
  {
    id: 5, applicationId: 4, matchedMark: "ЧИСТОТА В ДОМЕ", owner: "ООО «ЧистоСервис»",
    classes: "37", status: "active", similarityScore: 0.68, phoneticScore: 0.55,
    conflictReason: "Семантическое сходство, но различие в составе обозначений", reviewerDecision: "approve",
  },
];

// ========== RECOMMENDATION MEMOS ==========
export const mockRecommendations: RecommendationMemo[] = [
  {
    id: 1, applicationId: 4,
    summary: "Обозначение «ЧИСТЫЙ ДОМ» имеет среднюю вероятность регистрации. Основной риск — описательный характер для клининговых услуг.",
    riskAssessment: "Средний риск. Описательный характер обозначения является основным препятствием. Обнаружен один сходный знак с низкой степенью сходства.",
    recommendedAction: "Рекомендуется преобразовать в комбинированное обозначение с оригинальным графическим элементом для повышения различительной способности.",
    confidence: 0.72,
  },
];

// ========== DOCUMENT PACKAGES ==========
export const mockDocumentPackages: DocumentPackage[] = [
  { id: 1, applicationId: 5, generationStatus: "completed", approvedBy: 5, approvedAt: "2025-12-20T14:00:00Z", createdAt: "2025-12-18T10:00:00Z" },
  { id: 2, applicationId: 6, generationStatus: "completed", approvedBy: 2, approvedAt: "2026-02-25T11:00:00Z", createdAt: "2026-02-20T09:00:00Z" },
  { id: 3, applicationId: 4, generationStatus: "pending", approvedBy: null, approvedAt: null, createdAt: "2026-03-20T08:00:00Z" },
];

// ========== NOTIFICATIONS ==========
export const mockNotifications: Notification[] = [
  { id: 1, userId: 2, applicationId: 1, type: "review_required", title: "Требуется правовой анализ", message: "Заявка №1 (ТЕХНОПАРК) ожидает вашего рассмотрения", isRead: false, createdAt: "2026-03-28T10:00:00Z" },
  { id: 2, userId: 2, applicationId: 2, type: "conflict_found", title: "Обнаружены конфликты", message: "По заявке №2 (СИБИРСКИЙ МЁД) найдены 2 потенциальных конфликта", isRead: false, createdAt: "2026-03-27T15:30:00Z" },
  { id: 3, userId: 2, applicationId: 4, type: "recommendation_ready", title: "Рекомендации готовы", message: "Рекомендации по заявке №4 (ЧИСТЫЙ ДОМ) сформированы", isRead: true, createdAt: "2026-03-26T09:00:00Z" },
  { id: 4, userId: 3, applicationId: 8, type: "data_requested", title: "Ожидание данных клиента", message: "Клиенту отправлен запрос на дополнительные данные по заявке №8", isRead: false, createdAt: "2026-03-25T16:00:00Z" },
  { id: 5, userId: 4, applicationId: 8, type: "action_required", title: "Требуется ваше действие", message: "Пожалуйста, предоставьте скан логотипа для заявки №8 (БЛЕСК ПЛЮС)", isRead: false, createdAt: "2026-03-25T16:05:00Z" },
  { id: 6, userId: 4, applicationId: 4, type: "status_change", title: "Статус заявки обновлён", message: "Заявка №4 (ЧИСТЫЙ ДОМ) перешла в статус «Рекомендации готовы»", isRead: true, createdAt: "2026-03-18T17:00:00Z" },
  { id: 7, userId: 1, applicationId: 7, type: "rejected", title: "Заявка отклонена", message: "Заявка №7 (НАТУРАЛЬНЫЙ) отклонена Роспатентом", isRead: true, createdAt: "2026-01-05T15:30:00Z" },
  { id: 8, userId: 2, applicationId: 1, type: "assignment", title: "Назначена новая заявка", message: "Вам назначена заявка №1 (ТЕХНОПАРК)", isRead: true, createdAt: "2026-01-20T10:30:00Z" },
];

// ========== AUDIT LOGS ==========
export const mockAuditLogs: AuditLog[] = [
  { id: 1, userId: 3, applicationId: 1, action: "Создана заявка", entityType: "application", createdAt: "2026-01-20T10:30:00Z" },
  { id: 2, userId: 3, applicationId: 1, action: "Назначен исполнитель: Козлова Е.С.", entityType: "application", createdAt: "2026-01-20T10:35:00Z" },
  { id: 3, userId: 2, applicationId: 1, action: "Начат правовой анализ", entityType: "legal_review", createdAt: "2026-03-10T10:00:00Z" },
  { id: 4, userId: 3, applicationId: 2, action: "Создана заявка", entityType: "application", createdAt: "2026-02-01T09:00:00Z" },
  { id: 5, userId: 2, applicationId: 2, action: "Запущен поиск конфликтов", entityType: "conflict_search", createdAt: "2026-03-20T11:00:00Z" },
  { id: 6, userId: 3, applicationId: 8, action: "Создана заявка", entityType: "application", createdAt: "2026-03-10T08:00:00Z" },
  { id: 7, userId: 3, applicationId: 8, action: "Запрошены данные у клиента", entityType: "application", createdAt: "2026-03-25T12:00:00Z" },
  { id: 8, userId: 2, applicationId: 4, action: "Правовой анализ завершён", entityType: "legal_review", createdAt: "2026-03-15T09:00:00Z" },
  { id: 9, userId: 5, applicationId: 5, action: "Документы утверждены", entityType: "document_package", createdAt: "2025-12-20T14:00:00Z" },
  { id: 10, userId: 5, applicationId: 5, action: "Заявка подана в Роспатент", entityType: "application", createdAt: "2025-12-22T10:00:00Z" },
  { id: 11, userId: 1, applicationId: null, action: "Создан пользователь: manager@demo.ru", entityType: "user", createdAt: "2025-09-01T09:00:00Z" },
  { id: 12, userId: 5, applicationId: 7, action: "Заявка отклонена Роспатентом", entityType: "application", createdAt: "2026-01-05T15:30:00Z" },
];

// ========== STATUS HISTORY ==========
export const mockStatusHistory: StatusHistoryEntry[] = [
  { id: 1, applicationId: 1, fromStatus: null, toStatus: "draft", changedBy: "Сидоров Д.О.", comment: "Заявка создана", createdAt: "2026-01-20T10:30:00Z" },
  { id: 2, applicationId: 1, fromStatus: "draft", toStatus: "intake_review", changedBy: "Сидоров Д.О.", comment: "Отправлена на первичную проверку", createdAt: "2026-01-20T11:00:00Z" },
  { id: 3, applicationId: 1, fromStatus: "intake_review", toStatus: "legal_precheck_running", changedBy: "Система", comment: "Запущен автоматический предварительный анализ", createdAt: "2026-01-21T09:00:00Z" },
  { id: 4, applicationId: 1, fromStatus: "legal_precheck_running", toStatus: "awaiting_lawyer_review", changedBy: "Система", comment: "Анализ завершён, требуется рассмотрение юриста", createdAt: "2026-03-10T10:00:00Z" },
  { id: 5, applicationId: 2, fromStatus: null, toStatus: "draft", changedBy: "Сидоров Д.О.", comment: "Заявка создана", createdAt: "2026-02-01T09:00:00Z" },
  { id: 6, applicationId: 2, fromStatus: "draft", toStatus: "intake_review", changedBy: "Сидоров Д.О.", comment: "", createdAt: "2026-02-01T09:15:00Z" },
  { id: 7, applicationId: 2, fromStatus: "intake_review", toStatus: "conflict_search_running", changedBy: "Система", comment: "Запущен поиск конфликтов", createdAt: "2026-03-20T11:00:00Z" },
];

// ========== COMPLETENESS CHECKS ==========
export const mockCompletenessChecks: Record<number, CompletenessCheck[]> = {
  1: [
    { field: "markName", label: "Наименование обозначения", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "markType", label: "Вид обозначения", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "goodsServicesRaw", label: "Товары и услуги", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "transliteration", label: "Транслитерация", present: true, severity: "non_blocking", reason: "", provider: "manager" },
    { field: "colorsClaimed", label: "Заявленные цвета", present: false, severity: "non_blocking", reason: "Не указаны, так как словесный знак", provider: "client" },
    { field: "businessDescription", label: "Описание бизнеса", present: true, severity: "blocking", reason: "", provider: "client" },
  ],
  3: [
    { field: "markName", label: "Наименование обозначения", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "markType", label: "Вид обозначения", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "markImage", label: "Изображение обозначения", present: false, severity: "blocking", reason: "Для изобразительного знака требуется изображение", provider: "client" },
    { field: "goodsServicesRaw", label: "Товары и услуги", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "transliteration", label: "Транслитерация", present: false, severity: "non_blocking", reason: "Нет текстовой составляющей", provider: "manager" },
    { field: "businessDescription", label: "Описание бизнеса", present: true, severity: "blocking", reason: "", provider: "client" },
  ],
  8: [
    { field: "markName", label: "Наименование обозначения", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "markImage", label: "Изображение логотипа", present: false, severity: "blocking", reason: "Необходимо предоставить скан или файл логотипа", provider: "client" },
    { field: "goodsServicesRaw", label: "Товары и услуги", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "businessDescription", label: "Описание бизнеса", present: true, severity: "blocking", reason: "", provider: "client" },
    { field: "colorsClaimed", label: "Заявленные цвета", present: true, severity: "non_blocking", reason: "", provider: "client" },
  ],
};

// ========== HELPER FUNCTIONS (mock API) ==========

export function getUser(email: string): User | undefined {
  return mockUsers.find(u => u.email === email);
}

export function getUserById(id: number): User | undefined {
  return mockUsers.find(u => u.id === id);
}

export function getClientById(id: number): Client | undefined {
  return mockClients.find(c => c.id === id);
}

export function getApplicationById(id: number): Application | undefined {
  return mockApplications.find(a => a.id === id);
}

export function getApplicationsByClientId(clientId: number): Application[] {
  return mockApplications.filter(a => a.clientId === clientId);
}

export function getApplicationsByAssignee(userId: number): Application[] {
  return mockApplications.filter(a => a.assigneeId === userId);
}

export function getLegalReviewsForApp(appId: number): LegalReview[] {
  return mockLegalReviews.filter(r => r.applicationId === appId);
}

export function getLegalFindings(reviewId: number): LegalFinding[] {
  return mockLegalFindings.filter(f => f.legalReviewId === reviewId);
}

export function getConflictResults(appId: number): ConflictSearchResult[] {
  return mockConflictResults.filter(c => c.applicationId === appId);
}

export function getClassSuggestions(appId: number): NiceClassSuggestion[] {
  return mockNiceClassSuggestions.filter(c => c.applicationId === appId);
}

export function getRecommendation(appId: number): RecommendationMemo | undefined {
  return mockRecommendations.find(r => r.applicationId === appId);
}

export function getDocPackages(appId: number): DocumentPackage[] {
  return mockDocumentPackages.filter(d => d.applicationId === appId);
}

export function getNotifications(userId: number): Notification[] {
  return mockNotifications.filter(n => n.userId === userId).sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function getUnreadCount(userId: number): number {
  return mockNotifications.filter(n => n.userId === userId && !n.isRead).length;
}

export function getAuditLogs(appId?: number): AuditLog[] {
  const logs = appId ? mockAuditLogs.filter(l => l.applicationId === appId) : mockAuditLogs;
  return logs.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function getStatusHistory(appId: number): StatusHistoryEntry[] {
  return mockStatusHistory.filter(h => h.applicationId === appId).sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

export function getCompletenessChecks(appId: number): CompletenessCheck[] {
  return mockCompletenessChecks[appId] || [];
}

export function getGoodsServicesItems(appId: number): GoodsServicesItem[] {
  return mockGoodsServicesItems.filter(g => g.applicationId === appId);
}
