'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend, ScatterChart,
  Scatter, ZAxis
} from 'recharts';

const COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#8b5cf6'];

const chartTooltipStyle = {
  backgroundColor: '#1a2035',
  border: '1px solid rgba(148,163,184,0.2)',
  borderRadius: '8px',
  color: '#f1f5f9',
  fontSize: '13px',
  fontFamily: 'Inter, sans-serif',
};

function formatK(val) {
  if (val >= 1000000) return `$${(val / 1000000).toFixed(1)}M`;
  if (val >= 1000) return `$${(val / 1000).toFixed(0)}K`;
  return `$${val}`;
}

export function PriceDistributionChart({ deals }) {
  // Create price buckets
  const buckets = {};
  deals.forEach(d => {
    const price = d.property.list_price;
    const bucket = Math.floor(price / 50000) * 50000;
    const label = formatK(bucket) + '-' + formatK(bucket + 50000);
    buckets[label] = (buckets[label] || 0) + 1;
  });

  const data = Object.entries(buckets)
    .map(([range, count]) => ({ range, count }))
    .sort((a, b) => {
      const aVal = parseInt(a.range.replace(/[^0-9]/g, ''));
      const bVal = parseInt(b.range.replace(/[^0-9]/g, ''));
      return aVal - bVal;
    })
    .slice(0, 10);

  return (
    <div className="chart-card">
      <h3>📊 Price Distribution</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
          <XAxis dataKey="range" tick={{ fill: '#94a3b8', fontSize: 11 }} angle={-25} textAnchor="end" height={60} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <Tooltip contentStyle={chartTooltipStyle} />
          <Bar dataKey="count" name="Properties" radius={[4, 4, 0, 0]}>
            {data.map((_, idx) => (
              <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DealScoreChart({ deals }) {
  // Grade distribution
  const grades = {};
  deals.forEach(d => {
    const g = d.deal_grade || 'F';
    grades[g] = (grades[g] || 0) + 1;
  });

  const data = Object.entries(grades)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => {
      const order = ['A+', 'A', 'B+', 'B', 'C+', 'C', 'D', 'F'];
      return order.indexOf(a.name) - order.indexOf(b.name);
    });

  const gradeColors = {
    'A+': '#10b981', 'A': '#22d3ee', 'B+': '#6366f1', 'B': '#818cf8',
    'C+': '#f59e0b', 'C': '#fb923c', 'D': '#ef4444', 'F': '#dc2626',
  };

  return (
    <div className="chart-card">
      <h3>🏆 Deal Grade Distribution</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={95}
            dataKey="value"
            label={({ name, value }) => `${name}: ${value}`}
          >
            {data.map((entry, idx) => (
              <Cell key={idx} fill={gradeColors[entry.name] || COLORS[idx % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={chartTooltipStyle} />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ValueVsPriceChart({ deals }) {
  const data = deals.slice(0, 30).map(d => ({
    name: d.property.address.substring(0, 20),
    asking: Math.round(d.property.list_price / 1000),
    estimated: Math.round(d.valuation.estimated_value / 1000),
    score: d.deal_score,
  }));

  return (
    <div className="chart-card">
      <h3>💰 Asking Price vs Estimated Value (in $K)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} barGap={0}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
          <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} angle={-30} textAnchor="end" height={70} interval={0} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <Tooltip contentStyle={chartTooltipStyle} formatter={(val) => `$${val}K`} />
          <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
          <Bar dataKey="asking" name="Asking" fill="#6366f1" radius={[2, 2, 0, 0]} />
          <Bar dataKey="estimated" name="Estimated" fill="#22d3ee" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SqftVsPriceScatter({ deals }) {
  const data = deals.map(d => ({
    sqft: d.property.sqft,
    price: Math.round(d.property.list_price / 1000),
    score: d.deal_score,
    city: d.property.city,
  }));

  return (
    <div className="chart-card">
      <h3>📐 Sqft vs Price Scatter</h3>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
          <XAxis dataKey="sqft" name="Sqft" tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <YAxis dataKey="price" name="Price ($K)" tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <ZAxis dataKey="score" range={[30, 200]} name="Deal Score" />
          <Tooltip
            contentStyle={chartTooltipStyle}
            formatter={(val, name) => {
              if (name === 'Price ($K)') return `$${val}K`;
              return val;
            }}
          />
          <Scatter data={data} fill="#6366f1">
            {data.map((entry, idx) => (
              <Cell key={idx} fill={entry.score >= 60 ? '#10b981' : entry.score >= 40 ? '#f59e0b' : '#ef4444'} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
