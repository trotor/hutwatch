// HutWatch Übersicht Widget
// https://tracesof.net/uebersicht/
//
// Displays sensor temperatures and weather from HutWatch SQLite database.
// Adjust PYTHON_PATH and DB_PATH below to match your installation.

const PYTHON_PATH = "/path/to/hutwatch/venv/bin/python3";
const DB_PATH = "/path/to/hutwatch/hutwatch.db";

export const refreshFrequency = 30000; // 30 seconds

export const command = `${PYTHON_PATH} -m hutwatch.widget_output -d ${DB_PATH} 2>/dev/null`;

export const className = `
  bottom: 20px;
  left: 20px;
  font-family: "SF Mono", "Menlo", "Monaco", monospace;
  font-size: 12px;
  color: #e0e0e0;
  background: rgba(20, 20, 20, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 14px 18px;
  min-width: 280px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  line-height: 1.5;

  .title {
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.15);
    padding-bottom: 6px;
  }

  .section-label {
    font-size: 10px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 10px;
    margin-bottom: 4px;
  }

  .sensor-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
  }

  .sensor-name {
    color: #ccc;
  }

  .sensor-temp {
    font-weight: 600;
    color: #fff;
  }

  .sensor-humidity {
    color: #888;
    margin-left: 8px;
  }

  .sensor-age {
    color: #666;
    font-size: 11px;
    margin-left: 6px;
  }

  .dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
  }

  .dot-green { background: #4caf50; }
  .dot-yellow { background: #ff9800; }
  .dot-red { background: #f44336; }

  .weather-row {
    display: flex;
    justify-content: space-between;
    padding: 1px 0;
    color: #bbb;
  }

  .weather-value {
    color: #ddd;
  }

  .error {
    color: #f44336;
    font-style: italic;
  }

  .timestamp {
    font-size: 10px;
    color: #555;
    text-align: right;
    margin-top: 8px;
  }
`;

function formatAge(seconds) {
  if (seconds == null) return "";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}min`;
  return `${Math.floor(seconds / 3600)}h`;
}

function dotClass(ageSeconds) {
  if (ageSeconds == null) return "dot dot-red";
  if (ageSeconds < 300) return "dot dot-green";
  if (ageSeconds < 600) return "dot dot-yellow";
  return "dot dot-red";
}

const WEATHER_SYMBOLS = {
  clearsky: "\u2600\uFE0F",
  fair: "\uD83C\uDF24\uFE0F",
  partlycloudy: "\u26C5",
  cloudy: "\u2601\uFE0F",
  fog: "\uD83C\uDF2B\uFE0F",
  lightrain: "\uD83C\uDF26\uFE0F",
  rain: "\uD83C\uDF27\uFE0F",
  heavyrain: "\uD83C\uDF27\uFE0F",
  snow: "\u2744\uFE0F",
  heavysnow: "\u2744\uFE0F",
  thunder: "\u26C8\uFE0F",
};

function weatherEmoji(symbolCode) {
  if (!symbolCode) return "\uD83C\uDF21\uFE0F";
  const base = symbolCode.split("_")[0];
  return WEATHER_SYMBOLS[base] || "\uD83C\uDF21\uFE0F";
}

function windDirection(degrees) {
  if (degrees == null) return "";
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.floor((degrees + 22.5) / 45) % 8];
}

export const render = ({ output, error }) => {
  if (error) {
    return <div className="error">Error: {String(error)}</div>;
  }

  let data;
  try {
    data = JSON.parse(output);
  } catch (e) {
    return <div className="error">Parse error</div>;
  }

  if (data.error) {
    return <div className="error">{data.error}</div>;
  }

  const title = data.site_name ? `HutWatch \u2014 ${data.site_name}` : "HutWatch";

  return (
    <div>
      <div className="title">{title}</div>

      {data.sensors && data.sensors.length > 0 && (
        <div>
          <div className="section-label">Sensors</div>
          {data.sensors.map((s, i) => (
            <div className="sensor-row" key={i}>
              <span>
                <span className={dotClass(s.age_seconds)} />
                <span className="sensor-name">{s.name}</span>
              </span>
              <span>
                {s.temperature != null ? (
                  <span>
                    <span className="sensor-temp">{s.temperature.toFixed(1)}&deg;C</span>
                    {s.humidity != null && (
                      <span className="sensor-humidity">{s.humidity.toFixed(0)}%</span>
                    )}
                    <span className="sensor-age">{formatAge(s.age_seconds)}</span>
                  </span>
                ) : (
                  <span className="sensor-age">offline</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      {data.weather && (
        <div>
          <div className="section-label">
            {weatherEmoji(data.weather.symbol_code)} {data.weather.location || "Weather"}
          </div>
          <div className="weather-row">
            <span>Temp</span>
            <span className="weather-value">{data.weather.temperature.toFixed(1)}&deg;C</span>
          </div>
          {data.weather.humidity != null && (
            <div className="weather-row">
              <span>Humidity</span>
              <span className="weather-value">{data.weather.humidity.toFixed(0)}%</span>
            </div>
          )}
          {data.weather.wind_speed != null && (
            <div className="weather-row">
              <span>Wind</span>
              <span className="weather-value">
                {data.weather.wind_speed.toFixed(1)} m/s{" "}
                {windDirection(data.weather.wind_direction)}
              </span>
            </div>
          )}
          {data.weather.pressure != null && (
            <div className="weather-row">
              <span>Pressure</span>
              <span className="weather-value">{data.weather.pressure.toFixed(0)} hPa</span>
            </div>
          )}
        </div>
      )}

      <div className="timestamp">{data.timestamp}</div>
    </div>
  );
};
