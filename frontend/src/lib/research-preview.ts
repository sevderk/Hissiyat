// Curated Phase 5A/5D aggregates for the opt-in local preview.
export const researchPreview = {
  reviewedQuestions: 80,
  overlapQuestions: 12,
  stabilityRepetitions: 5,
  stabilitySampleShare: 0.8,
  comparisons: [
    {k: 2, betweenMethods: 0.3518, nmfStability: 0.8184, miniLmStability: 0.8770},
    {k: 3, betweenMethods: 0.1823, nmfStability: 0.5177, miniLmStability: 0.4989}
  ],
  source: {
    release: 'https://github.com/RenaissancePhilanthropy/careernet-data/releases/tag/v1.1',
    license: 'https://creativecommons.org/licenses/by/4.0/'
  }
} as const;

export function isResearchPreviewEnabled(environment: string | undefined, setting: string | undefined) {
  return environment === 'development' && setting === '1';
}
