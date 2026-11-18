export const analysisLimits = {minTexts: 12, maxTexts: 100, maxChars: 500, maxBytes: 65_536};

type TopicGroup = {size: number; keywords: string[]};
type MethodResult = {groups: TopicGroup[]; unassigned: number; iteration_limit: boolean};
export const analysisMethods = ['nmf', 'minilm'] as const;
export type AnalysisMethod = typeof analysisMethods[number] | 'both';
export const expressionCategories = {
  emotions: ['worry', 'excitement', 'frustration', 'confidence', 'curiosity'],
  needs: ['information', 'guidance', 'support'],
  experiences: ['reported']
} as const;
export type ExpressionSignals = {submitted_texts: number} & {
  [Group in keyof typeof expressionCategories]: Record<typeof expressionCategories[Group][number], number>;
};
export type LocalAnalysisResult = {
  methods: Partial<Record<typeof analysisMethods[number], MethodResult>>;
  agreement: {ari: number | null; common_assigned: number} | null;
  expression_signals?: ExpressionSignals;
};

export function isLocalAnalysisEnabled(environment: string | undefined, setting: string | undefined) {
  return environment === 'development' && setting === '1';
}

export function parseTextarea(input: string) {
  return input.split(/\r\n|\r|\n/).map(line => line.trim()).filter(Boolean);
}

export function makeAnalysisBody(texts: string[], k: 2 | 3, method: AnalysisMethod) {
  const body = JSON.stringify({texts, k, method, include_signals: true});
  const {minTexts, maxTexts, maxChars, maxBytes} = analysisLimits;
  if (texts.length < minTexts || texts.length > maxTexts) return {error: 'textCount'} as const;
  if (texts.some(text => [...text].length > maxChars) || new TextEncoder().encode(body).length > maxBytes) {
    return {error: 'tooLarge'} as const;
  }
  return {body} as const;
}

function hasKeys(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}

export function isExpressionSignals(value: unknown, total: number): value is ExpressionSignals {
  if (!hasKeys(value, ['submitted_texts', ...Object.keys(expressionCategories)]) || value.submitted_texts !== total) {
    return false;
  }
  return Object.entries(expressionCategories).every(([group, labels]) => {
    const counts = value[group];
    return hasKeys(counts, labels) && labels.every(label => {
      const count = counts[label];
      return isCount(count) && count <= total;
    });
  });
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= analysisLimits.maxTexts;
}

function isTopicGroup(value: unknown): value is TopicGroup {
  return hasKeys(value, ['size', 'keywords']) && isCount(value.size) &&
    Array.isArray(value.keywords) && value.keywords.length <= 4 &&
    (value.size >= 3 || value.keywords.length === 0) && new Set(value.keywords).size === value.keywords.length &&
    value.keywords.every(word => typeof word === 'string' && /^[a-z]{2,24}$/.test(word));
}

export function isMethodResult(value: unknown, expectedCount?: number, expectedK?: number): value is MethodResult {
  if (!hasKeys(value, ['groups', 'unassigned', 'iteration_limit']) || !isCount(value.unassigned) ||
      typeof value.iteration_limit !== 'boolean' || !Array.isArray(value.groups) ||
      ![2, 3].includes(value.groups.length) || !value.groups.every(isTopicGroup)) return false;
  const total = value.groups.reduce((sum, group) => sum + group.size, value.unassigned);
  return total >= analysisLimits.minTexts && total <= analysisLimits.maxTexts &&
    (expectedCount === undefined || total === expectedCount) &&
    (expectedK === undefined || value.groups.length === expectedK);
}

export function resultTextCount(result: MethodResult) {
  return result.groups.reduce((total, group) => total + group.size, result.unassigned);
}

export function isLocalAnalysisResult(value: unknown, expectedCount?: number, expectedK?: number, expectedMethod?: AnalysisMethod): value is LocalAnalysisResult {
  const withSignals = typeof value === 'object' && value !== null && Object.hasOwn(value, 'expression_signals');
  const keys = withSignals ? ['methods', 'agreement', 'expression_signals'] : ['methods', 'agreement'];
  if (!hasKeys(value, keys) || !value.methods || typeof value.methods !== 'object') return false;
  const methods = Object.keys(value.methods);
  if (!methods.length || !methods.every(method => method === 'nmf' || method === 'minilm')) return false;
  if (expectedMethod === 'both' ? methods.length !== 2 : expectedMethod && (methods.length !== 1 || methods[0] !== expectedMethod)) return false;
  const {nmf, minilm} = value.methods as Record<string, unknown>;
  const validNmf = isMethodResult(nmf, expectedCount, expectedK);
  const validMiniLM = isMethodResult(minilm, expectedCount, expectedK);
  if (methods.includes('nmf') && !validNmf) return false;
  if (methods.includes('minilm') && (!validMiniLM || minilm.unassigned !== 0)) return false;
  if (withSignals && !isExpressionSignals(value.expression_signals,
    validNmf ? resultTextCount(nmf) : validMiniLM ? resultTextCount(minilm) : 0)) return false;
  if (methods.length === 1) return value.agreement === null;
  if (!isMethodResult(nmf) || !isMethodResult(minilm) || nmf.groups.length !== minilm.groups.length ||
      resultTextCount(nmf) !== resultTextCount(minilm)) return false;
  const agreement = value.agreement;
  if (!hasKeys(agreement, ['ari', 'common_assigned']) || agreement.common_assigned !== resultTextCount(nmf) - nmf.unassigned) return false;
  return agreement.ari === null || (typeof agreement.ari === 'number' && agreement.ari >= -1 && agreement.ari <= 1 &&
    typeof agreement.common_assigned === 'number' && agreement.common_assigned >= 3);
}
