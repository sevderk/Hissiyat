import {trendPath, type TrendPoint} from '@/lib/trends-research';

type Props = {
  points: TrendPoint[];
  ticks: number[];
  chartLabel: string;
  formatDate: (date: string) => string;
  formatValue: (value: number) => string;
  comparison?: TrendPoint[];
  activeIndex?: number;
};

export function TrendPlot({points, ticks, chartLabel, formatDate, formatValue, comparison, activeIndex}: Props) {
  const position = points.map(point => Date.parse(point.date + 'T00:00:00Z'));
  const span = position[position.length - 1] - position[0];
  const x = (index: number) => span ? 20 + (position[index] - position[0]) * 760 / span : 400;
  const gapWidth = (index: number) => Math.min(24, (index > 0 ? x(index) - x(index - 1) : Infinity) * .8,
    (index < points.length - 1 ? x(index + 1) - x(index) : Infinity) * .8);
  const divisor = Math.max(Math.abs(ticks[0]), Math.abs(ticks[ticks.length - 1])) || 1;
  const lower = ticks[ticks.length - 1] / divisor;
  const upper = ticks[0] / divisor;
  const y = (value: number) => upper === lower ? 100 : 200 * (upper - value / divisor) / (upper - lower);
  const series = comparison ? [points, comparison] : [points];

  return (
    <div className="trend-chart">
      <div className="trend-y" aria-hidden="true" style={ticks.length === 1 ? {justifyContent: 'center'} : undefined}>
        {ticks.map(tick => <span key={tick}>{formatValue(tick)}</span>)}
      </div>
      <div className="trend-plot">
        <svg role="img" aria-label={chartLabel} viewBox="0 -7 800 214" preserveAspectRatio="none">
          {ticks.map(tick => <line key={tick} x1="0" x2="800" y1={y(tick)} y2={y(tick)} className="trend-grid-line" vectorEffect="non-scaling-stroke" />)}
          {activeIndex !== undefined && <line x1={x(activeIndex)} x2={x(activeIndex)} y1="0" y2="200"
            className="trend-cursor" vectorEffect="non-scaling-stroke" />}
          {series.map((line, seriesIndex) => <g key={seriesIndex} className={seriesIndex ? 'trend-secondary' : undefined}>
            {line.map(({date, status}, index) => {
              if (status === 'observed') return null;
              const width = gapWidth(index);
              return <rect key={date} data-gap={status} x={x(index) - width / 2} y={comparison ? 100 * seriesIndex : 0}
                width={width} height={comparison ? 100 : 200} className={'trend-gap ' + status} />;
            })}
            <path d={trendPath(line, x, y)} className="trend-line" vectorEffect="non-scaling-stroke" />
            {line.map(({date, value}, index) => value !== null && (
              <circle key={date} cx={x(index)} cy={y(value)} r={index === activeIndex ? 7 : 4}
                className="trend-dot" vectorEffect="non-scaling-stroke" />
            ))}
          </g>)}
        </svg>
        <div className="trend-x" aria-hidden="true">
          <span>{formatDate(points[0].date)}</span>
          {points.length > 2 && <span>{formatDate(points[Math.floor(points.length / 2)].date)}</span>}
          {points.length > 1 && <span>{formatDate(points[points.length - 1].date)}</span>}
        </div>
      </div>
    </div>
  );
}
