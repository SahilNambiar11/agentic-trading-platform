SELECT *
FROM market_data
WHERE high_price < low_price
   OR high_price < open_price
   OR high_price < close_price
   OR low_price > open_price
   OR low_price > close_price
   OR volume < 0;