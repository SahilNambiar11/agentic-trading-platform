SELECT symbol, interval, timestamp, COUNT(*)
FROM market_data
GROUP BY symbol, interval, timestamp
HAVING COUNT(*) > 1;