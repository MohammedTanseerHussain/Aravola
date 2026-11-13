
import pg from 'pg';

const { Pool } = pg;

export function openDatabase(databaseUrl) {
  if (!databaseUrl || typeof databaseUrl !== 'string') {
    throw new Error('DATABASE_URL is required to connect to PostgreSQL.');
  }

  const pool = new Pool({
    connectionString: databaseUrl,
    ssl: process.env.DB_SSL === 'true'
      ? { rejectUnauthorized: true }
      : false,
    max: 5,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 10000,
    keepAlive: true,
  });

  pool.on('error', (error) => {
    console.error('[database] Unexpected PostgreSQL error:', error.message);
  });

  return pool;
}

export async function withTransaction(pool, work) {
  const client = await pool.connect();

  try {
    await client.query('BEGIN');

    const result = await work(client);

    await client.query('COMMIT');

    return result;
  } catch (error) {
    try {
      await client.query('ROLLBACK');
    } catch (rollbackError) {
      console.error('[database] Rollback failed:', rollbackError.message);
    }

    throw error;
  } finally {
    client.release();
  }
}

export async function checkDatabase(pool) {
  await pool.query('SELECT 1');
  return true;
}
