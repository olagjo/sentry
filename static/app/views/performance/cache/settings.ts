import {t} from 'sentry/locale';
import type {SpanMetricsQueryFilters} from 'sentry/views/starfish/types';

export const MODULE_TITLE = t('Caches');
export const BASE_URL = 'caches';

// NOTE: Awkward typing, but without it `RELEASE_LEVEL` is narrowed and the comparison is not allowed
export const releaseLevelAsBadgeProps = {
  isNew: true,
};

export const CHART_HEIGHT = 160;

export const CACHE_BASE_URL = `/performance/${BASE_URL}`;

export const BASE_FILTERS: SpanMetricsQueryFilters = {
  'span.op': '[cache.get_item,cache.get]', //  TODO - add more span ops as they become available, we can't use span.module because db.redis is also `cache`
}; // TODO - Its akward to construct an array here, mutibleSearch should support array values

export const MODULE_DESCRIPTION = t(
  'Discover whether your application is utilizing caching effectively and understand the latency associated with cache misses.'
);
export const MODULE_DOC_LINK = 'https://docs.sentry.io/product/performance/caches/';

export const ONBOARDING_CONTENT = {
  title: t('Start collecting Insights about your Caches!'),
  description: t('Our robot is waiting to collect your first cache hit.'),
  link: MODULE_DOC_LINK,
};
