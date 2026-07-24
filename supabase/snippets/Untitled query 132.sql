SELECT
  COUNT(*) AS total_rows,
  MIN(timestamp) AS earliest,
  MAX(timestamp) AS latest
FROM market_data
WHERE symbol = 'SPY'
  AND interval = '1d';