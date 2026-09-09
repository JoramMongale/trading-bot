import { DuckDBInstance } from '@duckdb/node-api';

const dbPath = process.env.DUCKDB_TEST_PATH || 'C:/Users/joram/Documents/trading-bot-windows-289e5dc/trading-bot/data/analytics/trading.duckdb';
const instance = await DuckDBInstance.create(dbPath, { access_mode: 'read_only' });
const connection = await instance.connect();
const reader = await connection.runAndReadAll('SELECT source_log, last_event_ts FROM mart_bot_health LIMIT 3');
const rows = reader.getRowObjects();
console.log('rows:', JSON.stringify(rows, (k, v) => (typeof v === 'bigint' ? v.toString() : v), 1));
console.log('OK: duckdb node-api reads marts');
connection.closeSync();
