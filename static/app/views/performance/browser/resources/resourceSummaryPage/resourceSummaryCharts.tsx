import {t, tct} from 'sentry/locale';
import {formatBytesBase2} from 'sentry/utils/bytes/formatBytesBase2';
import {formatRate} from 'sentry/utils/formatters';
import getDynamicText from 'sentry/utils/getDynamicText';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import useOrganization from 'sentry/utils/useOrganization';
import {RESOURCE_THROUGHPUT_UNIT} from 'sentry/views/performance/browser/resources';
import {Referrer} from 'sentry/views/performance/browser/resources/referrer';
import {
  DATA_TYPE,
  PERFORMANCE_DATA_TYPE,
} from 'sentry/views/performance/browser/resources/settings';
import {useResourceModuleFilters} from 'sentry/views/performance/browser/resources/utils/useResourceFilters';
import {AVG_COLOR, THROUGHPUT_COLOR} from 'sentry/views/starfish/colors';
import Chart, {ChartType} from 'sentry/views/starfish/components/chart';
import ChartPanel from 'sentry/views/starfish/components/chartPanel';
import {useSpanMetricsSeries} from 'sentry/views/starfish/queries/useDiscoverSeries';
import {SpanMetricsField} from 'sentry/views/starfish/types';
import {
  DataTitles,
  getDurationChartTitle,
  getThroughputChartTitle,
} from 'sentry/views/starfish/views/spans/types';
import {Block, BlockContainer} from 'sentry/views/starfish/views/spanSummaryPage/block';

const {
  SPAN_SELF_TIME,
  HTTP_RESPONSE_CONTENT_LENGTH,
  HTTP_DECODED_RESPONSE_CONTENT_LENGTH,
  HTTP_RESPONSE_TRANSFER_SIZE,
  RESOURCE_RENDER_BLOCKING_STATUS,
} = SpanMetricsField;

function ResourceSummaryCharts(props: {groupId: string}) {
  const filters = useResourceModuleFilters();
  const organization = useOrganization();

  const isInsightsEnabled = organization.features.includes('performance-insights');
  const resourceDataType = isInsightsEnabled ? DATA_TYPE : PERFORMANCE_DATA_TYPE;

  const {data: spanMetricsSeriesData, isLoading: areSpanMetricsSeriesLoading} =
    useSpanMetricsSeries(
      {
        search: MutableSearch.fromQueryObject({
          'span.group': props.groupId,
          ...(filters[RESOURCE_RENDER_BLOCKING_STATUS]
            ? {
                [RESOURCE_RENDER_BLOCKING_STATUS]:
                  filters[RESOURCE_RENDER_BLOCKING_STATUS],
              }
            : {}),
        }),
        yAxis: [
          `spm()`,
          `avg(${SPAN_SELF_TIME})`,
          `avg(${HTTP_RESPONSE_CONTENT_LENGTH})`,
          `avg(${HTTP_DECODED_RESPONSE_CONTENT_LENGTH})`,
          `avg(${HTTP_RESPONSE_TRANSFER_SIZE})`,
        ],
        enabled: Boolean(props.groupId),
      },
      Referrer.RESOURCE_SUMMARY_CHARTS
    );

  if (spanMetricsSeriesData) {
    spanMetricsSeriesData[`avg(${HTTP_RESPONSE_TRANSFER_SIZE})`].lineStyle = {
      type: 'dashed',
    };
    spanMetricsSeriesData[`avg(${HTTP_DECODED_RESPONSE_CONTENT_LENGTH})`].lineStyle = {
      type: 'dashed',
    };
  }

  return (
    <BlockContainer>
      <Block>
        <ChartPanel title={getThroughputChartTitle('http', RESOURCE_THROUGHPUT_UNIT)}>
          <Chart
            height={160}
            data={[spanMetricsSeriesData?.[`spm()`]]}
            loading={areSpanMetricsSeriesLoading}
            type={ChartType.LINE}
            definedAxisTicks={4}
            aggregateOutputFormat="rate"
            rateUnit={RESOURCE_THROUGHPUT_UNIT}
            stacked
            chartColors={[THROUGHPUT_COLOR]}
            tooltipFormatterOptions={{
              valueFormatter: value => formatRate(value, RESOURCE_THROUGHPUT_UNIT),
              nameFormatter: () => t('Requests'),
            }}
          />
        </ChartPanel>
      </Block>
      <Block>
        <ChartPanel title={getDurationChartTitle('http')}>
          <Chart
            height={160}
            data={[spanMetricsSeriesData?.[`avg(${SPAN_SELF_TIME})`]]}
            loading={areSpanMetricsSeriesLoading}
            chartColors={[AVG_COLOR]}
            type={ChartType.LINE}
            definedAxisTicks={4}
          />
        </ChartPanel>
      </Block>
      <Block>
        <ChartPanel title={tct('Average [dataType] Size', {dataType: resourceDataType})}>
          <Chart
            height={160}
            aggregateOutputFormat="size"
            data={[
              spanMetricsSeriesData?.[`avg(${HTTP_DECODED_RESPONSE_CONTENT_LENGTH})`],
              spanMetricsSeriesData?.[`avg(${HTTP_RESPONSE_TRANSFER_SIZE})`],
              spanMetricsSeriesData?.[`avg(${HTTP_RESPONSE_CONTENT_LENGTH})`],
            ]}
            loading={areSpanMetricsSeriesLoading}
            chartColors={[AVG_COLOR]}
            type={ChartType.LINE}
            definedAxisTicks={4}
            tooltipFormatterOptions={{
              valueFormatter: bytes =>
                getDynamicText({
                  value: formatBytesBase2(bytes),
                  fixed: 'xx KiB',
                }),
              nameFormatter: name => DataTitles[name],
            }}
          />
        </ChartPanel>
      </Block>
    </BlockContainer>
  );
}

export default ResourceSummaryCharts;
