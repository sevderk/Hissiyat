import type {TrendPoint} from '@/lib/trends-research';

type Props = {
  points: TrendPoint[];
  ticks: number[];
  chartLabel: string;
  formatDate: (date: string) => string;
  formatValue: (value: number) => string;
};

export function TrendPlot({points, ticks, chartLabel, formatDate, formatValue}: Props) {
  const position = points.map(point => Date.parse(point.date + 'T00:00:00Z'));
  const span = position[position.length - 1] - position[0];
  const x = (index: number) => span ? 20 + (position[index] - position[0]) * 760 / span : 400;
  const divisor = Math.max(Math.abs(ticks[0]), Math.abs(ticks[ticks.length - 1])) || 1;
  const lower = ticks[ticks.length - 1] / divisor;
  const upper = ticks[0] / divisor;
  const y = (value: number) => upper === lower ? 100 : 200 * (upper - value / divisor) / (upper - lower);
  const path = points.map(({value}, index) => value === null ? '' :
    (index > 0 && points[index - 1].value !== null ? 'L' : 'M') + x(index) + ' ' + y(value)).join(' ');

  return (
    <div className="trend-chart">
      <div className="trend-y" aria-hidden="true" style={ticks.length === 1 ? {justifyContent: 'center'} : undefined}>
        {ticks.map(tick => <span key={tick}>{formatValue(tick)}</span>)}
      </div>
      <div className="trend-plot">
        <svg role="img" aria-label={chartLabel} viewBox="0 -7 800 214" preserveAspectRatio="none">
          {ticks.map(tick => <line key={tick} x1="0" x2="800" y1={y(tick)} y2={y(tick)} className="trend-grid-line" vectorEffect="non-scaling-stroke" />)}
          {points.map(({date, status}, index) => status !== 'observed' && (
            <rect key={date} data-gap={status} x={x(index) - 12} y="0" width="24" height="200" className={'trend-gap ' + status} />
          ))}
          <path d={path} className="trend-line" vectorEffect="non-scaling-stroke" />
          {points.map(({date, value}, index) => value !== null && (
            <circle key={date} cx={x(index)} cy={y(value)} r="4" className="trend-dot" vectorEffect="non-scaling-stroke" />
          ))}
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
